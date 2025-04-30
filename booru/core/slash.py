import logging
from typing import List, Optional

import discord
from discord import app_commands
from redbot.core import commands

from .tags import TagHandler

log = logging.getLogger("red.booru")


class BooruSlash(commands.GroupCog, name="booru"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.tag_handler = TagHandler()

    @app_commands.command(
        name="search",
        description="Search all configured booru sources.",
    )
    @app_commands.describe(tags="Tags / keywords to search for.")
    async def search(self, interaction: discord.Interaction, tags: str = ""):
        await self._do_search(interaction, tags)

    @app_commands.command(
        name="source",
        description="Search a specific booru site.",
    )
    @app_commands.describe(
        site="danbooru | gelbooru | konachan | yandere | safebooru | rule34",
        tags="Tags / keywords",
    )
    async def source(self, interaction: discord.Interaction, site: str, tags: str = ""):
        await self._do_search(interaction, tags, specific_site=site.lower())

    async def _do_search(
        self,
        interaction: discord.Interaction,
        query: str,
        specific_site: Optional[str] = None,
    ):
        await interaction.response.defer()
        channel = interaction.channel
        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send("Booru core cog not loaded.")
            return

        is_nsfw = await self._dm_nsfw_allowed(interaction, channel, booru_cog)

        if specific_site:
            srcs = [specific_site]
        else:
            srcs = (await booru_cog.config.filters())["source_order"]

        posts: List[dict] = []
        used_source = None
        for src in srcs:
            if src not in booru_cog.sources:
                continue
            try:
                posts = await booru_cog._get_multiple_posts_from_source(src, query, is_nsfw, limit=100)
                if posts:
                    used_source = src
                    break
            except Exception as e:
                log.error("Error with %s: %s", src, e)

        if not posts:
            await interaction.followup.send("No results.")
            return

        embed = booru_cog._build_embed(posts[0], 0, len(posts))
        footer = embed.footer.text or ""
        embed.set_footer(text=f"{footer} • From {used_source.title()}")
        msg = await interaction.followup.send(embed=embed)

        if len(posts) > 1:
            view = BooruPaginationView(interaction.user, posts, used_source.title())
            view.message = msg
            await msg.edit(view=view)

    boorunsfw = app_commands.Group(
        name="boorunsfw",
        description="Owner-only DM-NSFW whitelist.",
        guild_only=False,
    )

    @boorunsfw.command(name="list")
    async def wl_list(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        ids = await interaction.client.get_cog("Booru").config.dm_nsfw_allowed()
        txt = "None." if not ids else "\n".join(map(str, ids))
        await interaction.response.send_message(txt, ephemeral=True)

    @boorunsfw.command(name="add")
    @app_commands.describe(user="User to allow NSFW in DMs")
    async def wl_add(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        conf = interaction.client.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id in ids:
            await interaction.response.send_message("Already allowed.", ephemeral=True)
            return
        ids.add(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message("Added.", ephemeral=True)

    @boorunsfw.command(name="remove")
    @app_commands.describe(user="User to remove")
    async def wl_remove(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("Owner only.", ephemeral=True)
            return
        conf = interaction.client.get_cog("Booru").config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id not in ids:
            await interaction.response.send_message("Not on list.", ephemeral=True)
            return
        ids.remove(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message("Removed.", ephemeral=True)

    @boorunsfw.command(name="clear")
    async def wl_clear(self, interaction: discord.Interaction):
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
    ):
        if isinstance(channel, discord.TextChannel):
            return channel.is_nsfw()
        if await interaction.client.is_owner(interaction.user):
            return True
        ids: List[int] = await booru_cog.config.dm_nsfw_allowed()
        return interaction.user.id in ids


class BooruPaginationView(discord.ui.View):
    def __init__(self, author: discord.User, posts: List[dict], source: str):
        super().__init__(timeout=60)
        self.author = author
        self.posts = posts
        self.idx = 0
        self.source = source
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, i: discord.Interaction) -> bool:
        return i.user.id == self.author.id

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary)
    async def prev(self, i: discord.Interaction, _):
        self.idx = (self.idx - 1) % len(self.posts)
        await self._update(i)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next(self, i: discord.Interaction, _):
        self.idx = (self.idx + 1) % len(self.posts)
        await self._update(i)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, i: discord.Interaction, _):
        await i.message.edit(view=None)
        self.stop()

    async def _update(self, i: discord.Interaction):
        p = self.posts[self.idx]
        cog = i.client.get_cog("Booru")
        e = cog._build_embed(p, self.idx, len(self.posts))
        foot = e.footer.text or ""
        e.set_footer(text=f"{foot} • From {self.source}")
        await i.response.edit_message(embed=e, view=self)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.NotFound, discord.HTTPException):
                pass
