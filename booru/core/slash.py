import logging
from typing import List, Optional, Union, Set, cast

import discord
from discord import app_commands

try:
    from discord.app_commands import installs as app_installs
except ImportError:
    app_installs = None
from redbot.core import commands
from .tags import TagHandler

log = logging.getLogger("red.booru")


class BooruSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tag_handler = TagHandler()

        if app_installs is not None:
            try:
                for cmd in [self.booru, self.boorus]:
                    cmd.allowed_contexts = app_installs.AppCommandContext(
                        guild=True, dm_channel=True, private_channel=True
                    )
                    cmd.allowed_installs = app_installs.AppInstallationType(guild=True, user=True)
            except Exception as exc:
                import logging

                logging.getLogger("red.booru").exception(
                    "Failed to set allowed_contexts/installs for BooruSlash commands", exc_info=exc
                )

    async def is_dm_nsfw_allowed(self, user: discord.User) -> bool:
        """Checks if a user is allowed to use NSFW commands in DMs."""
        if await self.bot.is_owner(user):
            return True
        booru_cog = self.bot.get_cog("Booru")
        if booru_cog is None:
            log.warning("Booru core cog not found for DM NSFW check.")
            return False
        allowed_user_ids: Union[List[int], Set[int]] = await booru_cog.config.dm_nsfw_allowed()
        if not isinstance(allowed_user_ids, (list, set)):
            log.error(f"Expected list or set for dm_nsfw_allowed, got {type(allowed_user_ids)}")
            return False
        if any(not isinstance(id, int) for id in allowed_user_ids):
            log.error(f"Non-integer ID found in dm_nsfw_allowed: {allowed_user_ids}")
            return False
        return user.id in allowed_user_ids

    async def access_denied(self, interaction: discord.Interaction) -> bool:
        """
        Returns True and sends a message if user is in a DM-like context
        and not allowed to use the command.
        """
        if interaction.guild is None:
            allowed = await self.is_dm_nsfw_allowed(interaction.user)
            if not allowed:
                await interaction.response.send_message(
                    "You are not permitted to use this command in DMs or private channels.", ephemeral=True
                )
                return True
        return False

    async def get_nsfw_status(self, interaction: discord.Interaction) -> bool:
        """Determines if the current context is considered NSFW."""
        channel = interaction.channel

        if interaction.guild is None:
            return await self.is_dm_nsfw_allowed(interaction.user)
        if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)):
            return channel.is_nsfw()
        if hasattr(channel, "is_nsfw") and callable(channel.is_nsfw):
            try:
                return cast(bool, channel.is_nsfw())
            except Exception as e:
                log.error(f"Error calling is_nsfw on channel type {type(channel)}: {e}", exc_info=True)

        log.warning(
            f"Could not determine NSFW status for channel ID {channel.id} of type {type(channel)}. "
            "Defaulting to SFW (False)."
        )
        return False

    @app_commands.command(
        name="booru",
        description="Search all configured booru sources.",
    )
    @app_commands.describe(tags="Tags or keywords to search for.")
    async def booru(self, interaction: discord.Interaction, tags: str = ""):
        if await self.access_denied(interaction):
            return
        await self.search(interaction, tags)

    @app_commands.command(
        name="boorus",
        description="Search a specific booru site.",
    )
    @app_commands.describe(
        site="danbooru | gelbooru | konachan | yandere | safebooru | rule34",
        tags="Tags or keywords",
    )
    async def boorus(self, interaction: discord.Interaction, site: str, tags: str = ""):
        if await self.access_denied(interaction):
            return
        await self.search(interaction, tags, site.lower())

    async def search(
        self,
        interaction: discord.Interaction,
        query: str,
        specific_site: Optional[str] = None,
    ):
        ephemeral_response = False
        await interaction.response.defer(ephemeral=ephemeral_response)
        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.followup.send(
                "Booru core cog not loaded. Please try again later.", ephemeral=ephemeral_response
            )
            return

        is_nsfw_context = await self.get_nsfw_status(interaction)
        if specific_site:
            sources = [specific_site]
        else:
            try:
                filters_config = await booru_cog.config.filters()
                sources = filters_config.get("source_order", [])
                if not sources:
                    log.warning("No source_order found in Booru cog config, or it's empty.")
                    sources = list(booru_cog.sources.keys())
            except Exception as e:
                log.error(f"Error retrieving source_order from config: {e}", exc_info=True)
                await interaction.followup.send("Error accessing booru configuration.", ephemeral=ephemeral_response)
                return

        posts: List[dict] = []
        used_source = None
        for src in sources:
            if src not in booru_cog.sources:
                log.debug(f"Source '{src}' not available in Booru cog sources.")
                continue
            try:
                posts = await booru_cog.get_multiple_posts(src, query, is_nsfw_context, limit=100)
                if posts:
                    used_source = src
                    break
            except Exception as e:
                log.error("Error searching source %s for query '%s': %s", src, query, e, exc_info=True)
        if not posts:
            await interaction.followup.send("No results found for your query.", ephemeral=ephemeral_response)
            return
        is_dm = interaction.guild is None
        rating = posts[0].get("rating", "safe").lower()
        nsfw = rating in ("explicit", "questionable")
        embed = booru_cog.build_embed(posts[0], 0, len(posts))
        foot = embed.footer.text or ""
        embed.set_footer(text=f"{foot} • From {used_source.title() if used_source else 'Unknown Source'}")
        view = None
        message_kwargs = {"embed": embed, "view": None, "ephemeral": ephemeral_response}
        if is_dm and nsfw:
            spoiler_url = f"||{posts[0]['url']}||"
            warning = f"⚠️ NSFW Content: {spoiler_url}"
            message_kwargs = {"content": warning, "embed": embed, "view": None, "ephemeral": ephemeral_response}
        if len(posts) > 1:
            view = BooruPaginationView(
                interaction.user, posts, used_source.title() if used_source else "Unknown Source", is_dm=is_dm
            )
            message_kwargs["view"] = view
        msg = await interaction.followup.send(**message_kwargs)
        if view:
            view.message = msg

    booruset = app_commands.Group(
        name="booruset",
        description="Owner-only commands to manage DM NSFW whitelist.",
    )

    @booruset.command(name="list", description="List users whitelisted for DM NSFW.")
    async def wl_list(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("This command is restricted to the bot owner.", ephemeral=True)
            return
        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.response.send_message("Booru core cog not loaded.", ephemeral=True)
            return
        ids = await booru_cog.config.dm_nsfw_allowed()
        if not ids:
            await interaction.response.send_message("The DM NSFW whitelist is currently empty.", ephemeral=True)
        else:
            members_info = []
            for user_id in ids:
                user = interaction.client.get_user(user_id)
                if user:
                    members_info.append(f"- {user.mention} (`{user.name}`, ID: `{user.id}`)")
                else:
                    members_info.append(f"- Unknown User (ID: `{user_id}`)")
            message_content = "Users whitelisted for DM NSFW:\n" + "\n".join(members_info)
            if len(message_content) > 1900:
                await interaction.response.send_message(
                    "Whitelist is too long to display here.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(message_content, ephemeral=True)

    @booruset.command(name="add", description="Add a user to the DM NSFW whitelist.")
    @app_commands.describe(user="The user to add to the whitelist.")
    async def wl_add(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("This command is restricted to the bot owner.", ephemeral=True)
            return

        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.response.send_message("Booru core cog not loaded.", ephemeral=True)
            return
        conf = booru_cog.config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id in ids:
            await interaction.response.send_message(
                f"{user.mention} is already on the DM NSFW whitelist.", ephemeral=True
            )
            return
        ids.add(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message(
            f"{user.mention} has been added to the DM NSFW whitelist.", ephemeral=True
        )

    @booruset.command(name="remove", description="Remove a user from the DM NSFW whitelist.")
    @app_commands.describe(user="The user to remove from the whitelist.")
    async def wl_remove(self, interaction: discord.Interaction, user: discord.User):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("This command is restricted to the bot owner.", ephemeral=True)
            return

        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.response.send_message("Booru core cog not loaded.", ephemeral=True)
            return

        conf = booru_cog.config
        ids = set(await conf.dm_nsfw_allowed())
        if user.id not in ids:
            await interaction.response.send_message(f"{user.mention} is not on the DM NSFW whitelist.", ephemeral=True)
            return
        ids.remove(user.id)
        await conf.dm_nsfw_allowed.set(list(ids))
        await interaction.response.send_message(
            f"{user.mention} has been removed from the DM NSFW whitelist.", ephemeral=True
        )

    @booruset.command(name="clear", description="Clear the entire DM NSFW whitelist.")
    async def wl_clear(self, interaction: discord.Interaction):
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("This command is restricted to the bot owner.", ephemeral=True)
            return

        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.response.send_message("Booru core cog not loaded.", ephemeral=True)
            return
        await booru_cog.config.dm_nsfw_allowed.clear()
        await interaction.response.send_message("The DM NSFW whitelist has been cleared.", ephemeral=True)


class BooruPaginationView(discord.ui.View):
    def __init__(self, author: discord.User, posts: List[dict], source: str, is_dm: bool = False):
        super().__init__(timeout=60.0)
        self.author = author
        self.posts = posts
        self.idx = 0
        self.source = source
        self.is_dm = is_dm
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Tell the gooner to switch to the next page", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, custom_id="booru_prev")
    async def prev_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.idx = (self.idx - 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="booru_next")
    async def next_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.idx = (self.idx + 1) % len(self.posts)
        await self.update_message(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="booru_close")
    async def close_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            await interaction.delete_original_response()
        except Exception:
            if interaction.message:
                try:
                    await interaction.message.edit(view=None)
                except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                    try:
                        await interaction.message.delete()
                    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                        pass
        self.stop()

    async def update_message(self, interaction: discord.Interaction):
        current_post = self.posts[self.idx]
        booru_cog = interaction.client.get_cog("Booru")
        if not booru_cog:
            await interaction.response.send_message("Error: Booru cog not found during pagination.", ephemeral=True)
            return

        rating = current_post.get("rating", "safe").lower()
        nsfw = rating in ("explicit", "questionable")
        embed = booru_cog.build_embed(current_post, self.idx, len(self.posts))
        foot = embed.footer.text or ""
        embed.set_footer(text=f"{foot} • From {self.source}")
        message_kwargs = {"embed": embed, "view": self}
        if self.is_dm and nsfw:
            spoiler_url = f"||{current_post['url']}||"
            warning = f"⚠️ NSFW Content: {spoiler_url}"
            message_kwargs = {"content": warning, "embed": embed, "view": self}
        await interaction.response.edit_message(**message_kwargs)

    async def on_timeout(self):
        if self.message:
            try:
                if self.message.components:
                    await self.message.edit(view=None)
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                log.warning(f"Failed to remove view on timeout for message {self.message.id}: {e}")
        self.stop()
