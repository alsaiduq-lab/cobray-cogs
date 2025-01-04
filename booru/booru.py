import logging
import discord
import aiohttp
import random
from typing import Optional, Dict, Any, List
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

from .core.tags import TagHandler
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
        self.tag_handler = TagHandler()
        self.sources = {
            "danbooru": DanbooruSource(self.session),
            "gelbooru": GelbooruSource(self.session),
            "konachan": KonachanSource(self.session),
            "yandere": YandereSource(self.session),
            "safebooru": SafebooruSource(self.session)
        }
        self.image_cache = {}
        
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
            
    async def _get_post_from_source(self, source_name: str, tag_string: str, is_nsfw: bool = False) -> Optional[Dict[str, Any]]:
        """Get a post from a specific source."""
        try:
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
            posts = await source.get_posts(tag_list, limit=10, credentials=credentials)
            
            if not posts:
                return None
                
            return [source.parse_post(post) for post in posts]
            
        except Exception as e:
            log.error(f"Error fetching from {source_name}: {e}")
            return None

    async def _handle_reactions(self, message, user_id, posts, current_index):
        def check(reaction, user):
            return user.id == user_id and str(reaction.emoji) in ["⬅️", "➡️"]

        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            
            if str(reaction.emoji) == "⬅️":
                current_index = (current_index - 1) % len(posts)
            elif str(reaction.emoji) == "➡️":
                current_index = (current_index + 1) % len(posts)
                
            await message.remove_reaction(reaction.emoji, user)
            return current_index
            
        except TimeoutError:
            return None
            
    @commands.group(invoke_without_command=True)
    async def booru(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search booru sites for images."""
        is_nsfw = ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
        
        async with ctx.typing():
            source_order = (await self.config.filters())["source_order"]
            
            all_posts = []
            for source_name in source_order:
                posts = await self._get_post_from_source(source_name, tag_string, is_nsfw)
                if posts:
                    all_posts.extend((post, source_name) for post in posts)
                    
            if not all_posts:
                await ctx.send("No results found in any source.")
                return
                
            current_index = 0
            post, source_name = all_posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From {source_name.title()} • ID: {post['id']} • Image {current_index + 1}/{len(all_posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, all_posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post, source_name = all_posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From {source_name.title()} • ID: {post['id']} • Image {current_index + 1}/{len(all_posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass

    @commands.group(name="boorus")
    async def source_specific(self, ctx: commands.Context):
        """Commands for specific booru sources."""
        pass
        
    @source_specific.command(name="dan")
    async def danbooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Danbooru specifically."""
        async with ctx.typing():
            posts = await self._get_post_from_source(
                "danbooru",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
            if not posts:
                await ctx.send("No results found on Danbooru.")
                return
                
            current_index = 0
            post = posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Danbooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post = posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From Danbooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass

    @source_specific.command(name="gel")
    async def gelbooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Gelbooru specifically."""
        async with ctx.typing():
            posts = await self._get_post_from_source(
                "gelbooru",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
            if not posts:
                await ctx.send("No results found on Gelbooru.")
                return
                
            current_index = 0
            post = posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Gelbooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post = posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From Gelbooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass

    @source_specific.command(name="kon")
    async def konachan_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Konachan specifically."""
        async with ctx.typing():
            posts = await self._get_post_from_source(
                "konachan",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
            if not posts:
                await ctx.send("No results found on Konachan.")
                return
                
            current_index = 0
            post = posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Konachan • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post = posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From Konachan • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass

    @source_specific.command(name="yan")
    async def yandere_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Yande.re specifically."""
        async with ctx.typing():
            posts = await self._get_post_from_source(
                "yandere",
                tag_string,
                ctx.channel.is_nsfw() if isinstance(ctx.channel, discord.TextChannel) else False
            )
            
            if not posts:
                await ctx.send("No results found on Yande.re.")
                return
                
            current_index = 0
            post = posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Yande.re • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post = posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From Yande.re • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass

    @source_specific.command(name="safe")
    async def safebooru_search(self, ctx: commands.Context, *, tag_string: str = ""):
        """Search Safebooru specifically."""
        async with ctx.typing():
            posts = await self._get_post_from_source(
                "safebooru",
                tag_string,
                is_nsfw=False
            )
            
            if not posts:
                await ctx.send("No results found on Safebooru.")
                return
                
            current_index = 0
            post = posts[current_index]
            
            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From Safebooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
            
            message = await ctx.send(embed=embed)
            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")
            
            while True:
                new_index = await self._handle_reactions(message, ctx.author.id, posts, current_index)
                if new_index is None:
                    break
                    
                current_index = new_index
                post = posts[current_index]
                
                embed = discord.Embed(color=discord.Color.random())
                embed.set_image(url=post["url"])
                embed.add_field(name="Rating", value=post["rating"])
                if post.get("score") is not None:
                    embed.add_field(name="Score", value=post["score"])
                embed.set_footer(text=f"From Safebooru • ID: {post['id']} • Image {current_index + 1}/{len(posts)}")
                
                await message.edit(embed=embed)

            try:
                await message.clear_reactions()
            except:
                pass
            
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
