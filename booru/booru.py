import logging
from asyncio import TimeoutError
from typing import Any, Dict, List, Optional, Type

import aiohttp
import discord
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from .core.exceptions import RequestError
from .core.tags import TagHandler
from .sources import (
    DanbooruSource,
    GelbooruSource,
    KonachanSource,
    Rule34Source,
    SafebooruSource,
    YandereSource,
)

log = logging.getLogger("red.booru")

ALL_SOURCES: Dict[str, Type] = {
    "danbooru": DanbooruSource,
    "gelbooru": GelbooruSource,
    "konachan": KonachanSource,
    "yandere": YandereSource,
    "safebooru": SafebooruSource,
    "rule34": Rule34Source,
}


class Booru(commands.Cog):
    """Search booru sites for anime art."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession()

        self.config = Config.get_conf(self, identifier=127318273, force_registration=True)
        self.tag_handler = TagHandler()

        self.sources: Dict[str, Any] = {name: cls(self.session) for name, cls in ALL_SOURCES.items()}

        default_global = {
            "api_keys": {"gelbooru": {"api_key": None, "user_id": None}},
            "filters": {
                "blacklist": [],
                "source_order": list(ALL_SOURCES.keys()),
            },
        }
        self.config.register_global(**default_global)
        self._register_source_commands()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def _get_post_from_source(
        self, source_name: str, tag_string: str, is_nsfw: bool = False
    ) -> Optional[Dict[str, Any]]:
        source = self.sources.get(source_name)
        if not source:
            return None

        credentials = None
        if source_name == "gelbooru":
            api_keys = (await self.config.api_keys())["gelbooru"]
            if api_keys["api_key"] and api_keys["user_id"]:
                credentials = api_keys

        positive_tags, negative_tags = self.tag_handler.parse_tags(tag_string)
        if not is_nsfw:
            negative_tags.add("rating:explicit")
            negative_tags.add("rating:questionable")
        tag_list = self.tag_handler.combine_tags(positive_tags, negative_tags)

        try:
            posts = await source.get_posts(tag_list, limit=1, credentials=credentials)
            if not posts:
                return None
            return source.parse_post(posts[0])
        except Exception as e:
            log.exception(f"Unexpected error fetching from {source_name}: {e}")
            return None

    async def _get_multiple_posts_from_source(
        self, source_name: str, tag_string: str, is_nsfw: bool, limit: int = 5
    ) -> List[Dict[str, Any]]:
        source = self.sources.get(source_name)
        if not source:
            return []
        credentials = None
        if source_name == "gelbooru":
            api_keys = (await self.config.api_keys())["gelbooru"]
            if api_keys["api_key"] and api_keys["user_id"]:
                credentials = api_keys
        positive_tags, negative_tags = self.tag_handler.parse_tags(tag_string)
        if not is_nsfw:
            negative_tags.add("rating:explicit")
            negative_tags.add("rating:questionable")
        tag_list = self.tag_handler.combine_tags(positive_tags, negative_tags)
        try:
            posts = await source.get_posts(tag_list, limit=limit, credentials=credentials)
        except Exception as e:
            log.exception(f"Unexpected error fetching multiple from {source_name}: {e}")
            return []
        return [source.parse_post(p) for p in posts if p]

    def _format_embed_or_spoiler(self, post: dict, source: str) -> Dict[str, Any]:
        rating = post.get("rating", "").lower()
        url = post.get("url", "")
        desc = f"Source: **{source}**\nRating: **{rating}**\nID: {post.get('id', '')}"
        embed = discord.Embed(description=desc, color=discord.Color.random())
        if post.get("score") is not None:
            embed.add_field(name="Score", value=post["score"])
        if rating == "explicit":
            return {"content": f"{desc}\n||{url}||", "embed": None}
        else:
            embed.set_image(url=url)
            return {"content": None, "embed": embed}

    @commands.group(invoke_without_command=True)
    async def booru(self, ctx: commands.Context, *, tag_string: str = ""):
        """Searches booru sites for images using the configured source order. Explicit images are spoilered."""
        is_nsfw = ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else True
        source_order = (await self.config.filters())["source_order"]
        if not source_order:
            await ctx.send("No sources configured.")
            return

        posts = []
        used_source: Optional[str] = None

        for source_name in source_order:
            try:
                posts = await self._get_multiple_posts_from_source(source_name, tag_string, is_nsfw, limit=100)
                if posts:
                    used_source = source_name
                    break
            except RequestError as e:
                log.error(f"Error with {source_name}: {e}")
                continue

        if not posts or used_source is None:
            await ctx.send("No results found in any source.")
            return

        current_index = 0
        post = posts[current_index]
        result = self._format_embed_or_spoiler(post, used_source)
        message = await ctx.send(**result)

        if len(posts) == 1:
            return

        controls = ["◀️", "❌", "▶️"]
        for emoji in controls:
            await message.add_reaction(emoji)

        def check(reaction, user):
            return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in controls

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            except TimeoutError:
                try:
                    await message.clear_reactions()
                except Exception:
                    pass
                break

            if str(reaction.emoji) == "◀️":
                current_index = (current_index - 1) % len(posts)
            elif str(reaction.emoji) == "▶️":
                current_index = (current_index + 1) % len(posts)
            elif str(reaction.emoji) == "❌":
                try:
                    await message.clear_reactions()
                except Exception:
                    pass
                break

            post = posts[current_index]
            result = self._format_embed_or_spoiler(post, used_source)
            await message.edit(**result)

            try:
                await message.remove_reaction(reaction.emoji, user)
            except Exception:
                pass

    @commands.group(name="boorus", invoke_without_command=True)
    async def source_specific(self, ctx: commands.Context):
        """Commands to search a specific booru source."""
        await ctx.send_help()

    def _register_source_commands(self):
        for source_name in ALL_SOURCES.keys():

            async def _source_command(this, ctx: commands.Context, *, tag_string: str = "", source_name=source_name):
                is_nsfw = ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else True
                async with ctx.typing():
                    post = await this._get_post_from_source(source_name, tag_string, is_nsfw)
                    if not post:
                        await ctx.send(f"No results found on {source_name.title()}.")
                        return
                    result = this._format_embed_or_spoiler(post, source_name)
                    await ctx.send(**result)

            _source_command.__name__ = f"{source_name}_search"
            _source_command.__doc__ = f"Search {source_name.title()} specifically."
            setattr(self, _source_command.__name__, _source_command)
            self.source_specific.command(name=source_name[:3])(_source_command)  # type: ignore[attr-defined]

    @commands.group(name="booruset")
    @checks.admin_or_permissions(administrator=True)
    async def settings(self, ctx: commands.Context):
        """Configure booru settings."""
        pass

    @settings.command(name="blacklist")  # type: ignore[attr-defined]
    async def add_blacklist(self, ctx: commands.Context, *, tag: str):
        """Add a tag to the blacklist."""
        async with self.config.filters.blacklist() as blacklist:
            if tag not in blacklist:
                blacklist.append(tag)
                await ctx.send(f"Added tag to blacklist: {tag}")
            else:
                await ctx.send("Tag already blacklisted.")

    @settings.command(name="unblacklist")  # type: ignore[attr-defined]
    async def remove_blacklist(self, ctx: commands.Context, *, tag: str):
        """Remove a tag from the blacklist."""
        async with self.config.filters.blacklist() as blacklist:
            if tag in blacklist:
                blacklist.remove(tag)
                await ctx.send(f"Removed tag from blacklist: {tag}")
            else:
                await ctx.send("Tag not found in blacklist.")

    @settings.command(name="listblacklist")  # type: ignore[attr-defined]
    async def list_blacklist(self, ctx: commands.Context):
        """List all blacklisted tags."""
        blacklist = await self.config.filters.blacklist()
        if blacklist:
            await ctx.send("\n".join(blacklist))
        else:
            await ctx.send("No tags blacklisted.")

    @settings.command(name="setapi")  # type: ignore[attr-defined]
    @commands.is_owner()
    async def set_api_key(self, ctx: commands.Context, api_key: str, user_id: str):
        """Set Gelbooru API credentials."""
        async with self.config.api_keys() as api_keys:
            api_keys["gelbooru"]["api_key"] = api_key
            api_keys["gelbooru"]["user_id"] = user_id

        await ctx.send("Gelbooru API credentials set.")
        await ctx.message.delete()
