import logging
import asyncio
from typing import Optional, List

import discord
from discord import app_commands
from redbot.core import commands, Config

from .core.api import PokemonMetaAPI
from .core.registry import CardRegistry
from .core.user_config import UserConfig
from .commands.cards import CardCommands
from .utils.embeds import EmbedBuilder
from .utils.parser import CardParser

log = logging.getLogger("red.pokemonmeta")

class PokemonMeta(commands.Cog):
    """Pokemon TCG card information and utilities."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=893427812, force_registration=True)
        self.api = PokemonMetaAPI(log=log)
        self.registry = CardRegistry(api=self.api, log=log)
        self.user_config = UserConfig(bot)
        self.parser = CardParser(log=log)
        self.card_commands = CardCommands(
            bot=bot,
            registry=self.registry,
            user_config=self.user_config,
            parser=self.parser,
            log=log
        )
        self._init_task: Optional[asyncio.Task] = None
        log.info("PokemonMeta Cog initialized")

    async def _initialize(self):
        """Initialize all components."""
        try:
            log.debug("Starting component initialization")
            await self.api.initialize()
            log.info("API initialized successfully")
            await self.registry.initialize()
            log.info("Card registry initialized successfully")
            await self.card_commands.initialize()
            log.info("Card commands initialized successfully")

        except Exception as exc:
            log.error(f"Error during initialization: {exc}", exc_info=True)
            raise

    async def cog_load(self) -> None:
        """Handle cog loading."""
        self._init_task = asyncio.create_task(self._initialize())
        try:
            await self._init_task
            log.info("Cog loaded successfully")
        except Exception as e:
            log.error(f"Failed to initialize cog: {e}", exc_info=True)
            raise

    async def cog_unload(self):
        """Handle cog unloading."""
        if hasattr(self, '_init_task') and not self._init_task.done():
            self._init_task.cancel()

        try:
            await asyncio.gather(
                self.api.close(),
                self.card_commands.close(),
                return_exceptions=True
            )
            log.info("All components closed successfully")
        except Exception as e:
            log.error(f"Error during cleanup: {e}")

    @commands.hybrid_group(name="pocket")
    async def pocket_group(self, ctx: commands.Context):
        """Pokemon TCG commands for card information and utilities."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def card_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Wrapper for card name autocomplete."""
        return await self.card_commands.card_name_autocomplete(interaction, current)

    @pocket_group.command(name="card")
    @app_commands.describe(name="The name of the card to search for")
    @app_commands.autocomplete(name=card_autocomplete)
    async def card(self, ctx: commands.Context, *, name: Optional[str] = None):
        """Search for a Pokemon card by name."""
        if not name:
            return await ctx.send("❗ Please provide a card name to search for!")
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.card_commands.text_card(ctx, query=name)

    @pocket_group.command(name="art")
    @app_commands.describe(
        name="The name of the card",
        variant="Art variant number (if multiple exist)"
    )
    @app_commands.autocomplete(name=card_autocomplete)
    async def art(self, ctx: commands.Context, name: str, variant: Optional[int] = 1):
        """Display card artwork."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.card_commands.display_art(ctx, name, variant)

    @app_commands.command(name="pcard")
    @app_commands.describe(name="The name of the card to search for")
    @app_commands.autocomplete(name=card_autocomplete)
    async def pcard(self, interaction: discord.Interaction, name: str):
        """Search for a Pokemon card by name."""
        await interaction.response.defer()
        ctx = await commands.Context.from_interaction(interaction)
        await self.card_commands.text_card(ctx, query=name)

    @app_commands.command(name="pocketart")
    @app_commands.describe(
        name="The name of the card",
        variant="Art variant number (if multiple exist)"
    )
    @app_commands.autocomplete(name=card_autocomplete)
    async def pocketart(self, interaction: discord.Interaction, name: str, variant: Optional[int] = 1):
        """Display card artwork."""
        await interaction.response.defer()
        ctx = await commands.Context.from_interaction(interaction)
        await self.card_commands.display_art(ctx, name, variant)

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        """Handle command errors."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have the required permissions to do that.")
        else:
            log.error(f"Command error: {error}", exc_info=True)
            await ctx.send("An error occurred while processing your command.")
