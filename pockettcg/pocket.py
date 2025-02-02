import asyncio
from typing import Optional, List
import logging
from logging.handlers import RotatingFileHandler
import discord
from discord import app_commands
from redbot.core import commands, Config

from .core.api import PokemonMetaAPI
from .core.registry import CardRegistry
from .core.user_config import UserConfig
from .commands.cards import CardCommands
from .utils.embeds import EmbedBuilder
from .utils.parser import CardParser
from .utils.images import ImagePipeline

LOGGER_NAME_BASE = "red.pokemonmeta"
log = logging.getLogger(LOGGER_NAME_BASE)

def setup_logging():
    """Configure logging for the entire cog."""
    root_logger = logging.getLogger(LOGGER_NAME_BASE)
    
    # Remove any existing handlers first
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create formatter for detailed output
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create rotating file handler that captures everything (DEBUG and up)
    file_handler = RotatingFileHandler(
        'pokemon_meta.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Set to DEBUG to capture all messages

    # Create stream handler for console output
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)  # Set to DEBUG for development

    # Configure the root logger
    root_logger.setLevel(logging.DEBUG)  # Set root logger to DEBUG
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)
    
    # Prevent propagation to avoid duplicate logs
    root_logger.propagate = False
    
    # Configure child loggers
    child_loggers = [
        'core.api',
        'core.cache',
        'core.registry',
        'commands.cards',
        'utils.embeds',
        'utils.parser',
        'utils.images'
    ]

    for name in child_loggers:
        logger = logging.getLogger(f"{LOGGER_NAME_BASE}.{name}")
        # Remove any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        # Configure child logger
        logger.setLevel(logging.DEBUG)
        logger.propagate = True  # Allow propagation to root logger

    log.debug("Logging system initialized with DEBUG level enabled")

class PokemonMeta(commands.Cog):
    """Pokemon TCG card information and utilities."""

    def __init__(self, bot: commands.Bot):
        setup_logging()
        log.info("Initializing PokemonMeta cog")
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=893427812,
            force_registration=True
        )

        try:
            self.api = PokemonMetaAPI()
            self.image_pipeline = ImagePipeline()

            self.registry = CardRegistry(api=self.api)
            self.user_config = UserConfig(bot)
            self.parser = CardParser()
            self.builder = EmbedBuilder(image_pipeline=self.image_pipeline)

            self.card_commands = CardCommands(
                bot=bot,
                registry=self.registry,
                user_config=self.user_config,
                parser=self.parser,
                builder=self.builder
            )

            self._init_task: Optional[asyncio.Task] = None
            self._ready = asyncio.Event()
            log.info("PokemonMeta cog initialization completed")
        except Exception as e:
            log.error("Failed to initialize PokemonMeta cog", exc_info=True)
            raise

    async def _initialize(self):
        """Initialize all components."""
        try:
            log.info("Starting component initialization")
            await self.api.initialize()
            log.debug("API initialized successfully")

            await self.registry.initialize()
            log.debug("Registry initialized successfully")
            await self.card_commands.initialize()
            log.debug("Card commands initialized successfully")

            self._ready.set()
            log.info("All components initialized successfully")
        except Exception as exc:
            log.error("Critical error during initialization", exc_info=True)
            raise

    async def cog_load(self) -> None:
        """Handle cog loading."""
        log.info("Loading PokemonMeta cog")
        self._init_task = asyncio.create_task(self._initialize())
        try:
            await self._init_task
            log.info("PokemonMeta cog loaded successfully")
        except Exception as e:
            log.error("Fatal error during cog initialization", exc_info=True)
            raise

    async def cog_unload(self):
        """Handle cog unloading."""
        log.info("Unloading PokemonMeta cog")
        if hasattr(self, '_init_task') and not self._init_task.done():
            self._init_task.cancel()
            log.debug("Cancelled initialization task")

        try:
            await asyncio.gather(
                self.card_commands.close(),
                self.image_pipeline.close(),
                self.api.close(),
                return_exceptions=True
            )
            log.info("PokemonMeta cog unloaded successfully")
        except Exception as e:
            log.error("Error during cleanup", exc_info=True)

    async def _ensure_ready(self):
        """Ensure the cog is fully initialized before processing commands."""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            log.error("Initialization timeout exceeded")
            raise commands.CheckFailure(
                "The bot is still initializing. Please try again in a moment."
            )

    async def cog_before_invoke(self, ctx: commands.Context):
        """Ensure the cog is ready before processing any commands."""
        await self._ensure_ready()

    @commands.hybrid_group(name="pocket")
    async def pocket_group(self, ctx: commands.Context):
        """Pokemon TCG commands for card information and utilities."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    async def card_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Wrapper for card name autocomplete."""
        return await self.card_commands.card_name_autocomplete(interaction, current)

    @pocket_group.command(name="card")
    @app_commands.describe(name="The name of the card to search for")
    @app_commands.autocomplete(name=card_autocomplete)
    async def card(self, ctx: commands.Context, *, name: Optional[str] = None):
        """Search for a Pokemon card by name."""
        if not name:
            return await ctx.send("❗ Please provide a card name to search for!")
        log.debug("Processing card command", extra={
            'user_id': ctx.author.id,
            'query': name
        })
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.card_commands.text_card(ctx, query=name)

    @pocket_group.command(name="art")
    @app_commands.describe(
        name="The name of the card",
        variant="Art variant number (if multiple exist)"
    )
    @app_commands.autocomplete(name=card_autocomplete)
    async def art(
        self,
        ctx: commands.Context,
        name: str,
        variant: Optional[int] = 1
    ):
        """Display card artwork."""
        log.debug("Processing art command", extra={
            'user_id': ctx.author.id,
            'query': name,
            'variant': variant
        })
        if ctx.interaction:
            await ctx.interaction.response.defer()
        await self.card_commands.display_art(ctx, name, variant)

    @app_commands.command(name="pcard")
    @app_commands.describe(name="The name of the card to search for")
    @app_commands.autocomplete(name=card_autocomplete)
    async def pcard(self, interaction: discord.Interaction, name: str):
        """Search for a Pokemon card by name."""
        log.debug("Processing pcard command", extra={
            'user_id': interaction.user.id,
            'query': name
        })
        await interaction.response.defer()
        ctx = await commands.Context.from_interaction(interaction)
        await self.card_commands.text_card(ctx, query=name)

    @app_commands.command(name="pocketart")
    @app_commands.describe(
        name="The name of the card",
        variant="Art variant number (if multiple exist)"
    )
    @app_commands.autocomplete(name=card_autocomplete)
    async def pocketart(
        self,
        interaction: discord.Interaction,
        name: str,
        variant: Optional[int] = 1
    ):
        """Display card artwork."""
        log.debug("Processing pocketart command", extra={
            'user_id': interaction.user.id,
            'query': name,
            'variant': variant
        })
        await interaction.response.defer()
        ctx = await commands.Context.from_interaction(interaction)
        await self.card_commands.display_art(ctx, name, variant)

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: Exception
    ):
        """Handle command errors."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("I don't have the required permissions to do that.")
        else:
            log.error(
                "Command error",
                extra={
                    'command': ctx.command.qualified_name,
                    'user_id': ctx.author.id,
                    'error': str(error)
                },
                exc_info=True
            )
            await ctx.send("An error occurred while processing your command.")
