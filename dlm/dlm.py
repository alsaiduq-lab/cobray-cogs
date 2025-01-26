import discord
from redbot.core import commands, Config
import logging
import asyncio
from typing import Optional
from .core.registry import CardRegistry
from .core.interactions import InteractionHandler
from .core.user_config import UserConfig
from .utils.parser import CardParser

log = logging.getLogger("red.dlm")

class ArticleCommands:
    """
    Handles subcommands for articles.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="articles")
        async def dlm_articles(ctx: commands.Context, *, query: str = None):
            """
            Example usage: -dlm articles <query>
            """
            if not query:
                await ctx.send_help(ctx.command)
                return

            # Example, placeholder logic:
            await ctx.send(f"Searching articles for: {query} (placeholder)")

class CardCommands:
    """
    Handles subcommands for cards.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="cards")
        async def dlm_cards(ctx: commands.Context, *, card_name: str = None):
            """
            Usage: -dlm cards <card name>
            """
            if not card_name:
                await ctx.send_help(ctx.command)
                return

            results = self.registry.search_cards(card_name)
            if not results:
                await ctx.send(f"No cards found for: {card_name}")
            else:
                names = ", ".join(card.name for card in results[:5])
                await ctx.send(f"Found cards: {names}")

class DeckCommands:
    """
    Handles subcommands for decks.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="decks")
        async def dlm_decks(ctx: commands.Context, *, deck_name: str = None):
            """
            Usage: -dlm decks <deck name>
            """
            if not deck_name:
                await ctx.send_help(ctx.command)
                return

            await ctx.send(f"Looking up deck: {deck_name} (placeholder)")

class EventCommands:
    """
    Handles subcommands for events.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="events")
        async def dlm_events(ctx: commands.Context, *, event_name: str = None):
            """
            Usage: -dlm events <event name>
            """
            if not event_name:
                await ctx.send_help(ctx.command)
                return

            await ctx.send(f"Showing info on event: {event_name} (placeholder)")

class MetaCommands:
    """
    Handles subcommands for meta information.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="meta")
        async def dlm_meta(ctx: commands.Context, *, format_: str = None):
            """
            Usage: -dlm meta <format>
            """
            if not format_:
                await ctx.send_help(ctx.command)
                return

            await ctx.send(f"Fetching meta for format: {format_} (placeholder)")

class TournamentCommands:
    """
    Handles subcommands for tournaments.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="tournaments")
        async def dlm_tournaments(ctx: commands.Context, *, tournament_name: str = None):
            """
            Usage: -dlm tournaments <tournament name>
            """
            if not tournament_name:
                await ctx.send_help(ctx.command)
                return

            await ctx.send(f"Lookup for tournament: {tournament_name} (placeholder)")

class DLM(commands.Cog):
    """DuelLinksMeta Information Cog"""

    def __init__(self, bot):
        self.bot = bot
        self._ready = asyncio.Event()
        self._update_task = None
        self._last_update = None

        self.registry: Optional[CardRegistry] = None
        self.user_config: Optional[UserConfig] = None
        self.interactions: Optional[InteractionHandler] = None

        self.articles: Optional[ArticleCommands] = None
        self.cards: Optional[CardCommands] = None
        self.decks: Optional[DeckCommands] = None
        self.events: Optional[EventCommands] = None
        self.meta: Optional[MetaCommands] = None
        self.tournaments: Optional[TournamentCommands] = None

        log.info("DLM cog constructed")

    async def _initialize_components(self):
        """Initialize all cog components."""
        self.registry = CardRegistry()
        await self.registry.initialize()

        self.user_config = UserConfig(self.bot)
        self.interactions = InteractionHandler(self.bot, self.registry, self.user_config)
        await self.interactions.initialize()

        self.articles = ArticleCommands(self.bot, self.registry)
        self.cards = CardCommands(self.bot, self.registry)
        self.decks = DeckCommands(self.bot, self.registry)
        self.events = EventCommands(self.bot, self.registry)
        self.meta = MetaCommands(self.bot, self.registry)
        self.tournaments = TournamentCommands(self.bot, self.registry)

    def register_subcommands(self):
        """
        Attach subcommands from each subcommand class to the main 'dlm' group.
        """
        self.articles.register(self.dlm)
        self.cards.register(self.dlm)
        self.decks.register(self.dlm)
        self.events.register(self.dlm)
        self.meta.register(self.dlm)
        self.tournaments.register(self.dlm)

    async def cog_load(self) -> None:
        """Initialize cog dependencies."""
        try:
            await self._initialize_components()

            if self.bot.application_id:
                for cmd in self.interactions.get_commands():
                    self.bot.tree.add_command(cmd)
                log.info("Application commands registered")

            self.register_subcommands()

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

    async def _update_registry(self) -> bool:
        """Update the card registry and return success status."""
        try:
            updated = await self.registry.update_registry()
            if updated:
                self._last_update = discord.utils.utcnow()
            return updated
        except Exception as e:
            log.error(f"Error updating registry: {str(e)}", exc_info=True)
            return False

    @commands.group(name="dlm", invoke_without_command=True)
    async def dlm(self, ctx: commands.Context):
        """DuelLinksMeta commands."""
        await ctx.send_help(ctx.command)

    @commands.is_owner()
    @dlm.command(name="updatedb")
    async def force_update(self, ctx: commands.Context):
        """Force an update of the card database."""
        async with ctx.typing():
            if await self._update_registry():
                await ctx.send("Card database updated successfully.")
            else:
                await ctx.send("Failed to update card database. Check logs for details.")

    @commands.is_owner()
    @dlm.command(name="dbstatus")
    async def db_status(self, ctx: commands.Context):
        """Show database status and last update time."""
        if self._last_update:
            time_since = discord.utils.utcnow() - self._last_update
            days_ago = time_since.days
            await ctx.send(
                f"Database last updated: "
                f"{self._last_update.strftime('%Y-%m-%d %H:%M:%S UTC')} "
                f"({days_ago} days ago)"
            )
        else:
            await ctx.send("Database has not been updated since bot start.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Example auto-card-lookup. Handles card mentions in messages."""
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
            found = self.registry.search_cards(name)
            if found:
                cards.append(found[0])

        if not cards:
            return

        format_ = await self.user_config.get_user_format(message.author.id)
        embeds = []
        for card in cards:
            try:
                embed = await self.interactions.builder.build_card_embed(card, format_)
                embeds.append(embed)
            except Exception as e:
                log.error(f"Error building embed for card '{card.name}': {str(e)}", exc_info=True)

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
        """Background task to update card data weekly."""
        try:
            while True:
                try:
                    await self._update_registry()
                except Exception as e:
                    log.error(f"Error updating registry: {str(e)}", exc_info=True)
                await asyncio.sleep(604800)  # 7 days
        except asyncio.CancelledError:
            log.info("Update loop cancelled")
            raise
