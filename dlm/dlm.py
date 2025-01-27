from discord import app_commands
import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
from typing import Optional, List

from .core.registry import CardRegistry
from .core.interactions import InteractionHandler
from .core.user_config import UserConfig
from .core.api import DLMApi, DLMAPIError

from .utils.parser import CardParser
from .utils.embeds import format_card_embed
from .utils.images import ImagePipeline
from .utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm")


class DLM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=None, force_registration=True)
        self.api = DLMApi()
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
            await self.api.initialize()
            log.info("API initialized successfully")
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
        asyncio.create_task(self.api.close())


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


    async def card_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice]:
        """Provide autocompletions for card_name based on the current typed value."""
        results = self.registry.search_cards(current)
        return [
            app_commands.Choice(name=card.name, value=card.name)
            for card in results[:25]
        ]

    @dlm_group.command(name="cards", aliases=["card"])
    @app_commands.describe(card_name="The name of the card to search for")
    @app_commands.autocomplete(card_name=card_name_autocomplete)
    async def dlm_cards(
        self,
        ctx: commands.Context,
        *,
        card_name: str = None
    ):
        """Search for cards by name."""
        log.info(f"Card search requested by {ctx.author} for: {card_name}")
        if not card_name:
            return await ctx.send_help(ctx.command)

        async with ctx.typing():
            try:
                results = await self.registry.search_cards(card_name)
                if not results:
                    return await ctx.send(f"No cards found matching: {card_name}")
                exact_match = next((c for c in results if c.name.lower() == card_name.lower()), None)
                card = exact_match or results[0]
                log.info(f"Found card: {card.name}")

                embed = format_card_embed(card)
                card_id = str(getattr(card, "id", ""))
                if card_id:
                    try:
                        success, img_url = await self.image_pipeline.get_image_url(
                            card_id,
                            card.monster_types or []
                        )
                        if success:
                            embed.set_image(url=img_url)
                    except Exception as e:
                        log.error(f"Error fetching image for {card_id}: {e}", exc_info=True)

                return await ctx.send(embed=embed)

            except Exception as e:
                log.error(f"Error in card search: {e}", exc_info=True)
                return await ctx.send(f"An error occurred while searching: {str(e)}")




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
