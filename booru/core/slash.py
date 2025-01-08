import logging
from typing import List, Optional

import discord
from discord import app_commands
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru.slash")


class BooruSlash(commands.Cog):
    """
    Hybrid commands for booru searches.

    This cog contains two primary commands:
      1) booru  - Searches all configured booru sources in order.
      2) boorus - Searches a specific booru source.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tag_handler = TagHandler()

    def cog_unload(self):
        """
        Called automatically when the cog is unloaded.
        Red can safely handle cleanup of hybrid commands without manual removal.
        """
        pass

    @commands.hybrid_command(
        name="booru", description="Search booru sites with the configured source order."
    )
    @app_commands.describe(query="Tags or keywords to search for.")
    @commands.guild_only()
    @app_commands.guild_only()
    async def booru(self, ctx: commands.Context, *, query: str = ""):
        """
        Searches configured booru sources in the order set by the Booru cog.
        Works as both a text command and a slash command.
        """

        if ctx.interaction:
            await ctx.interaction.response.defer()
            channel = ctx.interaction.channel
        else:
            await ctx.typing()
            channel = ctx.channel

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            (
                await ctx.send("Booru cog is not loaded.")
                if not ctx.interaction
                else await ctx.interaction.followup.send("Booru cog is not loaded.")
            )
            return

        is_nsfw = isinstance(channel, discord.TextChannel) and channel.is_nsfw()

        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            response = "No sources configured."
            if ctx.interaction:
                await ctx.interaction.followup.send(response)
            else:
                await ctx.send(response)
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
            response = "No results found in any source."
            if ctx.interaction:
                await ctx.interaction.followup.send(response)
            else:
                await ctx.send(response)
            return

        current_index = 0
        embed = booru_cog._build_embed(posts[current_index], current_index, len(posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {used_source.title()}")

        if ctx.interaction:
            message = await ctx.interaction.followup.send(embed=embed)
        else:
            message = await ctx.send(embed=embed)

        if len(posts) > 1:
            view = BooruPaginationView(ctx.author, posts, used_source)
            view.message = message
            await message.edit(view=view)

    @commands.hybrid_command(
        name="boorus", description="Search a specific booru source."
    )
    @app_commands.describe(
        source="Name of the source to search.", query="Tags or keywords to search for."
    )
    @commands.guild_only()
    @app_commands.guild_only()
    async def boorus(self, ctx: commands.Context, source: str, *, query: str = ""):
        """
        Searches a specific booru source by name. Works as both a text command and a slash command.
        """

        if ctx.interaction:
            await ctx.interaction.response.defer()
            channel = ctx.interaction.channel
        else:
            await ctx.typing()
            channel = ctx.channel

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            response = "Booru cog is not loaded."
            if ctx.interaction:
                await ctx.interaction.followup.send(response)
            else:
                await ctx.send(response)
            return

        source = source.lower()
        if source not in booru_cog.sources:
            available = ", ".join(booru_cog.sources.keys())
            response = f"Invalid source: {source}. Available sources: {available}"
            if ctx.interaction:
                await ctx.interaction.followup.send(response)
            else:
                await ctx.send(response)
            return

        is_nsfw = isinstance(channel, discord.TextChannel) and channel.is_nsfw()

        post = await booru_cog._get_post_from_source(source, query, is_nsfw)
        if not post:
            response = f"No results found on {source.title()}."
            if ctx.interaction:
                await ctx.interaction.followup.send(response)
            else:
                await ctx.send(response)
            return

        embed = booru_cog._build_embed(post, 0, 1)
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {source.title()}")

        if ctx.interaction:
            await ctx.interaction.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)


class BooruPaginationView(discord.ui.View):
    """
    View for handling next/previous image navigation among booru results.
    """

    def __init__(self, author: discord.User, posts: List[dict], source: str):
        super().__init__(timeout=60)
        self.author = author
        self.posts = posts
        self.current_index = 0
        self.source = source
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Ensure only the command author can use the navigation buttons.
        """
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Show the previous image in the results.
        """
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Show the next image in the results.
        """
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Remove the pagination view and stop the interaction.
        """
        await interaction.message.edit(view=None)
        self.stop()

    async def update_message(self, interaction: discord.Interaction):
        """
        Update the embed to reflect the new current index.
        """
        post = self.posts[self.current_index]
        booru_cog = interaction.client.get_cog("Booru")
        embed = booru_cog._build_embed(post, self.current_index, len(self.posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {self.source.title()}")

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """
        When the view times out, remove all buttons.
        """
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass
