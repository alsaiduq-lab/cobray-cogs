import discord
from discord.ext import commands
import math
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import random

from ..core.base import BaseTournamentFormat
from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, ROUND_MESSAGES

class RoundRobinTournament(BaseTournamentFormat):
    """
    Handler for Round Robin tournament format
    """
    def __init__(self, bot, logger, backup):
        super().__init__(bot, logger, backup)
        self.format_name = "Round Robin"
        
    async def start_tournament(self, ctx, tournament: Tournament) -> bool:
        """Start the Round Robin tournament"""
        # Set tournament phase
        tournament.meta["current_phase"] = "round_robin"
        
        # Generate pairings for all rounds
        await self._generate_round_robin_pairings(tournament)
        
        # Create and send tournament announcement
        embed = discord.Embed(
            title=f"🏆 Tournament Started: {tournament.name} 🏆",
            description=f"The tournament has begun with {len(tournament.participants)} participants!",
            color=discord.Color.gold()
        )
        
        # Calculate total rounds
        player_count = len(tournament.participants)
        total_rounds = player_count - 1 if player_count % 2 == 0 else player_count
        
        embed.add_field(
            name="Format", 
            value=self.format_name, 
            inline=True
        )
        
        embed.add_field(
            name="Current Round", 
            value=f"Round {tournament.current_round} of {total_rounds}", 
            inline=True
        )
        
        # Handle different types of context objects
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
            
        return True
        
    async def _generate_round_robin_pairings(self, tournament: Tournament):
        """Generate pairings for all rounds of a round robin tournament"""
        player_ids = list(tournament.participants.keys())
        
        # If odd number of players, add a "dummy" player for byes
        if len(player_ids) % 2 == 1:
            player_ids.append(None)
        
        # Implement circle method for round robin pairings
        n = len(player_ids)
        rounds = n - 1
        half = n // 2
        
        match_id = tournament.meta["current_match_id"]
        
        # First player stays fixed, others rotate
        players = [player_ids[0]]
        players.extend(player_ids[1:])
        
        for round_num in range(1, rounds + 1):
            # Pair the players for this round
            pairings = []
            for i in range(half):
                # If we have an odd number, one player gets a bye (plays against None)
                if players[i] is not None and players[n - 1 - i] is not None:
                    pairings.append((players[i], players[n - 1 - i]))
            
            # Create matches for this round
            for p1, p2 in pairings:
                new_match = Match(
                    match_id=match_id,
                    player1=p1,
                    player2=p2,
                    round_num=round_num,
                    bracket="round_robin",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
            
            # Check for byes
            for i in range(half):
                if players[i] is not None and players[n - 1 - i] is None:
                    # This player gets a bye
                    bye_player_id = players[i]
                    tournament.participants[bye_player_id].wins += 1
                    tournament.participants[bye_player_id].match_points += 3
                    
                    # Log bye match
                    self.logger.log_tournament_event(tournament.meta["guild_id"], "bye_granted", {
                        "player_id": bye_player_id,
                        "round": round_num
                    })
                elif players[i] is None and players[n - 1 - i] is not None:
                    # This player gets a bye
                    bye_player_id = players[n - 1 - i]
                    tournament.participants[bye_player_id].wins += 1
                    tournament.participants[bye_player_id].match_points += 3
                    
                    # Log bye match
                    self.logger.log_tournament_event(tournament.meta["guild_id"], "bye_granted", {
                        "player_id": bye_player_id,
                        "round": round_num
                    })
            
            # Rotate the players (keep first player fixed)
            players = [players[0]] + [players[-1]] + players[1:-1]
        
        # Update the match ID counter
        tournament.meta["current_match_id"] = match_id
        
    async def check_round_completion(self, ctx, tournament: Tournament):
        """Check if the current round is complete and start the next round if needed"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "round_robin"]
        
        # Check if all matches in the current round are completed
        if not all(m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ] for m in current_matches):
            return
        
        # Get total rounds
        player_count = len(tournament.participants)
        total_rounds = player_count - 1 if player_count % 2 == 0 else player_count
        
        # Check if this was the last round
        if tournament.current_round >= total_rounds:
            # Tournament complete, determine winner by points
            await self._handle_round_robin_completion(ctx, tournament)
        else:
            # Advance to next round
            tournament.current_round += 1
            
            # Save state
            self.backup.save_tournament_state(
                tournament.meta["guild_id"], 
                tournament.to_dict()
            )
            
            # Send round completion message
            embed = discord.Embed(
                title=f"Round {tournament.current_round - 1} Complete!",
                description=f"Round {tournament.current_round - 1} is complete! Starting Round {tournament.current_round}...",
                color=discord.Color.green()
            )
            
            is_interaction = hasattr(ctx, 'response')
            if is_interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
    
    async def _handle_round_robin_completion(self, ctx, tournament: Tournament):
        """Handle completion of a round robin tournament"""
        is_interaction = hasattr(ctx, 'response')
        
        # Sort players by match points and tiebreakers
        sorted_players = sorted(
            tournament.participants.items(),
            key=lambda x: (x[1].match_points, x[1].tiebreaker_points),
            reverse=True
        )
        
        # Winner is the player with the most points
        winner_id, winner_info = sorted_players[0]
        
        # Complete the tournament
        await self._handle_tournament_completion(ctx, tournament, winner_id)
        
        # Create standings embed
        embed = discord.Embed(
            title="Round Robin Complete - Final Standings",
            description=f"Tournament winner: <@{winner_id}>",
            color=discord.Color.blue()
        )
        
        # Add top players to the embed
        for i, (player_id, player_info) in enumerate(sorted_players[:10], 1):
            player = await self.bot.fetch_user(player_id)
            winner_mark = "🏆" if i == 1 else ""
            embed.add_field(
                name=f"{i}. {player.display_name} {winner_mark}",
                value=f"Points: {player_info.match_points} | "
                      f"Record: {player_info.wins}-{player_info.losses}-{player_info.draws}",
                inline=False
            )
        
        # Send standings
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
        """Create a visualization of the round robin tournament"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                           if m.round_num == tournament.current_round and m.bracket == "round_robin"]
        
        # Get total rounds
        player_count = len(tournament.participants)
        total_rounds = player_count - 1 if player_count % 2 == 0 else player_count
        
        # Create embed
        embed = discord.Embed(
            title=f"Round Robin - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name} | "
                        f"Round {tournament.current_round} of {total_rounds}",
            color=discord.Color.gold()
        )
        
        # Add current matches to the embed
        if current_matches:
            for match in current_matches:
                player1 = await self.bot.fetch_user(match.player1)
                player2 = await self.bot.fetch_user(match.player2)
                
                # Determine match status
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
                
                # Check if match is scheduled
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
                    value=f"{player1.display_name} vs {player2.display_name}\n{status}",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Matches",
                value="No matches scheduled for this round.",
                inline=False
            )
        
        # Add standings table
        sorted_players = sorted(
            tournament.participants.items(),
            key=lambda x: (x[1].match_points, x[1].tiebreaker_points),
            reverse=True
        )
        
        standings = "Current Standings:\n"
        for i, (player_id, player_info) in enumerate(sorted_players[:10], 1):
            player = await self.bot.fetch_user(player_id)
            standings += f"{i}. {player.display_name} - {player_info.match_points} pts " \
                         f"({player_info.wins}-{player_info.losses}-{player_info.draws})\n"
        
        embed.add_field(
            name="Standings",
            value=standings,
            inline=False
        )
        
        return embed
    
    async def _calculate_tiebreakers(self, tournament: Tournament):
        """Calculate head-to-head tiebreakers for round robin format"""
        # For round robin, we use head-to-head results as primary tiebreaker
        # and total game win percentage as secondary tiebreaker
        
        player_matchups = {}
        
        # Build matchup dict
        for player_id in tournament.participants:
            player_matchups[player_id] = {}
        
        # Record head-to-head results
        for match in tournament.matches.values():
            if match.status != MatchStatus.COMPLETED:
                continue
                
            if match.player1 is not None and match.player2 is not None:
                # Record the result for both players
                player_matchups[match.player1][match.player2] = 1 if match.winner == match.player1 else 0
                player_matchups[match.player2][match.player1] = 1 if match.winner == match.player2 else 0
        
        # Calculate tiebreaker points based on head-to-head
        for player_id, player in tournament.participants.items():
            if not player.active:
                continue
                
            # Get players with same match points
            same_points_players = [p_id for p_id, p in tournament.participants.items() 
                                 if p.match_points == player.match_points and p_id != player_id]
            
            # Calculate head-to-head win percentage against tied players
            if same_points_players:
                h2h_wins = sum(player_matchups[player_id].get(opp_id, 0) for opp_id in same_points_players)
                h2h_matches = sum(1 for opp_id in same_points_players if opp_id in player_matchups[player_id])
                h2h_win_pct = h2h_wins / h2h_matches if h2h_matches > 0 else 0
                
                # Use game win percentage as secondary tiebreaker
                total_games = player.wins + player.losses
                game_win_pct = player.wins / total_games if total_games > 0 else 0
                
                # Combine primary and secondary tiebreakers
                player.tiebreaker_points = h2h_win_pct + (game_win_pct * 0.001)  # Small weight for secondary tiebreaker
            else:
                # If no ties, use game win percentage
                total_games = player.wins + player.losses
                game_win_pct = player.wins / total_games if total_games > 0 else 0
                player.tiebreaker_points = game_win_pct
