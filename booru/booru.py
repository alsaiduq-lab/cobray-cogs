import logging
from asyncio import TimeoutError
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from aiohttp import ClientError, ClientResponseError
from redbot.core import Config, checks, commands
from redbot.core.bot import Red

from .core.exceptions import RequestError
from .core.tags import TagHandler
from .sources import DanbooruSource, GelbooruSource, KonachanSource, Rule34Source, SafebooruSource, YandereSource

log = logging.getLogger("red.booru")


class Booru(commands.Cog):
    """Search booru sites for anime art."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, identifier=127318273, force_registration=True)
        self.tag_handler = TagHandler()

        self.sources = {
            "danbooru": DanbooruSource(self.session),
            "gelbooru": GelbooruSource(self.session),
            "konachan": KonachanSource(self.session),
            "yandere": YandereSource(self.session),
            "safebooru": SafebooruSource(self.session),
            "rule34": Rule34Source(self.session),
        }

        default_global = {
            "api_keys": {"gelbooru": {"api_key": None, "user_id": None}},
            "filters": {
                "blacklist": [],
                "source_order": [
                    "danbooru",
                    "gelbooru",
                    "konachan",
                    "yandere",
                    "safebooru",
                    "rule34",
                ],
            },
            "dm_nsfw_allowed": [],
        }

        self.config.register_global(**default_global)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    async def is_dm_nsfw_allowed(self, user: discord.User) -> bool:
        """Check if user is allowed NSFW in DMs (owner or whitelisted)."""
        if await self.bot.is_owner(user):
            return True
        allowed = await self.config.dm_nsfw_allowed()
        return user.id in allowed

    async def dm_access_denied(self, ctx: commands.Context) -> bool:
        """Returns True if DM access is denied."""
        if isinstance(ctx.channel, discord.DMChannel):
            allowed = await self.is_dm_nsfw_allowed(ctx.author)
            if not allowed:
                await ctx.send("You are not allowed to use this command in DMs.")
                return True
        return False

    async def get_nsfw_status(self, ctx: commands.Context) -> bool:
        """Determine if NSFW should be allowed (guild/DM)."""
        if isinstance(ctx.channel, discord.TextChannel):
            return ctx.channel.is_nsfw()
        return await self.is_dm_nsfw_allowed(ctx.author)

    async def get_post(self, source_name: str, tag_string: str, is_nsfw: bool = False) -> Optional[Dict[str, Any]]:
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
        except ClientResponseError as cre:
            log.error(f"[{source_name}] HTTP {cre.status} error: {cre.message}")
            return None
        except (ClientError, TimeoutError) as ce:
            log.error(f"Connection error while fetching from {source_name}: {ce}")
            return None
        except Exception as e:
            log.exception(f"Unexpected error fetching from {source_name}: {e}")
            return None

    async def get_multiple_posts(
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
        except ClientResponseError as cre:
            log.error(f"HTTP {cre.status} error on multiple fetch: {cre.message}")
            return []
        except (ClientError, TimeoutError) as ce:
            log.error(f"Connection error while fetching multiple from {source_name}: {ce}")
            return []
        except Exception as e:
            log.exception(f"Unexpected error fetching multiple from {source_name}: {e}")
            return []
        return [source.parse_post(p) for p in posts if p]

    def build_embed(self, post_data: dict, index: int, total: int) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.random())
        embed.set_image(url=post_data["url"])
        embed.add_field(name="Rating", value=post_data["rating"])
        if "score" in post_data and post_data["score"] is not None:
            embed.add_field(name="Score", value=post_data["score"])
        footer_text = f"Post {index + 1}/{total}"
        if "id" in post_data:
            footer_text += f" • ID: {post_data['id']}"
        embed.set_footer(text=footer_text)
        return embed

    async def send_post_embed(self, ctx: commands.Context, post_data: dict, index: int, total: int) -> discord.Message:
        embed = self.build_embed(post_data, index, total)
        return await ctx.send(embed=embed)

    async def cleanup_reactions(self, message: discord.Message, controls: List[str]):
        for emoji in controls:
            try:
                await message.clear_reaction(emoji)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.group(invoke_without_command=True)
    async def booru(self, ctx: commands.Context, *, tag_string: str = ""):
        """Searches booru sites for images using the configured source order."""
        if await self.dm_access_denied(ctx):
            return
        is_nsfw = await self.get_nsfw_status(ctx)
        source_order = (await self.config.filters())["source_order"]
        if not source_order:
            await ctx.send("No sources configured.")
            return
        posts = []
        for source_name in source_order:
            try:
                posts = await self.get_multiple_posts(source_name, tag_string, is_nsfw, limit=100)
                if posts:
                    break
            except RequestError as e:
                log.error(f"Error with {source_name}: {e}")
                continue
        if not posts:
            await ctx.send("No results found in any source.")
            return
        current_index = 0
        message = await self.send_post_embed(ctx, posts[current_index], current_index, len(posts))
        if len(posts) == 1:
            return
        controls = ["◀️", "❌", "▶️"]
        for emoji in controls:
            await message.add_reaction(emoji)

        def check(reaction: discord.Reaction, user: discord.User):
            return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in controls

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            except TimeoutError:
                await self.cleanup_reactions(message, controls)
                break
            if str(reaction.emoji) == "◀️":
                current_index = (current_index - 1) % len(posts)
            elif str(reaction.emoji) == "▶️":
                current_index = (current_index + 1) % len(posts)
            elif str(reaction.emoji) == "❌":
                await self.cleanup_reactions(message, controls)
                break
            new_embed = self.build_embed(posts[current_index], current_index, len(posts))
            await message.edit(embed=new_embed)
            try:
                await message.remove_reaction(reaction.emoji, user)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.group(name="boorus")
    async def source_specific(self, ctx: commands.Context):
        """Commands to search a specific booru source."""
        if await self.dm_access_denied(ctx):
            return

    @source_specific.command(name="dan")
    async def danbooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        if await self.dm_access_denied(ctx):
            return
        is_nsfw = await self.get_nsfw_status(ctx)
        async with ctx.typing():
            post = await self.get_post("danbooru", tag_string, is_nsfw)
            if not post:
                await ctx.send("No results found on Danbooru.")
                return
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Danbooru • ID: {post['id']}")
            await ctx.send(embed=embed)

    @source_specific.command(name="gel")
    async def gelbooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        if await self.dm_access_denied(ctx):
            return
        is_nsfw = await self.get_nsfw_status(ctx)
        async with ctx.typing():
            post = await self.get_post("gelbooru", tag_string, is_nsfw)
            if not post:
                await ctx.send("No results found on Gelbooru.")
                return
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Gelbooru • ID: {post['id']}")
            await ctx.send(embed=embed)

    @source_specific.command(name="kon")
    async def konachan_search(self, ctx: commands.Context, *, tag_string: str = ""):
        if await self.dm_access_denied(ctx):
            return
        is_nsfw = await self.get_nsfw_status(ctx)
        async with ctx.typing():
            post = await self.get_post("konachan", tag_string, is_nsfw)
            if not post:
                await ctx.send("No results found on Konachan.")
                return
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Konachan • ID: {post['id']}")
            await ctx.send(embed=embed)

    @source_specific.command(name="yan")
    async def yandere_search(self, ctx: commands.Context, *, tag_string: str = ""):
        if await self.dm_access_denied(ctx):
            return
        is_nsfw = await self.get_nsfw_status(ctx)
        async with ctx.typing():
            post = await self.get_post("yandere", tag_string, is_nsfw)
            if not post:
                await ctx.send("No results found on Yande.re.")
                return
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Yande.re • ID: {post['id']}")
            await ctx.send(embed=embed)

    @source_specific.command(name="safe")
    async def safebooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        if await self.dm_access_denied(ctx):
            return
        async with ctx.typing():
            post = await self.get_post("safebooru", tag_string, is_nsfw=False)
            if not post:
                await ctx.send("No results found on Safebooru.")
                return
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Safebooru • ID: {post['id']}")
            await ctx.send(embed=embed)

    @commands.group(name="booruset")
    @checks.admin_or_permissions(administrator=True)
    async def settings(self, ctx: commands.Context):
        """Configure booru settings."""
        pass

    @settings.command(name="blacklist")
    async def add_blacklist(self, ctx: commands.Context, *, tag: str):
        async with self.config.filters.blacklist() as blacklist:
            if tag not in blacklist:
                blacklist.append(tag)
                await ctx.send(f"Added tag to blacklist: {tag}")
            else:
                await ctx.send("Tag already blacklisted.")

    @settings.command(name="unblacklist")
    async def remove_blacklist(self, ctx: commands.Context, *, tag: str):
        async with self.config.filters.blacklist() as blacklist:
            if tag in blacklist:
                blacklist.remove(tag)
                await ctx.send(f"Removed tag from blacklist: {tag}")
            else:
                await ctx.send("Tag not found in blacklist.")

    @settings.command(name="listblacklist")
    async def list_blacklist(self, ctx: commands.Context):
        blacklist = await self.config.filters.blacklist()
        if blacklist:
            await ctx.send("\n".join(blacklist))
        else:
            await ctx.send("No tags blacklisted.")

    @settings.command(name="setapi")
    @commands.is_owner()
    async def set_api_key(self, ctx: commands.Context, api_key: str, user_id: str):
        async with self.config.api_keys() as api_keys:
            api_keys["gelbooru"]["api_key"] = api_key
            api_keys["gelbooru"]["user_id"] = user_id
        await ctx.send("Gelbooru API credentials set.")
        await ctx.message.delete()
