import discord
from redbot.core import commands, Config
import logging
import asyncio
from typing import Optional

from .commands import (
    ArticleCommands, CardCommands, DeckCommands,
    EventCommands, MetaCommands, TournamentCommands
)
from .core.registry import CardRegistry
from .core.interactions import InteractionHandler
from .core.user_config import UserConfig
from .utils.parser import CardParser

log = logging.getLogger("red.dlm")

class DLM(commands.Cog):
    """DuelLinksMeta Information Cog"""

    def __init__(self, bot):
        self.bot = bot
        self.registry = CardRegistry()
        self.user_config = UserConfig(bot)
        self.interactions = InteractionHandler(bot, self.registry, self.user_config)
        self._load_commands()
        self._update_task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        log.info("DLM cog initialized")

    def _load_commands(self):
        """Initialize all command modules."""
        self.articles = ArticleCommands(self.bot, self.registry)
        self.cards = CardCommands(self.bot, self.registry)
        self.decks = DeckCommands(self.bot, self.registry)
        self.events = EventCommands(self.bot, self.registry)
        self.meta = MetaCommands(self.bot, self.registry)
        self.tournaments = TournamentCommands(self.bot, self.registry)

    async def cog_load(self) -> None:
        """Initialize cog dependencies."""
        try:
            await self.registry.initialize()
            await self.interactions.initialize()
            if self.bot.application_id:
                app_commands = self.interactions.get_commands()
                self.bot.tree.add_command(app_commands)
                log.info("Application commands registered")
            self._update_task = asyncio.create_task(self._update_loop())
            self._ready.set()
            log.info("DLM cog loaded successfully")
        except Exception as e:
            log.error(f"Error during cog load: {str(e)}", exc_info=True)
            raise

    async def cog_unload(self) -> None:
        """Clean up cog dependencies."""
        try:
            if self._update_task:
                self._update_task.cancel()
                try:
                    await self._update_task
                except asyncio.CancelledError:
                    pass
            await self.registry.close()
            await self.interactions.close()
            log.info("DLM cog unloaded successfully")
        except Exception as e:
            log.error(f"Error during cog unload: {str(e)}", exc_info=True)
            raise

    @commands.group(name="dlm")
    async def dlm(self, ctx):
        """DuelLinksMeta commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle card mentions in messages."""
        # Ignore bot messages
        if message.author.bot:
            return
        await self._ready.wait()
        if not message.guild or not await self.user_config.get_auto_search(message.guild.id):
            return
        card_names = CardParser.extract_card_names(message.content)
        if not card_names:
            return
        cards = []
        for name in card_names[:10]:
            if found := self.registry.get_card(name):
                cards.append(found[0])
        if not cards:
            return
        format = await self.user_config.get_user_format(message.author.id)
        embeds = []
        for card in cards:
            try:
                embed = await self.interactions.builder.build_card_embed(card, format)
                embeds.append(embed)
            except Exception as e:
                log.error(f"Error building embed: {str(e)}", exc_info=True)
        if embeds:
            try:
                await message.reply(embeds=embeds)
            except Exception as e:
                log.error(f"Error sending card embeds: {str(e)}", exc_info=True)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Global error handler for the cog."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.1f}s")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param.name}")
        else:
            log.error(f"Command error: {str(error)}", exc_info=True)
            await ctx.send("An error occurred while processing your command.")

    async def _update_loop(self):
        """Background task to update card data."""
        try:
            while True:
                try:
                    await self.registry.update_registry()
                except Exception as e:
                    log.error(f"Error updating registry: {str(e)}", exc_info=True)
                await asyncio.sleep(7200)
        except asyncio.CancelledError:
            log.info("Update loop cancelled")
            raise
