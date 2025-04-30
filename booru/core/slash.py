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

    • /booru   – Searches all configured sources in order.
    • /boorus  – Searches a specific source.
    • /boorunsfw … (owner-only) – Manage DM-NSFW whitelist.
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
        for source_name in source_order:
            try:
                posts = await booru_cog._get_multiple_posts_from_source(source_name, query, is_nsfw, limit=100)
                if posts:
                    used_source = source_name
                    break
            except Exception as e:
                log.error("Error with %s: %s", source_name, e)

        if not posts:
            await self._send(ctx, "No results found in any source.")
            return

        embed = booru_cog._build_embed(posts[0], 0, len(posts))
        embed.set_footer(text=f"{embed.footer.text} • From {used_source.title()}")

        message = await self._send(ctx, embed=embed)

        if len(posts) > 1:
            view = BooruPaginationView(ctx.author, posts, used_source)
            view.message = message
            await message.edit(view=view)

    @commands.hybrid_command(
        name="boorus",
        description="Search a specific booru source.",
    )
    @app_commands.describe(
        source="Name of the source to search.",
        query="Tags or keywords to search for.",
    )
    async def boorus(self, ctx: commands.Context, source: str, *, query: str = ""):
        """Works in guilds and DMs."""
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
            await self._send(ctx, f"Invalid source: {source}. Available sources: {available}")
            return

        is_nsfw = await self._dm_nsfw_allowed(ctx, channel, booru_cog)

        post = await booru_cog._get_post_from_source(source, query, is_nsfw)
        if not post:
            await self._send(ctx, f"No results found on {source.title()}.")
            return

        embed = booru_cog._build_embed(post, 0, 1)
        embed.set_footer(text=f"{embed.footer.text} • From {source.title()}")
        await self._send(ctx, embed=embed)

    @commands.hybrid_group(
        name="boorunsfw",
        description="Manage DM-NSFW whitelist (owner-only).",
        invoke_without_command=True,
    )
    @commands.is_owner()
    async def boorunsfw(self, ctx: commands.Context):
        """Show help if no subcommand used."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @boorunsfw.command(name="list", description="List IDs allowed NSFW")
    @commands.is_owner()
    async def _bn_list(self, ctx: commands.Context):
        ids = await self.bot.get_cog("Booru").config.dm_nsfw_allowed()
        msg = "None." if not ids else "\n".join(map(str, ids))
        await ctx.send(f"**Allowed IDs:**\n{msg}")

    @boorunsfw.command(name="add", description="Add a user ID to whitelist.")
    @commands.is_owner()
    async def _bn_add(self, ctx: commands.Context, user: discord.User):
        conf = self.bot.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id in ids:
            await ctx.send(f"{user.mention} is already whitelisted.")
            return
        ids.add(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await ctx.send(f"Added {user.mention} (`{user.id}`) to whitelist.")

    @boorunsfw.command(name="remove", description="Remove a user from whitelist.")
    @commands.is_owner()
    async def _bn_remove(self, ctx: commands.Context, user: discord.User):
        conf = self.bot.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id not in ids:
            await ctx.send(f"{user.mention} is not on the whitelist.")
            return
        ids.remove(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await ctx.send(f"Removed {user.mention} from whitelist.")

    @boorunsfw.command(name="clear", description="Clear the entire whitelist.")
    @commands.is_owner()
    async def _bn_clear(self, ctx: commands.Context):
        await self.bot.get_cog("Booru").config.dm_nsfw_allowed.clear()
        await ctx.send("Whitelist cleared.")

    async def _prepare_ctx(self, ctx: commands.Context) -> Optional[discord.abc.MessageableChannel]:
        """Handle defer/typing and return the channel, or None on early exit."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
            return ctx.interaction.channel
        else:
            await ctx.typing()
            return ctx.channel

    async def _send(self, ctx: commands.Context, content: str = None, *, embed: discord.Embed = None):
        """Send a reply respecting prefix/slash context, and return the message."""
        if ctx.interaction:
            return await ctx.interaction.followup.send(content=content, embed=embed)
        return await ctx.send(content=content, embed=embed)

    async def _dm_nsfw_allowed(
        self,
        ctx: commands.Context,
        channel: discord.abc.MessageableChannel,
        booru_cog,
    ) -> bool:
        """Guilds respect channel.is_nsfw(); DMs allow only owners/whitelist."""
        if isinstance(channel, discord.TextChannel):
            return channel.is_nsfw()
        is_owner = await self.bot.is_owner(ctx.author)
        allowed_ids: List[int] = await booru_cog.config.dm_nsfw_allowed()
        return is_owner or ctx.author.id in allowed_ids


class BooruPaginationView(discord.ui.View):
    """Next / Previous navigation for multi-result searches."""

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
    async def _btn_prev(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_index = (self.current_index - 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, emoji="▶️")
    async def _btn_next(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.current_index = (self.current_index + 1) % len(self.posts)
        await self._update(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="❌")
    async def _btn_close(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.message.edit(view=None)
        self.stop()

    async def _update(self, interaction: discord.Interaction):
        post = self.posts[self.current_index]
        booru_cog = interaction.client.get_cog("Booru")
        embed = booru_cog._build_embed(post, self.current_index, len(self.posts))
        embed.set_footer(text=f"{embed.footer.text} • From {self.source.title()}")
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass
