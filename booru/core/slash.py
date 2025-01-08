import logging
from typing import List, Optional

import discord
from discord import app_commands
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru.slash")


class BooruSlash(commands.Cog):
    """Slash command implementation of booru search commands"""

    def __init__(self, bot):
        self.bot = bot
        self.tag_handler = TagHandler()
        super().__init__()

        # Add application commands
        self.booru_app = app_commands.Command(
            name="booru",
            description="Search booru sites for images using the configured source order",
            callback=self.booru,
        )
        self.boorus_app = app_commands.Command(
            name="boorus",
            description="Search a specific booru source",
            callback=self.boorus,
        )
        bot.tree.add_command(self.booru_app)
        bot.tree.add_command(self.boorus_app)

    def cog_unload(self):
        """Clean up when cog is unloaded"""
        self.bot.tree.remove_command("booru")
        self.bot.tree.remove_command("boorus")

    @app_commands.guild_only()
    async def booru(self, interaction: discord.Interaction, query: str = ""):
        """Search booru sites for images using the configured source order"""
        is_nsfw = False
        if isinstance(interaction.channel, discord.TextChannel):
            is_nsfw = interaction.channel.is_nsfw()

        await interaction.response.defer()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru cog is not loaded.")
            return

        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await interaction.followup.send("No sources configured.")
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
            await interaction.followup.send("No results found in any source.")
            return

        current_index = 0
        embed = booru_cog._build_embed(posts[current_index], current_index, len(posts))
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {used_source.title()}")

        message = await interaction.followup.send(embed=embed)
        if len(posts) > 1:
            view = BooruPaginationView(interaction.user, posts, used_source)
            await message.edit(view=view)

    @app_commands.guild_only()
    async def boorus(
        self, interaction: discord.Interaction, source: str, query: str = ""
    ):
        """Search a specific booru source"""
        is_nsfw = False
        if isinstance(interaction.channel, discord.TextChannel):
            is_nsfw = interaction.channel.is_nsfw()

        await interaction.response.defer()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru cog is not loaded.")
            return

        source = source.lower()
        if source not in booru_cog.sources:
            await interaction.followup.send(
                f"Invalid source: {source}. Available sources: {', '.join(booru_cog.sources.keys())}"
            )
            return

        post = await booru_cog._get_post_from_source(source, query, is_nsfw)
        if not post:
            await interaction.followup.send(f"No results found on {source.title()}")
            return

        embed = booru_cog._build_embed(post, 0, 1)
        footer_text = embed.footer.text
        embed.set_footer(text=f"{footer_text} • From {source.title()}")

        await interaction.followup.send(embed=embed)


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
