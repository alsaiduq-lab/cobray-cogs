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

        # Initialize the slash command group
        self.booru_group = app_commands.Group(
            name="booru", description="Search booru sites for images", guild_only=True
        )

    def cog_unload(self):
        """Cleanup when cog is unloaded"""
        self.booru_group.remove_command("search")

    @app_commands.command(name="search")
    @app_commands.guild_only()
    async def booru_search(
        self, interaction: discord.Interaction, tags: str, source: Optional[str] = None
    ):
        """
        Search booru sites for images

        Parameters
        ----------
        tags: The tags to search for
        source: Optional specific source to search (danbooru, gelbooru, etc)
        """
        await interaction.response.defer()

        is_nsfw = False
        if isinstance(interaction.channel, discord.TextChannel):
            is_nsfw = interaction.channel.is_nsfw()

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru cog is not loaded.")
            return

        # Process tags
        positive_tags, negative_tags = self.tag_handler.parse_tags(tags)
        if not is_nsfw:
            negative_tags.add("rating:explicit")
            negative_tags.add("rating:questionable")

        combined_tags = self.tag_handler.combine_tags(positive_tags, negative_tags)

        # Handle specific source search
        if source:
            source = source.lower()
            if source not in booru_cog.sources:
                await interaction.followup.send(f"Invalid source: {source}")
                return

            post = await booru_cog._get_post_from_source(source, tags, is_nsfw)
            if not post:
                await interaction.followup.send(f"No results found on {source.title()}")
                return

            embed = discord.Embed(color=discord.Color.random())
            embed.set_image(url=post["url"])
            embed.add_field(name="Rating", value=post["rating"])
            if post.get("score") is not None:
                embed.add_field(name="Score", value=post["score"])
            embed.set_footer(text=f"From {source.title()} • ID: {post['id']}")

            await interaction.followup.send(embed=embed)
            return

        # Search all sources in order
        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await interaction.followup.send("No sources configured.")
            return

        posts = []
        used_source = None

        for source_name in source_order:
            try:
                posts = await booru_cog._get_multiple_posts_from_source(
                    source_name, tags, is_nsfw, limit=100
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
        embed = discord.Embed(color=discord.Color.random())
        post = self.posts[self.current_index]

        embed.set_image(url=post["url"])
        embed.add_field(name="Rating", value=post["rating"])
        if post.get("score") is not None:
            embed.add_field(name="Score", value=post["score"])

        footer_text = f"Post {self.current_index+1}/{len(self.posts)}"
        if post.get("id"):
            footer_text += f" • ID: {post['id']}"
        footer_text += f" • From {self.source.title()}"
        embed.set_footer(text=footer_text)

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Remove buttons when the view times out"""
        try:
            await self.message.edit(view=None)
        except (discord.NotFound, discord.HTTPException):
            pass
