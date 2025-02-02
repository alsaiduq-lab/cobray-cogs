from discord import app_commands
import discord
from redbot.core import commands, Config
import logging
import asyncio
import datetime
from typing import Optional, List
from .core.registry import CardRegistry
from .core.interactions import InteractionHandler
from .core.user_config import UserConfig
from .utils.parser import CardParser
from .utils.embeds import format_card_embed
from .utils.images import ImagePipeline
log = logging.getLogger("red.dlm")

class DLM(commands.Cog):
    """
    DLM Cog for card game related commands and functionality.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=None, force_registration=True)
        self.registry = CardRegistry()
        self.user_config = UserConfig(bot)
        self.card_parser = CardParser()
        self.image_pipeline = ImagePipeline()
        self.interaction_handler = InteractionHandler(
            bot=bot,
            card_registry=self.registry,
            user_config=self.user_config
        )
        self._init_task = asyncio.create_task(self._initialize())
        log.info("DLM Cog initialized")

    async def _initialize(self):
        """Initialize components."""
        try:
            await self.registry.initialize()
            log.info("CardRegistry initialized successfully")
            await self.interaction_handler.initialize()
            log.info("InteractionHandler initialized successfully")
            await self.image_pipeline.initialize()
            log.info("ImagePipeline initialized successfully")
        except Exception as exc:
            log.error(f"Error during initialization: {exc}", exc_info=True)


    async def cog_load(self) -> None:
        """Register application commands when the cog loads."""
        await self.bot.tree.sync()

    @commands.hybrid_group(name="dlm", fallback="help")
    async def dlm_group(self, ctx: commands.Context):
        """DLM commands for card game information and utilities."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        if hasattr(self, '_init_task'):
            self._init_task.cancel()
        asyncio.create_task(self.interaction_handler.close())
        asyncio.create_task(self.image_pipeline.close())


    @dlm_group.command(name="articles")
    @app_commands.describe(query="Search term for articles")
    async def dlm_articles(self, ctx: commands.Context, *, query: str = None):
        """
        Search for articles or get the latest ones.
        If no query is provided, returns the latest articles.
        """
        log.info(f"Article search requested by {ctx.author} with query: {query}")
        if not query:
            articles = await self.registry.get_latest_articles(limit=3)
            if not articles:
                return await ctx.send("No articles found.")
            latest = articles[0]
            return await ctx.send(
                f"Latest article: {latest.get('title', 'Untitled')}\n"
                f"https://duellinksmeta.com/articles{latest.get('url', '')}"
            )

        results = await self.registry.search_articles(query)
        if not results:
            return await ctx.send(f"No articles found matching: {query}")

        embed = discord.Embed(
            title="Article Search Results",
            description=f"Found {len(results)} articles matching: {query}",
            color=discord.Color.blue()
        )
        for article in results[:5]:
            embed.add_field(
                name=article.get('title', 'Untitled'),
                value=f"https://duellinksmeta.com/articles{article.get('url', '')}",
                inline=False
            )

        await ctx.send(embed=embed)

    @dlm_group.command(name="cards", aliases=["card"])
    @app_commands.describe(card_name="The name of the card to search for")
    async def dlm_cards(self, ctx: commands.Context, *, card_name: str = None):
        """
        Search for cards by name.
        Displays card information including stats, effects, and format-specific details,
        now with an image.
        """
        log.info(f"Card search requested by {ctx.author} for: {card_name}")
        if not card_name:
            return await ctx.send_help(ctx.command)

        async with ctx.typing():
            results = await self.registry.search_cards(card_name)
            if not results:
                return await ctx.send(f"No cards found matching: {card_name}")

            # Find exact match first, preserving original case and punctuation
            exact_match = next((card for card in results if card.name.replace(" ", "-") == card_name.replace(" ", "-")), None)
            if not exact_match:
                # Try case-insensitive match but preserve original case from result
                exact_match = next((card for card in results if card.name.lower().replace(" ", "-") == card_name.lower().replace(" ", "-")), None)
            
            if exact_match:
                card = exact_match
            else:
                # If no exact match, use the first (best) result from fuzzy search
                card = results[0]

            # Display single card result
            embed = await format_card_embed(card)
            card_id = str(getattr(card, "konamiID", ""))
            monster_types = getattr(card, "monsterType", []) or []

            if card_id:
                success, img_url = await self.image_pipeline.get_image_url(
                    card_id,
                    monster_types
                )
                if success:
                    embed.set_image(url=img_url)

            return await ctx.send(embed=embed)

    @dlm_group.command(name="decks")
    @app_commands.describe(deck_name="The name or archetype of the deck to search for")
    async def dlm_decks(self, ctx: commands.Context, *, deck_name: str = None):
        """Search for decks by name or archetype."""
        log.info(f"Deck search requested by {ctx.author} for: {deck_name}")
        if not deck_name:
            return await ctx.send_help(ctx.command)

        results = await self.registry.search_decks(deck_name)
        if not results:
            return await ctx.send(f"No decks found matching: {deck_name}")

        embed = discord.Embed(
            title="Deck Search Results",
            description=f"Found {len(results)} decks matching: {deck_name}",
            color=discord.Color.blue()
        )
        for deck in results[:5]:
            embed.add_field(
                name=f"{deck.name} by {deck.author}",
                value=f"Format: {deck.format}\nLast Updated: {deck.last_update}",
                inline=False
            )
        await ctx.send(embed=embed)

    @dlm_group.command(name="meta")
    @app_commands.describe(format_="The format to get meta information for")
    async def dlm_meta(self, ctx: commands.Context, *, format_: str = None):
        """Get meta information for a specific format."""
        log.info(f"Meta information requested by {ctx.author} for format: {format_}")
        if not format_:
            return await ctx.send_help(ctx.command)

        meta_report = await self.registry.get_meta_report(format_)
        if not meta_report:
            return await ctx.send(f"No meta report found for format: {format_}")

        embed = discord.Embed(
            title=f"Meta Report - {format_}",
            description=f"Last Updated: {meta_report.last_update}",
            color=discord.Color.blue()
        )
        for deck in meta_report.top_decks[:5]:
            embed.add_field(
                name=f"{deck.name} - {deck.usage_percent}%",
                value=f"Trend: {deck.trend}\nWin Rate: {deck.win_rate}%",
                inline=False
            )
        await ctx.send(embed=embed)

    @dlm_group.command(name="tournaments", aliases=["tour"])
    @app_commands.describe(tournament_name="The name of the tournament to search for")
    async def dlm_tournaments(self, ctx: commands.Context, *, tournament_name: str = None):
        """Search for tournaments by name."""
        log.info(f"Tournament search requested by {ctx.author} for: {tournament_name}")
        if not tournament_name:
            return await ctx.send_help(ctx.command)

        tournaments = await self.registry.search_tournaments(tournament_name)
        if not tournaments:
            return await ctx.send(f"No tournaments found matching: {tournament_name}")

        embeds = []
        chunk_size = 3
        for i in range(0, len(tournaments), chunk_size):
            chunk = tournaments[i:i + chunk_size]
            embed = discord.Embed(
                title=f"Tournaments matching: {tournament_name}",
                description=f"Showing {i + 1}–{min(len(tournaments), i + chunk_size)} "
                           f"of {len(tournaments)} results",
                color=discord.Color.blue()
            )
            for t in chunk:
                next_date = "No upcoming date"
                if t.get("nextDate"):
                    try:
                        dt = datetime.fromisoformat(t["nextDate"].replace("Z", "+00:00"))
                        next_date = dt.strftime("%d %b %Y, %I:%M %p UTC")
                    except ValueError:
                        next_date = t["nextDate"]
                embed.add_field(
                    name=f"{t.get('shortName', 'N/A')} — {t.get('name', 'Unknown Tournament')}",
                    value=f"Next Date: {next_date}",
                    inline=False
                )
            embeds.append(embed)
        for embed in embeds:
            await ctx.send(embed=embed)
