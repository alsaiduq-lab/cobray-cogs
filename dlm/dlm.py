from discord import app_commands
import discord
from redbot.core import commands, Config
import logging
import asyncio
from datetime import datetime
from typing import Optional, List
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .core.registry import CardRegistry
from .core.user_config import UserConfig
from .core.api import DLMApi, DLMAPIError
from .commands.cards import CardCommands
from .commands.articles import ArticleCommands
from .commands.tours import TournamentCommands

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

        self.card_commands = CardCommands(
            bot=bot,
            registry=self.registry,
            user_config=self.user_config
            
        )
        self.article_commands = ArticleCommands(bot=bot, api=self.api, registry=self.registry)
        self.tournament_commands = TournamentCommands(bot=bot, api=self.api, registry=self.registry)

        # Create an init task. We'll await it in cog_load().
        self._init_task: asyncio.Task = asyncio.create_task(self._initialize())
        log.info("DLM Cog initialized")

    async def _initialize(self):
        """
        Initialize components. We catch NotFound errors from autocomplete
        if needed, so your log won't get spammed by 404 unknown interaction.
        """
        try:
            await self.api.initialize()
            log.info("API initialized successfully")

            await self.registry.initialize()
            log.info("CardRegistry initialized successfully")

            await self.image_pipeline.initialize()
            log.info("ImagePipeline initialized successfully")

        except Exception as exc:
            log.error(f"Error during initialization: {exc}", exc_info=True)

    async def cog_load(self) -> None:
        """
        Red 3.5+ allows async cog_load to register slash commands after internal setup.
        We also await the init task here to ensure everything is initialized.
        """
        # Wait for initialization to complete
        if not self._init_task.done():
            await self._init_task

        # Now register all slash commands from submodules
        commands_to_register = (
            self.card_commands.get_commands()
            + self.article_commands.get_commands()
            + self.tournament_commands.get_commands()
        )

        # Simply register commands
        for command in commands_to_register:
            self.bot.tree.add_command(command)

    async def cog_unload(self):
        """
        Cleanup method to properly close all sessions
        """
        # If the init task never finished, cancel it to avoid leaks
        if hasattr(self, '_init_task') and not self._init_task.done():
            self._init_task.cancel()

        # Close everything that might have a session
        try:
            await self.image_pipeline.close()
        except Exception as e:
            log.error(f"Error closing image pipeline: {e}")

        try:
            await self.api.close()
        except Exception as e:
            log.error(f"Error closing API: {e}")


    @commands.hybrid_group(name="dlm", fallback="help")
    async def dlm_group(self, ctx: commands.Context):
        """DLM commands for card game information and utilities."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm_group.command(name="cards", aliases=["card"])
    @app_commands.describe(
        card_name="The name of the card to search for",
        format="Which format to show (paper/md/dl)."
    )
    async def dlm_cards(
        self,
        ctx: commands.Context,
        *,
        card_name: Optional[str] = None,
        format: Optional[str] = None
    ):
        """
        Searches for a Yu-Gi-Oh! card by name, using prefix or slash.
        For slash usage (/dlm cards), you'll see minimal suggestions or none.
        For prefix usage (!dlm cards <name>), simply provide the card name.
        """
        log.info(f"Card search requested by {ctx.author}: {card_name}")

        # Slash command usage
        if ctx.interaction:
            await ctx.interaction.response.defer()
            if not card_name:
                return await ctx.interaction.followup.send(
                    "❗ You must provide a card name!",
                    ephemeral=True
                )
            try:
                parsed = self.card_commands.parser.parse_card_query(card_name)
                cards = await self.card_commands.registry.search_cards(parsed["query"])
                if not cards:
                    return await ctx.interaction.followup.send(
                        f"No results found for '{card_name}'.",
                        ephemeral=True
                    )

                card = cards[0]
                if card.type == "skill":
                    format = "sd"
                elif format:
                    await self.card_commands.config.update_last_format(ctx.author.id, format)
                else:
                    format = await self.card_commands.config.get_user_format(ctx.author.id)

                embed = await self.card_commands.builder.build_card_embed(card, format)
                embed.url = self.card_commands._get_card_url(card.name)
                await ctx.interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error handling /dlm cards command: {e}", exc_info=True)
                await ctx.interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        # Prefix usage
        else:
            if not card_name:
                return await ctx.send(
                    "❗ Please specify a card name! Example: `dlm cards Dark Magician`"
                )
            await self.card_commands.text_card(ctx, query=card_name)

    @dlm_group.command(name="tournaments", aliases=["tour"])
    @app_commands.describe(tournament_name="The name of the tournament to search for")
    async def dlm_tournaments(self, ctx: commands.Context, *, tournament_name: str = None):
        """Search for tournaments by name."""
        if not tournament_name:
            pass
        await self.tournament_commands.text_tournament_search(ctx=ctx, name=tournament_name)

    @dlm_group.command(name="articles")
    @app_commands.describe(query="Search term for articles")
    async def dlm_articles(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Search for articles or get the latest ones."""
        cmd = self.article_commands.articles
        await cmd.callback(self.article_commands, ctx, query=query)
