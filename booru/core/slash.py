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

    • /booru   – all configured sources
    • /boorus  – one source
    • /boorunsfw … – owner whitelist for NSFW in DMs
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tag_handler = TagHandler()

    @commands.hybrid_command(
        name="booru",
        description="Search booru sites with the configured source order.",
    )
    @app_commands.describe(query="Tags or keywords to search for.")
    async def booru(self, ctx: commands.Context, *, query: str = ""):
        channel = await self._prepare_ctx(ctx)
        if channel is None:
            return

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await self._send(ctx, "Booru cog is not loaded.")
            return

        is_nsfw = await self._dm_nsfw_allowed(ctx, channel, booru_cog)

        source_order = (await booru_cog.config.filters())["source_order"]
        if not source_order:
            await self._send(ctx, "No sources configured.")
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
            await self._send(ctx, "No results found in any source.")
            return

        footer = booru_cog._build_embed(posts[0], 0, len(posts)).footer.text or ""
        source_name = (used_source or "Unknown").title()
        embed = booru_cog._build_embed(posts[0], 0, len(posts))
        embed.set_footer(text=f"{footer} • From {source_name}")

        msg = await self._send(ctx, embed=embed)

        if len(posts) > 1:
            view = BooruPaginationView(ctx.author, posts, source_name)
            view.message = msg
            await msg.edit(view=view)

    @commands.hybrid_command(
        name="boorus",
        description="Search a specific booru source.",
    )
    @app_commands.describe(
        source="Name of the source to search.",
        query="Tags or keywords to search for.",
    )
    async def boorus(self, ctx: commands.Context, source: str, *, query: str = ""):
        channel = await self._prepare_ctx(ctx)
        if channel is None:
            return

        booru_cog = self.bot.get_cog("Booru")
        if not booru_cog:
            await self._send(ctx, "Booru cog is not loaded.")
            return

        source = source.lower()
        if source not in booru_cog.sources:
            available = ", ".join(booru_cog.sources.keys())
            await self._send(ctx, f"Invalid source: {source}. Available: {available}")
            return

        is_nsfw = await self._dm_nsfw_allowed(ctx, channel, booru_cog)

        post = await booru_cog._get_post_from_source(source, query, is_nsfw)
        if not post:
            await self._send(ctx, f"No results found on {source.title()}.")
            return

        footer = booru_cog._build_embed(post, 0, 1).footer.text or ""
        embed = booru_cog._build_embed(post, 0, 1)
        embed.set_footer(text=f"{footer} • From {source.title()}")
        await self._send(ctx, embed=embed)

    @commands.hybrid_group(
        name="boorunsfw",
        description="Manage DM-NSFW whitelist (owner).",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def boorunsfw(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @boorunsfw.command(name="list", description="Show whitelist")
    @commands.is_owner()
    async def _bn_list(self, ctx: commands.Context):
        ids = await self.bot.get_cog("Booru").config.dm_nsfw_allowed()
        msg = "None." if not ids else "\n".join(map(str, ids))
        await ctx.send(f"**Allowed IDs:**\n{msg}")

    @boorunsfw.command(name="add", description="Add user")
    @commands.is_owner()
    async def _bn_add(self, ctx: commands.Context, user: discord.User):
        conf = self.bot.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id in ids:
            await ctx.send("Already whitelisted.")
            return
        ids.add(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await ctx.send(f"Added {user.mention} (`{user.id}`)")

    @boorunsfw.command(name="remove", description="Remove user")
    @commands.is_owner()
    async def _bn_remove(self, ctx: commands.Context, user: discord.User):
        conf = self.bot.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id not in ids:
            await ctx.send("Not on whitelist.")
            return
        ids.remove(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await ctx.send(f"Removed {user.mention}")

    @boorunsfw.command(name="clear", description="Clear whitelist")
    @commands.is_owner()
    async def _bn_clear(self, ctx: commands.Context):
        await self.bot.get_cog("Booru").config.dm_nsfw_allowed.clear()
        await ctx.send("Whitelist cleared.")

    async def _prepare_ctx(self, ctx: commands.Context) -> Optional[discord.abc.Messageable]:
        if ctx.interaction:
            await ctx.interaction.response.defer()
            return ctx.interaction.channel
        await ctx.typing()
        return ctx.channel

    async def _send(
        self, ctx: commands.Context, content: str | None = None, *, embed: discord.Embed | None = None
    ) -> discord.Message:
        if ctx.interaction:
            return await ctx.interaction.followup.send(content=content, embed=embed)
        return await ctx.send(content=content, embed=embed)

    async def _dm_nsfw_allowed(
        self,
        ctx: commands.Context,
        channel: discord.abc.Messageable,
        booru_cog,
    ) -> bool:
        if isinstance(channel, discord.TextChannel):
            return channel.is_nsfw()
        is_owner = await self.bot.is_owner(ctx.author)
        allowed: List[int] = await booru_cog.config.dm_nsfw_allowed()
        return is_owner or ctx.author.id in allowed


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

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, emoji="◀️")
    async def _prev(self, interaction: discord.Interaction, _):
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def _next(self, interaction: discord.Interaction, _):
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
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
