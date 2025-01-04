import logging
import discord
import aiohttp
import random
from typing import Optional, Dict, Any, List
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from aiohttp import ClientError, ClientResponseError
from asyncio import TimeoutError

from .core.tags import TagHandler
from .core.exceptions import RequestError, SourceNotFound
from .sources import (
    DanbooruSource,
    GelbooruSource,
    KonachanSource,
    SafebooruSource,
    YandereSource,
    Rule34Source
)

log = logging.getLogger("red.booru")


class Booru(commands.Cog):
    """Search booru sites for anime art."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        
        self.config = Config.get_conf(
            self,
            identifier=127318273,
            force_registration=True
        )
        self.tag_handler = TagHandler()
        
        self.sources = {
            "danbooru": DanbooruSource(self.session),
            "gelbooru": GelbooruSource(self.session),
            "konachan": KonachanSource(self.session),
            "yandere": YandereSource(self.session),
            "safebooru": SafebooruSource(self.session),
            "rule34": Rule34Source(self.session)
        }
        
        default_global = {
            "api_keys": {
                "gelbooru": {
                    "api_key": None,
                    "user_id": None
                }
            },
            "filters": {
                "blacklist": [],
                "source_order": [
                    "danbooru",
                    "gelbooru",
                    "konachan",
                    "yandere",
                    "safebooru",
                    "rule34"
                ]
            }
        }
        
        self.config.register_global(**default_global)
        
    def cog_unload(self):
        """Cleanup when the cog is unloaded."""
        self.bot.loop.create_task(self.session.close())
    
    async def _get_post_from_source(
        self, 
        source_name: str, 
        tag_string: str, 
        is_nsfw: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Attempts to get a single post from the specified source.
        Returns None if no valid post is found or if an error occurs.
        """
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
            if cre.status == 422:
                log.error(
                    f"[{source_name}] HTTP {cre.status} - Possibly invalid or too many tags: {cre.message}"
                )
            else:
                log.error(f"[{source_name}] HTTP {cre.status} error: {cre.message}")
            return None
        
        except (ClientError, TimeoutError) as ce:
            log.error(f"Connection error while fetching from {source_name}: {ce}")
            return None
        
        except Exception as e:
            log.exception(f"Unexpected error fetching from {source_name}: {e}")
            return None


    async def _get_multiple_posts_from_source(
        self,
        source_name: str,
        tag_string: str,
        is_nsfw: bool,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Fetches up to `limit` posts from the specified source. Returns
        a list of parsed post dicts, or an empty list on failure.
        """
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

    def _build_embed(self, post_data: dict, index: int, total: int) -> discord.Embed:
        """
        Builds a new embed given post data and the index/total for pagination.
        """
        embed = discord.Embed(color=discord.Color.random())
        embed.set_image(url=post_data["url"])
        embed.add_field(name="Rating", value=post_data["rating"])
        
        if "score" in post_data and post_data["score"] is not None:
            embed.add_field(name="Score", value=post_data["score"])
        
        footer_text = f"Post {index+1}/{total}"
        if "id" in post_data:
            footer_text += f" • ID: {post_data['id']}"
        embed.set_footer(text=footer_text)
        
        return embed
    
    async def _send_post_embed(self, ctx: commands.Context, post_data: dict, index: int, total: int) -> discord.Message:
        """
        Sends an embed for the given post data, returning the sent message object.
        """
        embed = self._build_embed(post_data, index, total)
        return await ctx.send(embed=embed)
    
    async def _cleanup_reactions(self, message: discord.Message, controls: List[str]):
        """
        Removes reaction controls if possible. Permission errors are ignored.
        """
        for emoji in controls:
            try:
                await message.clear_reaction(emoji)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.group(invoke_without_command=True)
    async def booru(self, ctx: commands.Context, *, tag_string: str = ""):
        """
        Searches booru sites for images using the configured source order.
        If the channel is marked NSFW, explicit results may appear.
        """
        is_nsfw = (
            ctx.channel.is_nsfw() 
            if isinstance(ctx.channel, discord.TextChannel) 
            else False
        )

        source_order = (await self.config.filters())["source_order"]
        if not source_order:
            await ctx.send("No sources configured.")
            return

        # Try each source until we get posts
        posts = []
        used_source = None
        
        for source_name in source_order:
            try:
                posts = await self._get_multiple_posts_from_source(
                    source_name, tag_string, is_nsfw, limit=100
                )
                if posts:
                    used_source = source_name
                    break
            except RequestError as e:
                log.error(f"Error with {source_name}: {e}")
                continue

        if not posts:
            await ctx.send("No results found in any source.")
            return
        
        current_index = 0
        message = await self._send_post_embed(ctx, posts[current_index], current_index, len(posts))

        # If there's only one post, no need to paginate
        if len(posts) == 1:
            return
        
        controls = ["◀️", "❌", "▶️"]
        for emoji in controls:
            await message.add_reaction(emoji)

        def check(reaction: discord.Reaction, user: discord.Member):
            return (
                user == ctx.author
                and reaction.message.id == message.id
                and str(reaction.emoji) in controls
            )
        
        while True:
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add",
                    timeout=60.0,
                    check=check
                )
            except TimeoutError:
                await self._cleanup_reactions(message, controls)
                break
            
            if str(reaction.emoji) == "◀️":
                current_index = (current_index - 1) % len(posts)
            elif str(reaction.emoji) == "▶️":
                current_index = (current_index + 1) % len(posts)
            elif str(reaction.emoji) == "❌":
                await self._cleanup_reactions(message, controls)
                break
            
            new_embed = self._build_embed(posts[current_index], current_index, len(posts))
            await message.edit(embed=new_embed)

            try:
                await message.remove_reaction(reaction.emoji, user)
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass
    
    @commands.group(name="boorus")
    async def source_specific(self, ctx: commands.Context):
        """
        Commands to search a specific booru source.
        Example usage: [p]boorus dan artoria_pendragon
        """
        pass
    
    @source_specific.command(name="dan")
    async def danbooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Danbooru specifically."""
        async with ctx.typing():
            post = await self._get_post_from_source(
                "danbooru",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
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
        """Search Gelbooru specifically."""
        async with ctx.typing():
            post = await self._get_post_from_source(
                "gelbooru",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
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
        """Search Konachan specifically."""
        async with ctx.typing():
            post = await self._get_post_from_source(
                "konachan",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
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
        """Search Yande.re specifically."""
        async with ctx.typing():
            post = await self._get_post_from_source(
                "yandere",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
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
        """Search Safebooru specifically."""
        async with ctx.typing():
            post = await self._get_post_from_source(
                "safebooru",
                tag_string,
                is_nsfw=False
            )
            
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
        """Add a tag to the blacklist."""
        async with self.config.filters.blacklist() as blacklist:
            if tag not in blacklist:
                blacklist.append(tag)
                await ctx.send(f"Added tag to blacklist: {tag}")
            else:
                await ctx.send("Tag already blacklisted.")
    
    @settings.command(name="unblacklist")
    async def remove_blacklist(self, ctx: commands.Context, *, tag: str):
        """Remove a tag from the blacklist."""
        async with self.config.filters.blacklist() as blacklist:
            if tag in blacklist:
                blacklist.remove(tag)
                await ctx.send(f"Removed tag from blacklist: {tag}")
            else:
                await ctx.send("Tag not found in blacklist.")
    
    @settings.command(name="listblacklist")
    async def list_blacklist(self, ctx: commands.Context):
        """List all blacklisted tags."""
        blacklist = await self.config.filters.blacklist()
        if blacklist:
            await ctx.send("\n".join(blacklist))
        else:
            await ctx.send("No tags blacklisted.")
    
    @settings.command(name="setapi")
    @commands.is_owner()
    async def set_api_key(self, ctx: commands.Context, api_key: str, user_id: str):
        """Set Gelbooru API credentials."""
        async with self.config.api_keys() as api_keys:
            api_keys["gelbooru"]["api_key"] = api_key
            api_keys["gelbooru"]["user_id"] = user_id
        
        await ctx.send("Gelbooru API credentials set.")
        await ctx.message.delete()
