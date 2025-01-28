from discord import app_commands, Interaction
from discord.ext import commands
import discord
import logging
from typing import List, Optional
from datetime import datetime

from ..core.api import DLMApi
from ..utils.embeds import format_article_embed
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

class ArticleCommands(commands.Cog):
    """Handler for article-related commands."""

    def __init__(self, bot: commands.Bot, api: DLMApi):
        """Initialize ArticleCommands.
        Args:
            bot: Discord bot instance
            api: DLM API instance
            log: Optional logger instance. If not provided, uses default logger.
        """
        self.bot = bot
        self.api = api
        self.logger = logging.getLogger("red.dlm.commands.articles")

    def get_commands(self) -> List[app_commands.Command]:
        """
        Return slash-only commands that this cog wants to register.
        In this example, it's just /latest. The hybrid command is
        registered automatically since it uses @commands.hybrid_command.
        """
        return [
            self._latest_command(),
        ]

    def _latest_command(self) -> app_commands.Command:
        """Create the /latest articles command."""
        @app_commands.command(
            name="latest_articles",
            description="Get the latest DLM articles"
        )
        async def latest(interaction: Interaction):
            await interaction.response.defer()

            try:
                articles = await self.get_latest_articles(limit=3)
                if not articles:
                    await interaction.followup.send(
                        "No articles found.",
                        ephemeral=True
                    )
                    return

                embeds = []
                for article in articles:
                    try:
                        embed = format_article_embed(article)
                        embeds.append(embed)
                    except Exception as e:
                        self.logger.error(f"Error formatting article embed: {e}", exc_info=True)

                if not embeds:
                    await interaction.followup.send(
                        "Error formatting articles.",
                        ephemeral=True
                    )
                    return

                await interaction.followup.send(embeds=embeds[:3])

            except Exception as e:
                self.logger.error(f"Error fetching latest articles: {e}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        return latest

    @commands.hybrid_command(name="articles")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(query="Search term for articles")
    async def articles(self, ctx: commands.Context, *, query: Optional[str] = None):
        """Search for articles or get the latest ones (text or slash)."""
        async with ctx.typing():
            try:
                if query:
                    results = await self.search_articles(query)
                    if not results:
                        return await ctx.send(f"No articles found matching: {query}")

                    embeds = []
                    for article in results[:5]:
                        try:
                            embed = format_article_embed(article)
                            embeds.append(embed)
                        except Exception as e:
                            self.logger.error(f"Error formatting article embed: {e}", exc_info=True)

                    if not embeds:
                        return await ctx.send("Error formatting articles.")

                    if len(embeds) == 1:
                        await ctx.send(embed=embeds[0])
                    else:
                        await menu(ctx, embeds, DEFAULT_CONTROLS)

                else:
                    articles = await self.get_latest_articles(limit=3)
                    if not articles:
                        return await ctx.send("No articles found.")

                    embeds = []
                    for article in articles[:3]:
                        try:
                            embed = format_article_embed(article)
                            embeds.append(embed)
                        except Exception as e:
                            self.logger.error(f"Error formatting article embed: {e}", exc_info=True)

                    if not embeds:
                        return await ctx.send("Error formatting articles.")

                    await ctx.send(embeds=embeds)

            except Exception as e:
                self.logger.error(f"Error in article (hybrid) command: {e}", exc_info=True)
                await ctx.send("Something went wrong... :pensive:")

    async def get_latest_articles(self, limit: int = 3) -> List[dict]:
        """Get the latest articles from DLM."""
        try:
            return await self.api.get_latest_articles(limit)
        except Exception as e:
            self.logger.error(f"Error getting latest articles: {str(e)}", exc_info=True)
            return []

    async def search_articles(self, query: str) -> List[dict]:
        """Search articles by query."""
        try:
            return await self.api.search_articles(query)
        except Exception as e:
            self.logger.error(f"Error searching articles: {str(e)}", exc_info=True)
            return []
