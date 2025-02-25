import discord
from discord.ext import commands
import math
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import random

from .base import BaseTournamentFormat
from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, ROUND_MESSAGES

class SingleEliminationTournament(BaseTournamentFormat):
    """
    Handler for single elimination tournament format
    """
    def __init__(self, bot, logger, backup):
        super().__init__(bot, logger, backup)
        self.format_name = "Single Elimination"
    async def start_tournament(self, ctx, tournament: Tournament) -> bool:
        """Start the single elimination tournament"""
        tournament.meta["current_phase"] = "elimination"
        await self._generate_initial_pairings(tournament)
        embed = discord.Embed(
            title=f"🏆 Tournament Started: {tournament.name} 🏆",
            description=f"The tournament has begun with {len(tournament.participants)} participants!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Format",
            value=self.format_name,
            inline=True
        )
        embed.add_field(
            name="Current Round",
            value=f"Round {tournament.current_round}",
            inline=True
        )
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return True
    async def _generate_initial_pairings(self, tournament: Tournament):
        """Generate initial tournament pairings"""
        player_ids = list(tournament.participants.keys())
        if tournament.config["seeding_enabled"]:
            player_ids.sort(key=lambda p_id: tournament.participants[p_id].seed)
        else:
            random.shuffle(player_ids)
        player_count = len(player_ids)
        next_power_of_2 = 2 ** math.ceil(math.log2(player_count))
        byes_needed = next_power_of_2 - player_count
        match_id = tournament.meta["current_match_id"]
        for i in range(0, len(player_ids), 2):
            if i + 1 < len(player_ids):
                # Normal pairing
                new_match = Match(
                    match_id=match_id,
                    player1=player_ids[i],
                    player2=player_ids[i + 1],
                    round_num=tournament.current_round,
                    bracket="winners",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
            else:
                # Odd number of players - this player gets a bye
                bye_player_id = player_ids[i]
                tournament.participants[bye_player_id].wins += 1
                
                # Log bye match
                self.logger.log_tournament_event(tournament.meta["guild_id"], "bye_granted", {
                    "player_id": bye_player_id,
                    "round": tournament.current_round
                })
        tournament.meta["current_match_id"] = match_id
    async def check_round_completion(self, ctx, tournament: Tournament):
        """Check if the current round is complete and start the next round if needed"""
        current_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "winners"]
        if not all(m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ] 
                 for m in current_matches):
            return
        winners = [m.winner for m in current_matches if m.winner is not None]
        if len(winners) >= 2:
            await self._advance_to_next_round(ctx, tournament, winners)
        elif len(winners) == 1:
            await self._handle_tournament_completion(ctx, tournament, winners[0])
    async def _advance_to_next_round(self, ctx, tournament: Tournament, winners: List[int]):
        """Advance to the next round of the tournament"""
        tournament.current_round += 1
        match_id = tournament.meta["current_match_id"]
        for i in range(0, len(winners), 2):
            if i + 1 < len(winners):
                new_match = Match(
                    match_id=match_id,
                    player1=winners[i],
                    player2=winners[i + 1],
                    round_num=tournament.current_round,
                    bracket="winners",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
        tournament.meta["current_match_id"] = match_id
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        embed = discord.Embed(
            title=f"Round {tournament.current_round - 1} Complete!",
            description=ROUND_MESSAGES["COMPLETE"](tournament.current_round - 1),
            color=discord.Color.green()
        )
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)
    async def _handle_tournament_completion(self, ctx, tournament: Tournament, winner_id: int):
        """Handle tournament completion and winner determination"""
        winner_user = await self.bot.fetch_user(winner_id)
        winner_stats = tournament.participants[winner_id]
        tournament.is_started = False
        tournament.meta["end_time"] = datetime.now().isoformat()
        tournament.meta["current_phase"] = "complete"
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        self.logger.log_tournament_event(tournament.meta["guild_id"], "tournament_complete", {
            "winner_id": winner_id,
            "tournament_name": tournament.name,
            "participant_count": len(tournament.participants),
            "match_count": len(tournament.matches),
            "duration": tournament.calculate_tournament_duration()
        })
        embed = discord.Embed(
            title=ROUND_MESSAGES["TOURNAMENT_COMPLETE"],
            description=f"Congratulations to {winner_user.mention}!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736927776751992852.png?v=1") # Trophy emoji URL
        embed.add_field(
            name="Champion Stats",
            value=f"Wins: {winner_stats.wins}\n"
                  f"Losses: {winner_stats.losses}\n"
                  f"Draws: {winner_stats.draws}\n"
                  f"Match Points: {winner_stats.match_points}"
        )
        embed.add_field(
            name="Tournament Info",
            value=f"Name: {tournament.name}\n"
                  f"Format: {self.format_name}\n"
                  f"Players: {len(tournament.participants)}\n"
                  f"Matches: {len(tournament.matches)}"
        )
        if tournament.meta["start_time"]:
            duration = tournament.calculate_tournament_duration()
            embed.add_field(
                name="Tournament Duration",
                value=duration,
                inline=True
            )
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)
        return embed
    async def create_bracket_visualization(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create a visualization of the single elimination bracket"""
        current_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "winners"]
        embed = discord.Embed(
            title=f"Single Elimination - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name}",
            color=discord.Color.blue()
        )
        for match in current_matches:
            player1 = await self.bot.fetch_user(match.player1)
            player2 = await self.bot.fetch_user(match.player2)
            status = "🟡 In Progress"
            if match.status == MatchStatus.COMPLETED:
                winner = await self.bot.fetch_user(match.winner)
                status = f"✅ Complete - {match.score} - Winner: {winner.display_name}"
            elif match.status == MatchStatus.AWAITING_CONFIRMATION:
                status = f"🟠 Waiting for confirmation - {match.score}"
            elif match.status == MatchStatus.DRAW:
                status = f"🟠 Draw - {match.score}"
            elif match.status == MatchStatus.DQ:
                status = "⛔ Disqualification"
            if match.status == MatchStatus.PENDING and match.scheduled_time:
                try:
                    scheduled_time = datetime.fromisoformat(match.scheduled_time)
                    timestamp = int(scheduled_time.timestamp())
                    schedule_info = f"\n⏰ Scheduled: <t:{timestamp}:F>"
                    status += schedule_info
                except:
                    pass
            embed.add_field(
                name=f"Match {match.match_id}",
                value=f"{player1.mention} vs {player2.mention}\n{status}",
                inline=False
            )
        total_rounds = self._calculate_total_rounds(len(tournament.participants))
        embed.set_footer(text=f"Round {tournament.current_round} of {total_rounds} | "
                             f"Participants: {len(tournament.participants)}")
        return embed
    def _calculate_total_rounds(self, player_count: int) -> int:
        """Calculate the total number of rounds needed for a bracket"""
        if player_count <= 1:
            return 0
        return math.ceil(math.log2(player_count))
