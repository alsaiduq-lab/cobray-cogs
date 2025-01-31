from discord import app_commands, Interaction
from discord.ext import commands
import discord
import logging
from typing import List, Optional
from datetime import datetime
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
from ..utils.embeds import create_tournament_embeds

from ..core.api import DLMApi, DLMAPIError

log = logging.getLogger("red.dlm.commands.tournaments")

class TournamentCommands:
    """Handler for tournament-related commands."""

    def __init__(self, bot: commands.Bot, api: DLMApi, log: logging.Logger):
        """Initialize tournament commands handler."""
        self.bot = bot
        self.api = api
        self.log = log

    def get_commands(self) -> List[app_commands.Command]:
        """Get list of tournament-related commands."""
        return [
            self._tournament_command()
        ]

    def _tournament_command(self) -> app_commands.Command:
        """Create the tournament command."""
        @app_commands.command(
            name="tournament",
            description="Display tournament information by name"
        )
        @app_commands.describe(
            name="Name of the tournament to search for"
        )
        async def tournament(interaction: Interaction, name: str):
            await interaction.response.defer()

            try:
                tournaments = await self.api.search_tournaments(name)
                active_tournaments = [t for t in tournaments if t.get('nextDate')]
                if not active_tournaments:
                    await interaction.followup.send(
                        f"No upcoming tournaments found matching: {name}",
                        ephemeral=True
                    )
                    return
                embeds = create_tournament_embeds(active_tournaments, f"Tournaments matching: {name}")
                if embeds:
                    msg = await interaction.followup.send(embed=embeds[0], wait=True)
                    if len(embeds) > 1:
                        ctx = await self.bot.get_context(msg)
                        await menu(ctx, embeds, DEFAULT_CONTROLS)
                else:
                    await interaction.followup.send(
                        "No tournament information available.",
                        ephemeral=True
                    )

            except Exception as e:
                self.log.error(f"Error in tournament command: {e}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        return tournament

    @commands.group(name="tournament")
    async def tournament_group(self, ctx: commands.Context):
        """Group command for tournament-related functionality."""
        if ctx.invoked_subcommand is None:
            await self.text_recent_tournaments(ctx)

    @tournament_group.command(name="search", aliases=["find"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def text_tournament_search(self, ctx: commands.Context, *, name: str = None):
        """Search for tournaments by name."""
        if not name:
            return await self.text_recent_tournaments(ctx)
        self.log.info(f"Tournament search requested by {ctx.author} for: {name}")
        async with ctx.typing():
            try:
                tournaments = await self.api.search_tournaments(name)
                active_tournaments = [t for t in tournaments if t.get('nextDate')]
                if not active_tournaments:
                    return await ctx.send(f"No upcoming tournaments found matching: {name}")

                embeds = create_tournament_embeds(active_tournaments, name)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)

            except Exception as e:
                self.log.error(f"Error in tournament search: {e}", exc_info=True)
                await ctx.send("Something went wrong... :pensive:")

    @tournament_group.command(name="recent")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def text_recent_tournaments(self, ctx: commands.Context, limit: int = 5):
        """Display recent tournaments."""
        try:
            if limit > 10:
                limit = 10
                await ctx.send("Limiting results to 10 tournaments maximum.")

            async with ctx.typing():
                tournaments = await self.api.get_recent_tournaments(limit)
                active_tournaments = [t for t in tournaments if t.get('nextDate')]
                if not active_tournaments:
                    return await ctx.send("No upcoming tournaments found.")

                embeds = create_tournament_embeds(active_tournaments, "Recent Tournaments")
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)

        except Exception as e:
            self.log.error(f"Error fetching tournament data: {e}", exc_info=True)
            await ctx.send("Something went wrong... :pensive:")
