import logging
from typing import List, Optional

import discord
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru.slash")


class BooruSlash(commands.Cog):
    """Slash command implementation of booru search commands"""

    def __init__(self, bot):
        self.bot = bot
        self.tag_handler = TagHandler()
        super().__init__()

    @commands.hybrid_command(name="booru")
    @commands.guild_only()
    async def booru(self, ctx, *, query: str = ""):
        """Search booru sites for images using the configured source order"""
        is_nsfw = False
        if isinstance(ctx.channel, discord.TextChannel):
            is_nsfw = ctx.channel.is_nsfw()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await ctx.send("Booru cog is not loaded.")
            return

        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await ctx.send("No sources configured.")
            return

        posts = []
        used_source = None

        for source_name in source_order:
            try:
                posts = await booru_cog._get_multiple_posts_from_source(
                    source_name, query, is_nsfw, limit=100
                )
                if posts:
                    used_source = source_name
                    break
            except Exception as e:
                log.error(f"Error with {source_name}: {e}")
                continue

        if not posts:
            await ctx.send("No results found in any source.")
            return

        current_index = 0
        embed = booru_cog._build_embed(posts[current_index], current_index, len(posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {used_source.title()}")

        message = await ctx.send(embed=embed)
        if len(posts) > 1:
            view = BooruPaginationView(ctx.author, posts, used_source)
            await message.edit(view=view)

    @commands.hybrid_group(name="boorus")
    async def boorus(self, ctx):
        """Commands to search specific booru sources"""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    @boorus.command(name="dan")
    @commands.guild_only()
    async def danbooru_search(self, ctx, *, query: str = ""):
        """Search Danbooru specifically"""
        async with ctx.typing():
            is_nsfw = (
                ctx.channel.is_nsfw()
                if isinstance(ctx.channel, discord.TextChannel)
                else False
            )

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("danbooru", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Danbooru.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Danbooru")
            await ctx.send(embed=embed)

    @boorus.command(name="gel")
    @commands.guild_only()
    async def gelbooru_search(self, ctx, *, query: str = ""):
        """Search Gelbooru specifically"""
        async with ctx.typing():
            is_nsfw = (
                ctx.channel.is_nsfw()
                if isinstance(ctx.channel, discord.TextChannel)
                else False
            )

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("gelbooru", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Gelbooru.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Gelbooru")
            await ctx.send(embed=embed)

    @boorus.command(name="kon")
    @commands.guild_only()
    async def konachan_search(self, ctx, *, query: str = ""):
        """Search Konachan specifically"""
        async with ctx.typing():
            is_nsfw = (
                ctx.channel.is_nsfw()
                if isinstance(ctx.channel, discord.TextChannel)
                else False
            )

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("konachan", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Konachan.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Konachan")
            await ctx.send(embed=embed)

    @boorus.command(name="yan")
    @commands.guild_only()
    async def yandere_search(self, ctx, *, query: str = ""):
        """Search Yande.re specifically"""
        async with ctx.typing():
            is_nsfw = (
                ctx.channel.is_nsfw()
                if isinstance(ctx.channel, discord.TextChannel)
                else False
            )

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("yandere", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Yande.re.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Yande.re")
            await ctx.send(embed=embed)

    @boorus.command(name="safe")
    @commands.guild_only()
    async def safebooru_search(self, ctx, *, query: str = ""):
        """Search Safebooru specifically"""
        async with ctx.typing():
            is_nsfw = False  # Safebooru is always SFW

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("safebooru", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Safebooru.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Safebooru")
            await ctx.send(embed=embed)

    @boorus.command(name="r34")
    @commands.guild_only()
    async def r34_search(self, ctx, *, query: str = ""):
        """Search Rule34 specifically"""
        async with ctx.typing():
            is_nsfw = (
                ctx.channel.is_nsfw()
                if isinstance(ctx.channel, discord.TextChannel)
                else False
            )

            booru_cog = self.bot.get_cog("Booru")
            if not booru_cog:
                await ctx.send("Booru cog is not loaded.")
                return

            post = await booru_cog._get_post_from_source("rule34", query, is_nsfw)
            if not post:
                await ctx.send("No results found on Rule34.")
                return

            embed = booru_cog._build_embed(post, 0, 1)
            footer_text = embed.footer.text
            embed.set_footer(text=f"{footer_text} • From Rule34")
            await ctx.send(embed=embed)


class BooruPaginationView(discord.ui.View):
    """View for handling pagination of booru search results"""

    def __init__(self, author: discord.User, posts: List[dict], source: str):
        super().__init__(timeout=60)
        self.author = author
        self.posts = posts
        self.current_index = 0
        self.source = source

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the command author can use the buttons"""
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None)
        self.stop()

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the next/previous post"""
        post = self.posts[self.current_index]

        booru_cog = interaction.client.get_cog("Booru")
        embed = booru_cog._build_embed(post, self.current_index, len(self.posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {self.source.title()}")

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Remove buttons when the view times out"""
        try:
            await self.message.edit(view=None)
        except (discord.NotFound, discord.HTTPException):
            pass
