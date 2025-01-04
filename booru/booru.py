import logging
import discord
import aiohttp
from typing import Optional, Dict, Any, List
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

from .core import tags
from .core.exceptions import RequestError, SourceNotFound
from .sources import (
    DanbooruSource,
    GelbooruSource,
    KonachanSource,
    SafebooruSource,
    YandereSource
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
        
        # Initialize sources
        self.sources = {
            "danbooru": DanbooruSource(self.session),
            "gelbooru": GelbooruSource(self.session),
            "konachan": KonachanSource(self.session),
            "yandere": YandereSource(self.session),
            "safebooru": SafebooruSource(self.session)
        }
        
        # Default settings
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
                    "safebooru"
                ]
            }
        }
        
        self.config.register_global(**default_global)
        
    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.bot.loop.create_task(self.session.close())
            
    async def _get_post_from_source(
        self,
        source_name: str,
        tag_string: str,
        is_nsfw: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Get a post from a specific source."""
        try:
            source = self.sources.get(source_name)
            if not source:
                return None
                
            # Get credentials if needed
            credentials = None
            if source_name == "gelbooru":
                api_keys = (await self.config.api_keys())["gelbooru"]
                if api_keys["api_key"] and api_keys["user_id"]:
                    credentials = api_keys
                
            # Parse tags
            positive_tags, negative_tags = tags.parse_tags(tag_string)
            if not is_nsfw:
                negative_tags.add("rating:explicit")
                negative_tags.add("rating:questionable")
                
            # Get posts
            tag_list = tags.combine_tags(positive_tags, negative_tags)
            posts = await source.get_posts(tag_list, limit=1, credentials=credentials)
            
            if not posts:
                return None
                
            return source.parse_post(posts[0])
            
        except Exception as e:
            log.error(f"Error fetching from {source_name}: {e}")
            return None
            
    @commands.group(invoke_without_command=True)
    async def booru(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search booru sites for images.
        
        **Examples:**
        `{prefix}booru 1girl, solo`
        `{prefix}booru 1girl, -nsfw`
        """
        is_nsfw = ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
        
        async with ctx.typing():
            source_order = (await self.config.filters())["source_order"]
            
            for source_name in source_order:
                post = await self._get_post_from_source(source_name, tag_string, is_nsfw)
                if post:
                    embed = discord.Embed(color=discord.Color.random())
                    embed.set_image(url=post["url"])
                    embed.add_field(name="Rating", value=post["rating"])
                    if post.get("score") is not None:
                        embed.add_field(name="Score", value=post["score"])
                    embed.set_footer(text=f"From {source_name.title()} • ID: {post['id']}")
                    
                    await ctx.send(embed=embed)
                    return
                    
            await ctx.send("No results found in any source.")
            
    @commands.group(name="boorus")
    async def source_specific(self, ctx: commands.Context):
        """Commands for specific booru sources."""
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
        await ctx.message.delete()  # Delete to protect API credentials
