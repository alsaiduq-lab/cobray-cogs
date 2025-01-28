from discord import app_commands
from redbot.core import commands, Config
import logging
import asyncio
from typing import Optional

from .core.registry import CardRegistry
from .core.user_config import UserConfig
from .core.api import DLMApi
from .commands.cards import CardCommands
from .commands.articles import ArticleCommands
from .commands.tours import TournamentCommands

from .utils.parser import CardParser
from .utils.images import ImagePipeline

log = logging.getLogger("red.dlm")

class DLM(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=None, force_registration=True)
        self.api = DLMApi(log=log)
        self.registry = CardRegistry(log=log)
        self.user_config = UserConfig(bot)
        self.card_parser = CardParser(log=log)
        self.image_pipeline = ImagePipeline(log=log)

        self.card_commands = CardCommands(
            bot=bot,
            registry=self.registry,
            user_config=self.user_config,
            log=log
        )
        self.article_commands = ArticleCommands(bot=bot, api=self.api)
        self.tournament_commands = TournamentCommands(bot=bot, api=self.api)

        self._init_task: Optional[asyncio.Task] = None
        log.info("DLM Cog initialized")

    async def _initialize(self):
        try:
            await self.api.initialize()
            log.info("API initialized successfully")

            await self.registry.initialize()
            log.info("CardRegistry initialized successfully")

            await self.image_pipeline.initialize()
            log.info("ImagePipeline initialized successfully")

            await self.card_commands.initialize()
            log.info("CardCommands initialized successfully")

        except Exception as exc:
            log.error(f"Error during initialization: {exc}", exc_info=True)
            raise

    async def cog_load(self) -> None:
        self._init_task = asyncio.create_task(self._initialize())
        try:
            await self._init_task
        except Exception as e:
            log.error(f"Failed to initialize cog: {e}", exc_info=True)
            raise

        commands_to_register = (
            self.card_commands.get_commands()
            + self.article_commands.get_commands()
            + self.tournament_commands.get_commands()
        )

        for command in commands_to_register:
            self.bot.tree.add_command(command)

    async def cog_unload(self):
        if hasattr(self, '_init_task') and not self._init_task.done():
            self._init_task.cancel()

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

        else:
            if not card_name:
                return await ctx.send(
                    "❗ Please specify a card name! Example: `dlm cards Dark Magician`"
                )
            await self.card_commands.text_card(ctx, query=card_name)

    @dlm_group.command(name="tournaments", aliases=["tour"])
    @app_commands.describe(tournament_name="Optional: tournament name to search for")
    async def dlm_tournaments(self, ctx: commands.Context, *, tournament_name: Optional[str] = None):
        """Display tournaments (recent ones or search by name)."""
        if ctx.interaction:
            await ctx.interaction.response.defer()
            try:
                if not tournament_name:
                    await self.tournament_commands.text_recent_tournaments(ctx)
                else:
                    await self.tournament_commands.text_tournament_search(ctx, name=tournament_name)
            except Exception as e:
                log.error(f"Error in tournament command: {e}", exc_info=True)
                if ctx.interaction:
                    await ctx.interaction.followup.send(
                        "Something went wrong... :pensive:",
                        ephemeral=True
                    )
                else:
                    await ctx.send("Something went wrong... :pensive:")
        else:
            if not tournament_name:
                await self.tournament_commands.text_recent_tournaments(ctx)
            else:
                await self.tournament_commands.text_tournament_search(ctx, name=tournament_name)

    @dlm_group.command(name="articles")
    @app_commands.describe(query="Search term for articles")
    async def dlm_articles(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Search for articles or get the latest ones."""
        cmd = self.article_commands.articles
        await cmd.callback(self.article_commands, ctx, query=query)
