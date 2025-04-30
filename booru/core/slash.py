# core/slash.py – SLASH-ONLY helper for the Booru cog

import logging
from typing import List, Optional

import discord
from discord import app_commands
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru.slash")


class BooruSlash(commands.Cog):
    """
    Slash-only commands for booru searches.

    • /booru       – search all configured sources
    • /boorus      – search a specific source
    • /boorunsfw   – owner-only DM-NSFW whitelist
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tag_handler = TagHandler()

    @app_commands.command(
        name="booru",
        description="Search booru sites with the configured source order.",
        dm_permission=True,
    )
    @app_commands.describe(query="Tags or keywords to search for.")
    async def slash_booru(self, interaction: discord.Interaction, query: str = ""):
        await interaction.response.defer()
        channel = interaction.channel

        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru cog is not loaded.")
            return

        is_nsfw = await self._dm_nsfw_allowed(interaction, channel, booru_cog)
        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await interaction.followup.send("No sources configured.")
            return

        posts: List[dict] = []
        used_source: Optional[str] = None
        for src in source_order:
            try:
                posts = await booru_cog._get_multiple_posts_from_source(src, query, is_nsfw, limit=100)
                if posts:
                    used_source = src
                    break
            except Exception as e:
                log.error("Error with %s: %s", src, e)

        if not posts:
            await interaction.followup.send("No results found in any source.")
            return

        footer = booru_cog._build_embed(posts[0], 0, len(posts)).footer.text or ""
        source_name = (used_source or "Unknown").title()
        embed = booru_cog._build_embed(posts[0], 0, len(posts))
        embed.set_footer(text=f"{footer} • From {source_name}")

        msg = await interaction.followup.send(embed=embed)

        if len(posts) > 1:
            view = BooruPaginationView(interaction.user, posts, source_name)
            view.message = msg
            await msg.edit(view=view)

    @app_commands.command(
        name="boorus",
        description="Search a specific booru source.",
        dm_permission=True,
    )
    @app_commands.describe(
        source="Name of the source to search.",
        query="Tags or keywords to search for.",
    )
    async def slash_boorus(self, interaction: discord.Interaction, source: str, query: str = ""):
        await interaction.response.defer()
        channel = interaction.channel

        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru cog is not loaded.")
            return

        source = source.lower()
        if source not in booru_cog.sources:
            available = ", ".join(booru_cog.sources.keys())
            await interaction.followup.send(f"Invalid source: {source}. Available: {available}")
            return

        is_nsfw = await self._dm_nsfw_allowed(interaction, channel, booru_cog)
        post = await booru_cog._get_post_from_source(source, query, is_nsfw)
        if not post:
            await interaction.followup.send(f"No results found on {source.title()}.")
            return

        footer = booru_cog._build_embed(post, 0, 1).footer.text or ""
        embed = booru_cog._build_embed(post, 0, 1)
        embed.set_footer(text=f"{footer} • From {source.title()}")
        await interaction.followup.send(embed=embed)

    boorunsfw = app_commands.Group(
        name="boorunsfw",
        description="Manage DM-NSFW whitelist (owner only).",
        guild_only=False,
        dm_permission=True,
    )

    @boorunsfw.command(name="list", description="Show whitelist")
    async def _bn_list(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        ids = await interaction.client.get_cog("Booru").config.dm_nsfw_allowed()
        msg = "None." if not ids else "\n".join(map(str, ids))
        await interaction.response.send_message(f"**Allowed IDs:**\n{msg}", ephemeral=True)

    @boorunsfw.command(name="add", description="Add user")
    @app_commands.describe(user="User to allow NSFW in DMs")
    async def _bn_add(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        conf = interaction.client.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id in ids:
            await interaction.response.send_message("Already whitelisted.", ephemeral=True)
            return
        ids.add(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message(f"Added {user.mention}.", ephemeral=True)

    @boorunsfw.command(name="remove", description="Remove user")
    @app_commands.describe(user="User to remove")
    async def _bn_remove(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        conf = interaction.client.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id not in ids:
            await interaction.response.send_message("Not on whitelist.", ephemeral=True)
            return
        ids.remove(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message(f"Removed {user.mention}.", ephemeral=True)

    @boorunsfw.command(name="clear", description="Clear whitelist")
    async def _bn_clear(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        await interaction.client.get_cog("Booru").config.dm_nsfw_allowed.clear()
        await interaction.response.send_message("Whitelist cleared.", ephemeral=True)

    async def _dm_nsfw_allowed(
        self,
        interaction: discord.Interaction,
        channel: discord.abc.Messageable,
        booru_cog,
    ) -> bool:
        if isinstance(channel, discord.TextChannel):
            return channel.is_nsfw()
        if await interaction.client.is_owner(interaction.user):
            return True
        allowed: List[int] = await booru_cog.config.dm_nsfw_allowed()
        return interaction.user.id in allowed


class BooruPaginationView(discord.ui.View):
    """Embed pagination."""

    def __init__(self, author: discord.User, posts: List[dict], source: str):
        super().__init__(timeout=60)
        self.author = author
        self.posts = posts
        self.current_index = 0
        self.source = source
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def _prev(self, interaction: discord.Interaction, _):
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, _):
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def _close(self, interaction: discord.Interaction, _):
        await interaction.message.edit(view=None)
        self.stop()

    async def _update(self, interaction: discord.Interaction):
        post = self.posts[self.current_index]
        booru_cog = interaction.client.get_cog("Booru")
        embed = booru_cog._build_embed(post, self.current_index, len(self.posts))
        footer = embed.footer.text or ""
        embed.set_footer(text=f"{footer} • From {self.source.title()}")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass
