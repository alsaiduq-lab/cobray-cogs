import discord
from discord.ext import commands
import math
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import random

from ..core.base import BaseTournamentFormat
from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, ROUND_MESSAGES

class SwissTournament(BaseTournamentFormat):
    """
    Handler for Swiss tournament format
    """
    def __init__(self, bot, logger, backup):
        super().__init__(bot, logger, backup)
        self.format_name = "Swiss"
    async def start_tournament(self, ctx, tournament: Tournament) -> bool:
        """Start the Swiss tournament"""
        tournament.meta["current_phase"] = "swiss"
        await self._generate_initial_pairings(tournament)
        embed = discord.Embed(
            title=f"🏆 Tournament Started: {tournament.name} 🏆",
            description=f"The tournament has begun with {len(tournament.participants)} participants!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Format", 
            value=f"{self.format_name} - {tournament.config['rounds_swiss']} Rounds", 
            inline=True
        )
        embed.add_field(
            name="Current Round", 
            value=f"Round {tournament.current_round} of {tournament.config['rounds_swiss']}", 
            inline=True
        )
        # Handle different types of context objects
        is_interaction = hasattr(ctx, 'response')
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
            
        return True
        
    async def _generate_initial_pairings(self, tournament: Tournament):
        """Generate initial tournament pairings for first Swiss round"""
        # Sort participants list by seed if seeding is enabled, otherwise random
        player_ids = list(tournament.participants.keys())
        if tournament.config["seeding_enabled"]:
            player_ids.sort(key=lambda p_id: tournament.participants[p_id].seed)
        else:
            # Random initial pairings
            random.shuffle(player_ids)
        
        # Create pairings
        match_id = tournament.meta["current_match_id"]
        
        for i in range(0, len(player_ids), 2):
            if i + 1 < len(player_ids):
                # Normal pairing
                new_match = Match(
                    match_id=match_id,
                    player1=player_ids[i],
                    player2=player_ids[i + 1],
                    round_num=tournament.current_round,
                    bracket="swiss",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
            else:
                # Odd number of players - this player gets a bye
                bye_player_id = player_ids[i]
                tournament.participants[bye_player_id].wins += 1
                tournament.participants[bye_player_id].match_points += 3  # Award points for bye
                
                # Log bye match
                self.logger.log_tournament_event(tournament.meta["guild_id"], "bye_granted", {
                    "player_id": bye_player_id,
                    "round": tournament.current_round
                })
        
        # Update the match ID counter
        tournament.meta["current_match_id"] = match_id
        
    async def _generate_swiss_pairings(self, tournament: Tournament):
        """Generate pairings for a Swiss round after the first round"""
        # Group players by their match points
        point_groups = {}
        active_players = [p_id for p_id, p in tournament.participants.items() if p.active]
        
        for player_id in active_players:
            points = tournament.participants[player_id].match_points
            if points not in point_groups:
                point_groups[points] = []
            point_groups[points].append(player_id)
        
        # Sort groups by points in descending order
        sorted_groups = sorted(point_groups.keys(), reverse=True)
        
        # Generate pairings trying to match players with same points
        pairings = []
        unpaired_player = None
        
        match_id = tournament.meta["current_match_id"]
        
        for points in sorted_groups:
            players = point_groups[points].copy()
            
            # If we have an unpaired player from a previous group, add them to this group
            if unpaired_player is not None:
                players.append(unpaired_player)
                unpaired_player = None
            
            # Shuffle players in the same point group
            random.shuffle(players)
            
            # Pair players in this point group
            while len(players) >= 2:
                p1 = players.pop(0)
                
                # Try to find a player p1 hasn't played yet
                valid_opponents = [p for p in players if not self._have_players_met(tournament, p1, p)]
                
                if valid_opponents:
                    # Pair with a valid opponent
                    p2 = valid_opponents[0]
                    players.remove(p2)
                else:
                    # If all remaining players have played against p1,
                    # just take the first available player
                    p2 = players.pop(0)
                
                # Create the match
                new_match = Match(
                    match_id=match_id,
                    player1=p1,
                    player2=p2,
                    round_num=tournament.current_round,
                    bracket="swiss",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
            
            # If we have an odd number of players, keep the unpaired player
            if players:
                unpaired_player = players[0]
        
        # Handle the last unpaired player if there is one
        if unpaired_player is not None:
            # This player gets a bye
            tournament.participants[unpaired_player].match_points += 3  # Win points for bye
            tournament.participants[unpaired_player].wins += 1
            
            # Log bye match
            self.logger.log_tournament_event(tournament.meta["guild_id"], "bye_granted", {
                "player_id": unpaired_player,
                "round": tournament.current_round
            })
        
        # Update the match ID counter
        tournament.meta["current_match_id"] = match_id
    
    def _have_players_met(self, tournament: Tournament, player1_id: int, player2_id: int) -> bool:
        """Check if two players have already played each other"""
        for match in tournament.matches.values():
            # Check if both players were in the same match
            if (match.player1 == player1_id and match.player2 == player2_id) or \
               (match.player1 == player2_id and match.player2 == player1_id):
                return True
        return False
        
    async def check_round_completion(self, ctx, tournament: Tournament):
        """Check if the current round is complete and start the next round if needed"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "swiss"]
        
        # Check if all matches in the current round are completed
        if not all(m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ] for m in current_matches):
            return
        
        # Check if we've reached the maximum number of Swiss rounds
        if tournament.current_round >= tournament.config["rounds_swiss"]:
            # Swiss rounds are complete, move to elimination bracket with top players
            await self._start_elimination_phase(ctx, tournament)
        else:
            # Continue with another Swiss round
            tournament.current_round += 1
            
            # Generate new pairings for next Swiss round
            await self._generate_swiss_pairings(tournament)
            
            # Save state
            self.backup.save_tournament_state(
                tournament.meta["guild_id"], 
                tournament.to_dict()
            )
            
            # Send round completion message
            embed = discord.Embed(
                title=f"Swiss Round {tournament.current_round - 1} Complete!",
                description=f"Round {tournament.current_round - 1} is complete! Starting Round {tournament.current_round}...",
                color=discord.Color.green()
            )
            
            is_interaction = hasattr(ctx, 'response')
            if is_interaction:
                await ctx.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
    
    async def _start_elimination_phase(self, ctx, tournament: Tournament):
        """Start the elimination phase after Swiss rounds"""
        is_interaction = hasattr(ctx, 'response')
        
        # Get top players based on match points and tiebreakers
        sorted_players = sorted(
            tournament.participants.items(),
            key=lambda x: (x[1].match_points, x[1].tiebreaker_points),
            reverse=True
        )
        
        # Get top X players for the elimination bracket
        top_cut = min(tournament.config["top_cut"], len(sorted_players))
        top_players = [player_id for player_id, _ in sorted_players[:top_cut]]
        
        # Update tournament phase
        tournament.meta["current_phase"] = "elimination"
        tournament.current_round = 1  # Reset round counter for elimination phase
        
        # Create matches for the elimination bracket
        match_id = tournament.meta["current_match_id"]
        
        for i in range(0, len(top_players), 2):
            if i + 1 < len(top_players):
                new_match = Match(
                    match_id=match_id,
                    player1=top_players[i],
                    player2=top_players[i + 1],
                    round_num=tournament.current_round,
                    bracket="elimination",
                    status=MatchStatus.PENDING,
                    scheduled_time=datetime.now().isoformat()
                )
                tournament.matches[match_id] = new_match
                match_id += 1
        
        # Update match ID counter
        tournament.meta["current_match_id"] = match_id
        
        # Save state
        self.backup.save_tournament_state(
            tournament.meta["guild_id"], 
            tournament.to_dict()
        )
        
        # Send Swiss complete message
        embed = discord.Embed(
            title="Swiss Rounds Complete",
            description=f"Swiss rounds complete! Top {top_cut} advancing to elimination bracket.",
            color=discord.Color.blue()
        )
        
        if is_interaction:
            await ctx.followup.send(embed=embed)
        else:
            await ctx.send(embed=embed)
        
        # Create standings embed
        standings_embed = discord.Embed(
            title="Swiss Rounds Complete - Final Standings",
            description=f"Top {top_cut} players advancing to elimination bracket",
            color=discord.Color.blue()
        )
        
        # Add top players to the embed
        for i, (player_id, player_info) in enumerate(sorted_players[:10], 1):
            player = await self.bot.fetch_user(player_id)
            advancing = "✓" if i <= top_cut else ""
            standings_embed.add_field(
                name=f"{i}. {player.display_name} {advancing}",
                value=f"Points: {player_info.match_points} | "
                      f"Record: {player_info.wins}-{player_info.losses}-{player_info.draws}",
                inline=False
            )
        
        # Send standings
        if is_interaction:
            await ctx.followup.send(embed=standings_embed)
        else:
            await ctx.send(embed=standings_embed)
    
    async def create_bracket_visualization(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create a visualization of the Swiss tournament bracket"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                           if m.round_num == tournament.current_round and m.bracket == "swiss"]
        
        # Create embed
        embed = discord.Embed(
            title=f"Swiss Tournament - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name} | "
                        f"Round {tournament.current_round} of {tournament.config['rounds_swiss']}",
            color=discord.Color.green()
        )
        
        # Add current matches to the embed
        for match in current_matches:
            player1 = await self.bot.fetch_user(match.player1)
            player2 = await self.bot.fetch_user(match.player2)
            
            # Get player records
            p1_record = f"{tournament.participants[player1.id].wins}-{tournament.participants[player1.id].losses}"
            p2_record = f"{tournament.participants[player2.id].wins}-{tournament.participants[player2.id].losses}"
            
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
                value=f"{player1.display_name} ({p1_record}) vs {player2.display_name} ({p2_record})\n{status}",
                inline=False
            )
        
        # Add standings section (top 5 players)
        sorted_players = sorted(
            tournament.participants.items(),
            key=lambda x: (x[1].match_points, x[1].tiebreaker_points),
            reverse=True
        )
        
        standings = "Current Standings (Top 5):\n"
        for i, (player_id, player_info) in enumerate(sorted_players[:5], 1):
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
        """Calculate tiebreaker points for all players (opponent win percentage)"""
        for player_id, player in tournament.participants.items():
            if not player.active:
                continue
                
            # Get all opponents this player has faced
            opponents = []
            for match in tournament.matches.values():
                if match.status != MatchStatus.COMPLETED and match.status != MatchStatus.DRAW:
                    continue
                    
                if match.player1 == player_id and match.player2 is not None:
                    opponents.append(match.player2)
                elif match.player2 == player_id and match.player1 is not None:
                    opponents.append(match.player1)
            
            # Calculate average win percentage of opponents
            if not opponents:
                player.tiebreaker_points = 0.0
                continue
                
            opponent_win_percentages = []
            for opp_id in opponents:
                opp = tournament.participants[opp_id]
                total_matches = opp.wins + opp.losses + opp.draws
                
                if total_matches > 0:
                    win_pct = opp.wins / total_matches
                else:
                    win_pct = 0.0
                    
                opponent_win_percentages.append(win_pct)
                
            # Update tiebreaker points (opponent win percentage)
            if opponent_win_percentages:
                player.tiebreaker_points = sum(opponent_win_percentages) / len(opponent_win_percentages)
            else:
                player.tiebreaker_points = 0.0
