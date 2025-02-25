from discord.ext import commands
import discord
from typing import Dict, Optional, List, Union, Any
from datetime import datetime

from ..utils.constants import (
    DEFAULT_TOURNAMENT_CONFIG,
    MIN_PARTICIPANTS,
    MatchStatus,
    TournamentMode
)
from ..utils.log import TournamentLogger
from ..utils.backup import TournamentBackup

from ..formats.single_elimination import SingleEliminationTournament
from ..formats.double_elimination import DoubleEliminationTournament
from ..formats.swiss import SwissTournament
from ..formats.round_robin import RoundRobinTournament

from ..services.registration import RegistrationService
from ..services.match_service import MatchService
from ..services.bracket_service import BracketService
from ..services.scheduling import SchedulingService

from .models import Tournament, Match, Participant


class TournamentManager:
    """
    Core orchestrator for tournament management that delegates to specialized services.
    """
    def __init__(self, bot: commands.Bot, logger: TournamentLogger, backup: TournamentBackup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
        self.guild_settings = {}
        self.registration_service = RegistrationService(bot, logger, backup)
        self.match_service = MatchService(bot, logger, backup)
        self.bracket_service = BracketService(bot, logger)
        self.scheduling_service = SchedulingService(bot, logger, backup)
        self.format_handlers = {
            TournamentMode.SINGLE_ELIMINATION: SingleEliminationTournament(bot, logger, backup),
            TournamentMode.DOUBLE_ELIMINATION: DoubleEliminationTournament(bot, logger, backup),
            TournamentMode.SWISS: SwissTournament(bot, logger, backup),
            TournamentMode.ROUND_ROBIN: RoundRobinTournament(bot, logger, backup)
        }
        self.current_tournament: Optional[Tournament] = None
    async def load_states(self, guilds: List[discord.Guild]):
        """Load tournament states for all guilds"""
        for guild in guilds:
            state = self.backup.load_tournament_state(guild.id)
            if state:
                try:
                    self.current_tournament = Tournament.from_dict(state)
                    self.logger.log_tournament_event(
                        guild.id,
                        "state_restored",
                        {"restored_from": "backup"}
                    )
                except Exception as e:
                    self.logger.log_error(
                        guild.id,
                        "state_restore_failed",
                        f"Failed to restore state: {str(e)}"
                    )

    async def get_tournament_role(self, guild_id: int) -> Optional[discord.Role]:
        """Get the tournament role for a guild"""
        if guild_id not in self.guild_settings:
            return None
        role_id = self.guild_settings[guild_id].get("tournament_role_id")
        if not role_id:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        return guild.get_role(role_id)
    async def get_announcement_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        """Get the announcement channel for a guild"""
        if guild_id not in self.guild_settings:
            return None
        channel_id = self.guild_settings[guild_id].get("announcement_channel_id")
        if not channel_id:
            return None
        return self.bot.get_channel(channel_id)
    async def send_tournament_announcement(self, guild_id: int, embed: discord.Embed, mention_role: bool = False):
        """Send an announcement to the tournament announcement channel"""
        # Implementation remains similar but simplified
        # Delegates to the correct service based on message type
        channel = await self.get_announcement_channel(guild_id)
        if not channel:
            return
        content = None
        if mention_role:
            tournament_role = await self.get_tournament_role(guild_id)
            if tournament_role:
                content = f"{tournament_role.mention}"
        try:
            await channel.send(content=content, embed=embed)
        except Exception as e:
            self.logger.log_error(
                guild_id,
                "announcement_failed",
                f"Error sending announcement: {str(e)}"
            )
    async def create_tournament(self, ctx, name: str, description: str = "", **kwargs):
        """Create a new tournament with the specified settings"""
        if self.current_tournament and self.current_tournament.is_started:
            await ctx.send("A tournament is already in progress!")
            return False
        tournament_mode = kwargs.get("tournament_mode", TournamentMode.SINGLE_ELIMINATION)
        if tournament_mode not in self.format_handlers:
            await ctx.send(f"Invalid tournament mode: {tournament_mode}")
            return False
        self.current_tournament = Tournament(
            name=name,
            description=description,
            guild_id=ctx.guild.id,
            created_by=ctx.author.id if hasattr(ctx, 'author') else ctx.user.id,
            tournament_mode=tournament_mode,
            **kwargs
        )
        self.backup.save_tournament_state(ctx.guild.id, self.current_tournament.to_dict())
        self.logger.log_tournament_event(
            ctx.guild.id,
            "tournament_created",
            {
                "name": name,
                "tournament_mode": tournament_mode,
                "config": self.current_tournament.config
            }
        )
        embed = discord.Embed(
            title=f"Tournament Created: {name}",
            description=description or "No description provided",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Format",
            value=tournament_mode.replace("_", " ").title()
        )
        embed.add_field(
            name="Best of",
            value=str(self.current_tournament.config.get("best_of", 3))
        )
        embed.add_field(
            name="Deck Check",
            value="Required" if self.current_tournament.config.get("deck_check_required") else "Not Required"
        )
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return True
    async def open_registration(self, ctx):
        """Open registration for the tournament"""
        if not self.current_tournament:
            await ctx.send("No tournament has been created yet!")
            return False
        if self.current_tournament.is_started:
            await ctx.send("Tournament has already started!")
            return False
        self.current_tournament.registration_open = True
        self.current_tournament.meta["current_phase"] = "registration"
        self.backup.save_tournament_state(
            ctx.guild.id,
            self.current_tournament.to_dict()
        )
        is_interaction = hasattr(ctx, 'response')
        user = ctx.user if is_interaction else ctx.author
        self.logger.log_tournament_event(
            ctx.guild.id,
            "registration_opened",
            {
                "opened_by": user.id,
                "timestamp": datetime.now().isoformat()
            }
        )
        embed = discord.Embed(
            title=f"Registration Open for {self.current_tournament.name}",
            description="Players can now register for the tournament!",
            color=discord.Color.green()
        )
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return True

    async def register_player(self, ctx, main_deck=None, extra_deck=None, side_deck=None):
        """Register a player for the tournament - delegates to registration service"""
        if not self.current_tournament:
            await ctx.send("No tournament has been created yet!")
            return False
        await self.registration_service.register_player(
            ctx,
            self.current_tournament,
            main_deck,
            extra_deck,
            side_deck
        )

    async def start_tournament(self, ctx):
        """Start the tournament with registered participants"""
        if not self.current_tournament:
            await ctx.send("No tournament has been created yet!")
            return False
        if self.current_tournament.is_started:
            await ctx.send("Tournament has already started!")
            return False
        if len(self.current_tournament.participants) < MIN_PARTICIPANTS:
            await ctx.send(f"Not enough participants (minimum {MIN_PARTICIPANTS}, current: {len(self.current_tournament.participants)})")
            return False
        format_handler = self.format_handlers[self.current_tournament.config["tournament_mode"]]
        success = await format_handler.start_tournament(ctx, self.current_tournament)
        if success:
            self.current_tournament.is_started = True
            self.current_tournament.registration_open = False
            self.current_tournament.meta["start_time"] = datetime.now().isoformat()
            self.backup.save_tournament_state(
                ctx.guild.id,
                self.current_tournament.to_dict()
            )
            await self.send_bracket_status(ctx)
        return success

    async def report_result(self, ctx, opponent, wins, losses, draws=0):
        """Report a match result - delegates to match service"""
        if not self.current_tournament or not self.current_tournament.is_started:
            await ctx.send("No tournament is currently in progress!")
            return False
        result = await self.match_service.report_result(
            ctx,
            self.current_tournament,
            opponent,
            wins,
            losses,
            draws
        )
        if result and result.get("round_complete", False):
            await self.check_round_completion(ctx)
        return result
    async def check_round_completion(self, ctx):
        """Check if the current round is complete and start the next round if needed"""
        if not self.current_tournament or not self.current_tournament.is_started:
            return
        format_handler = self.format_handlers[self.current_tournament.config["tournament_mode"]]
        await format_handler.check_round_completion(ctx, self.current_tournament)
        self.backup.save_tournament_state(
            ctx.guild.id,
            self.current_tournament.to_dict()
        )
    async def send_bracket_status(self, ctx, send_to_announcement=False):
        """Send the current bracket status - delegates to bracket service"""
        if not self.current_tournament:
            await ctx.send("No tournament has been created yet!")
            return
        embed = await self.bracket_service.create_bracket_embed(ctx, self.current_tournament)
        if embed:
            is_interaction = hasattr(ctx, 'response')
            if is_interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
            if send_to_announcement and ctx.guild:
                await self.send_tournament_announcement(ctx.guild.id, embed, False)
    async def schedule_player_match(self, ctx, opponent, time_str):
        """Schedule a match with an opponent - delegates to scheduling service"""
        if not self.current_tournament or not self.current_tournament.is_started:
            await ctx.send("No tournament is currently in progress!")
            return False
        return await self.scheduling_service.schedule_match(
            ctx,
            self.current_tournament,
            opponent,
            time_str
        )
    async def show_upcoming_matches(self, ctx):
        """Show upcoming scheduled matches - delegates to scheduling service"""
        if not self.current_tournament or not self.current_tournament.is_started:
            await ctx.send("No tournament is currently in progress!")
            return False
        return await self.scheduling_service.show_upcoming_matches(ctx, self.current_tournament)
    async def get_tournament_stats(self, ctx):
        """Generate tournament statistics"""
        if not self.current_tournament:
            await ctx.send("No tournament has been created yet!")
            return
        embed = await self.bracket_service.create_stats_embed(ctx, self.current_tournament)
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
    async def disqualify_player(self, ctx, player, reason="Disqualified by moderator"):
        """Disqualify a player from the tournament"""
        if not self.current_tournament or not self.current_tournament.is_started:
            await ctx.send("No tournament is currently in progress!")
            return False
        result = await self.match_service.disqualify_player(
            ctx,
            self.current_tournament,
            player,
            reason
        )
        if result and result.get("round_complete", False):
            await self.check_round_completion(ctx)
        return result
