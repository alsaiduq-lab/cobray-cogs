import discord
from discord.ext import commands
import math
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import random

from ..core.base import BaseTournamentFormat
from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, ROUND_MESSAGES

class DoubleEliminationTournament(BaseTournamentFormat):
    """
    Handler for double elimination tournament format
    """
    def __init__(self, bot, logger, backup):
        super().__init__(bot, logger, backup)
        self.format_name = "Double Elimination"
    async def start_tournament(self, ctx, tournament: Tournament) -> bool:
        """Start the double elimination tournament"""
        tournament.meta["current_phase"] = "elimination"
        await self._generate_initial_pairings(tournament, "winners")
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
    async def _generate_initial_pairings(self, tournament: Tournament, bracket: str):
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
                    bracket=bracket,
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
                    "round": tournament.current_round,
                    "bracket": bracket
                })
        tournament.meta["current_match_id"] = match_id
    async def check_round_completion(self, ctx, tournament: Tournament):
        """Check if the current round is complete and start the next round if needed"""
        winners_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "winners"]
        losers_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "losers"]
        winners_complete = all(m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ] 
                            for m in winners_matches)
        losers_complete = all(m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ] 
                           for m in losers_matches)
        if not (winners_complete and losers_complete):
            return
        finals_matches = [m for m in tournament.matches.values() 
                         if m.bracket == "finals" and m.round_num == tournament.current_round]
        if finals_matches and all(m.status == MatchStatus.COMPLETED for m in finals_matches):
            champion_id = finals_matches[0].winner
            await self._handle_tournament_completion(ctx, tournament, champion_id)
            return
        await self._advance_to_next_round(ctx, tournament)
    async def _advance_to_next_round(self, ctx, tournament: Tournament):
        """Advance to the next round of the tournament"""
        winners_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "winners"]
        winners_winners = [m.winner for m in winners_matches if m.winner is not None]
        winners_losers = [m.loser for m in winners_matches if m.loser is not None]
        losers_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "losers"]
        losers_winners = [m.winner for m in losers_matches if m.winner is not None]
        match_id = tournament.meta["current_match_id"]
        if len(winners_winners) == 1 and len(losers_winners) == 1:
            grand_finals = Match(
                match_id=match_id,
                player1=winners_winners[0],  # Winner from winners bracket
                player2=losers_winners[0],   # Winner from losers bracket
                round_num=tournament.current_round + 1,
                bracket="finals",
                status=MatchStatus.PENDING,
                scheduled_time=datetime.now().isoformat()
            )
            tournament.matches[match_id] = grand_finals
            match_id += 1
            tournament.current_round += 1
            tournament.meta["current_match_id"] = match_id
            self.backup.save_tournament_state(
                tournament.meta["guild_id"], 
                tournament.to_dict()
            )
            embed = discord.Embed(
                title="Grand Finals Set!",
                description=f"The grand finals are set! <@{winners_winners[0]}> vs <@{losers_winners[0]}>",
                color=discord.Color.gold()
            )
            is_interaction = hasattr(ctx, 'response')
            if is_interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
            return
        if winners_winners and len(winners_winners) >= 2:
            for i in range(0, len(winners_winners), 2):
                if i + 1 < len(winners_winners):
                    new_match = Match(
                        match_id=match_id,
                        player1=winners_winners[i],
                        player2=winners_winners[i + 1],
                        round_num=tournament.current_round + 1,
                        bracket="winners",
                        status=MatchStatus.PENDING,
                        scheduled_time=datetime.now().isoformat()
                    )
                    tournament.matches[match_id] = new_match
                    match_id += 1
        if winners_losers:
            losers_next = winners_losers + losers_winners
            for i in range(0, len(losers_next), 2):
                if i + 1 < len(losers_next):
                    new_match = Match(
                        match_id=match_id,
                        player1=losers_next[i],
                        player2=losers_next[i + 1],
                        round_num=tournament.current_round + 1,
                        bracket="losers",
                        status=MatchStatus.PENDING,
                        scheduled_time=datetime.now().isoformat()
                    )
                    tournament.matches[match_id] = new_match
                    match_id += 1
        tournament.current_round += 1
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
        # Get winner information
        winner_user = await self.bot.fetch_user(winner_id)
        winner_stats = tournament.participants[winner_id]
        
        # Update tournament state
        tournament.is_started = False
        tournament.meta["end_time"] = datetime.now().isoformat()
        tournament.meta["current_phase"] = "complete"
        
        # Save final state
        self.backup.save_tournament_state(
            tournament.meta["guild_id"], 
            tournament.to_dict()
        )
        
        # Log winner
        self.logger.log_tournament_event(tournament.meta["guild_id"], "tournament_complete", {
            "winner_id": winner_id,
            "tournament_name": tournament.name,
            "participant_count": len(tournament.participants),
            "match_count": len(tournament.matches),
            "duration": tournament.calculate_tournament_duration()
        })
        
        # Create winner announcement embed
        embed = discord.Embed(
            title=ROUND_MESSAGES["TOURNAMENT_COMPLETE"],
            description=f"Congratulations to {winner_user.mention}!",
            color=discord.Color.gold()
        )
        
        # Add trophy emoji to title or make it more prominent
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736927776751992852.png?v=1") # Trophy emoji URL
        
        # Add winner stats
        embed.add_field(
            name="Champion Stats",
            value=f"Wins: {winner_stats.wins}\n"
                  f"Losses: {winner_stats.losses}\n"
                  f"Draws: {winner_stats.draws}\n"
                  f"Match Points: {winner_stats.match_points}"
        )
        
        # Add tournament info
        embed.add_field(
            name="Tournament Info",
            value=f"Name: {tournament.name}\n"
                  f"Format: {self.format_name}\n"
                  f"Players: {len(tournament.participants)}\n"
                  f"Matches: {len(tournament.matches)}"
        )
        
        # Add duration if available
        if tournament.meta["start_time"]:
            duration = tournament.calculate_tournament_duration()
            embed.add_field(
                name="Tournament Duration",
                value=duration,
                inline=True
            )
            
        # Send to channel
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)
        
        return embed
        
    async def create_bracket_visualization(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create a visualization of the double elimination bracket"""
        # Create parent embed
        embed = discord.Embed(
            title=f"Double Elimination - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name}",
            color=discord.Color.blue()
        )
        
        # Get winners bracket matches for current round
        winners_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "winners"]
        
        # Get losers bracket matches for current round
        losers_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "losers"]
        
        # Get finals matches for current round
        finals_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round and m.bracket == "finals"]
        
        # Add winners bracket section
        if winners_matches:
            winners_content = ""
            for match in winners_matches:
                player1 = await self.bot.fetch_user(match.player1)
                player2 = await self.bot.fetch_user(match.player2)
                
                # Determine match status
                status = "🟡 In Progress"
                if match.status == MatchStatus.COMPLETED:
                    winner = await self.bot.fetch_user(match.winner)
                    status = f"✅ {match.score} - Winner: {winner.display_name}"
                elif match.status == MatchStatus.AWAITING_CONFIRMATION:
                    status = f"🟠 Waiting for confirmation - {match.score}"
                elif match.status == MatchStatus.DQ:
                    status = "⛔ Disqualification"
                
                # Check if match is scheduled
                if match.status == MatchStatus.PENDING and match.scheduled_time:
                    try:
                        scheduled_time = datetime.fromisoformat(match.scheduled_time)
                        timestamp = int(scheduled_time.timestamp())
                        schedule_info = f" | ⏰ <t:{timestamp}:R>"
                        status += schedule_info
                    except:
                        pass
                
                winners_content += f"Match {match.match_id}: {player1.display_name} vs {player2.display_name} - {status}\n"
            
            embed.add_field(
                name="🏆 Winners Bracket",
                value=winners_content,
                inline=False
            )
        
        # Add losers bracket section
        if losers_matches:
            losers_content = ""
            for match in losers_matches:
                player1 = await self.bot.fetch_user(match.player1)
                player2 = await self.bot.fetch_user(match.player2)
                
                # Determine match status
                status = "🟡 In Progress"
                if match.status == MatchStatus.COMPLETED:
                    winner = await self.bot.fetch_user(match.winner)
                    status = f"✅ {match.score} - Winner: {winner.display_name}"
                elif match.status == MatchStatus.AWAITING_CONFIRMATION:
                    status = f"🟠 Waiting for confirmation - {match.score}"
                elif match.status == MatchStatus.DQ:
                    status = "⛔ Disqualification"
                
                # Check if match is scheduled
                if match.status == MatchStatus.PENDING and match.scheduled_time:
                    try:
                        scheduled_time = datetime.fromisoformat(match.scheduled_time)
                        timestamp = int(scheduled_time.timestamp())
                        schedule_info = f" | ⏰ <t:{timestamp}:R>"
                        status += schedule_info
                    except:
                        pass
                
                losers_content += f"Match {match.match_id}: {player1.display_name} vs {player2.display_name} - {status}\n"
            
            embed.add_field(
                name="🔄 Losers Bracket",
                value=losers_content,
                inline=False
            )
        
        # Add finals section
        if finals_matches:
            finals_content = ""
            for match in finals_matches:
                player1 = await self.bot.fetch_user(match.player1)
                player2 = await self.bot.fetch_user(match.player2)
                
                # Determine match status
                status = "🟡 In Progress"
                if match.status == MatchStatus.COMPLETED:
                    winner = await self.bot.fetch_user(match.winner)
                    status = f"✅ {match.score} - Winner: {winner.display_name}"
                elif match.status == MatchStatus.AWAITING_CONFIRMATION:
                    status = f"🟠 Waiting for confirmation - {match.score}"
                elif match.status == MatchStatus.DQ:
                    status = "⛔ Disqualification"
                
                # Check if match is scheduled
                if match.status == MatchStatus.PENDING and match.scheduled_time:
                    try:
                        scheduled_time = datetime.fromisoformat(match.scheduled_time)
                        timestamp = int(scheduled_time.timestamp())
                        schedule_info = f" | ⏰ <t:{timestamp}:R>"
                        status += schedule_info
                    except:
                        pass
                
                finals_content += f"Match {match.match_id}: {player1.display_name} vs {player2.display_name} - {status}\n"
            
            embed.add_field(
                name="🏅 Grand Finals",
                value=finals_content,
                inline=False
            )
        
        # Add progress information
        estimated_rounds = self._calculate_total_rounds(len(tournament.participants)) * 2 - 1  # Approximate for DE
        embed.set_footer(text=f"Round {tournament.current_round} | Participants: {len(tournament.participants)}")
        
        return embed
    
    def _calculate_total_rounds(self, player_count: int) -> int:
        """Calculate the total number of rounds needed for a bracket"""
        if player_count <= 1:
            return 0
        return math.ceil(math.log2(player_count))
