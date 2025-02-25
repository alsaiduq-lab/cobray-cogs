import discord
from typing import Dict, List, Optional, Any
import math
from datetime import datetime

from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, TournamentMode


class BracketService:
    """
    Service for handling tournament bracket visualization
    """
    def __init__(self, bot, logger, backup=None):
        self.bot = bot
        self.logger = logger
        self.format_handlers = {
            TournamentMode.SINGLE_ELIMINATION: self._create_single_elimination_embed,
            TournamentMode.DOUBLE_ELIMINATION: self._create_double_elimination_embed,
            TournamentMode.SWISS: self._create_swiss_embed,
            TournamentMode.ROUND_ROBIN: self._create_round_robin_embed
        }
    async def create_bracket_embed(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create appropriate bracket visualization based on tournament type"""
        if not tournament.is_started:
            return await self._create_registration_embed(tournament)
        
        # Check tournament phase
        if tournament.meta["current_phase"] == "elimination" and tournament.config["tournament_mode"] == TournamentMode.SWISS:
            # Top cut phase of a Swiss tournament
            return await self._create_elimination_embed(tournament)
        
        # Use the appropriate handler based on tournament mode
        handler = self.format_handlers.get(tournament.config["tournament_mode"])
        if handler:
            return await handler(tournament)
        
        # Fallback to generic bracket
        return await self._create_generic_bracket_embed(tournament)
        
    async def _create_registration_embed(self, tournament: Tournament) -> discord.Embed:
        """Create an embed showing registration status"""
        embed = discord.Embed(
            title=f"Tournament Registration: {tournament.name}",
            description=tournament.description or "No description provided",
            color=discord.Color.blue()
        )
        
        status = "Open" if tournament.registration_open else "Closed"
        embed.add_field(
            name="Registration Status",
            value=status,
            inline=True
        )
        
        embed.add_field(
            name="Format",
            value=tournament.config["tournament_mode"].replace("_", " ").title(),
            inline=True
        )
        
        embed.add_field(
            name="Match Format",
            value=f"Best of {tournament.config['best_of']}",
            inline=True
        )
        
        embed.add_field(
            name="Registered Players",
            value=str(len(tournament.participants)),
            inline=True
        )
        
        if tournament.participants:
            # Add some registered players
            players_text = ""
            count = 0
            max_display = 10  # Show at most 10 players
            
            for player_id in tournament.participants:
                try:
                    user = await self.bot.fetch_user(player_id)
                    players_text += f"{user.mention}\n"
                    count += 1
                    if count >= max_display:
                        if len(tournament.participants) > max_display:
                            players_text += f"...and {len(tournament.participants) - max_display} more"
                        break
                except:
                    pass
            
            if players_text:
                embed.add_field(
                    name="Participants",
                    value=players_text,
                    inline=False
                )
        
        return embed
        
    async def _create_single_elimination_embed(self, tournament: Tournament) -> discord.Embed:
        """Create visualization for single elimination bracket"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round and m.bracket == "winners"]
        
        # Create embed
        embed = discord.Embed(
            title=f"Single Elimination - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name}",
            color=discord.Color.blue()
        )
        
        # Add current matches to the embed
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
                value=f"{player1.mention} vs {player2.mention}\n{status}",
                inline=False
            )
        
        # Add progress information
        total_rounds = self._calculate_total_rounds(len(tournament.participants))
        embed.set_footer(text=f"Round {tournament.current_round} of {total_rounds} | "
                             f"Participants: {len(tournament.participants)}")
        
        return embed
    
    async def _create_double_elimination_embed(self, tournament: Tournament) -> discord.Embed:
        """Create visualization for double elimination bracket"""
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
        embed.set_footer(text=f"Round {tournament.current_round} | "
                             f"Participants: {len(tournament.participants)}")
        
        return embed
    
    async def _create_swiss_embed(self, tournament: Tournament) -> discord.Embed:
        """Create visualization for Swiss tournament"""
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
    
    async def _create_round_robin_embed(self, tournament: Tournament) -> discord.Embed:
        """Create visualization for round robin tournament"""
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
    
    async def _create_elimination_embed(self, tournament: Tournament) -> discord.Embed:
        """Create visualization for top cut elimination bracket"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                           if m.round_num == tournament.current_round and m.bracket == "elimination"]
        
        # Create embed
        embed = discord.Embed(
            title=f"Top Cut - Elimination Round {tournament.current_round}",
            description=f"Tournament: {tournament.name}",
            color=discord.Color.purple()
        )
        
        # Add current matches to the embed
        for match in current_matches:
            player1 = await self.bot.fetch_user(match.player1)
            player2 = await self.bot.fetch_user(match.player2)
            
            # Get player seeds/records
            p1_record = f"{tournament.participants[player1.id].wins}-{tournament.participants[player1.id].losses}"
            p2_record = f"{tournament.participants[player2.id].wins}-{tournament.participants[player2.id].losses}"
            
            # Determine match status
            status = "🟡 In Progress"
            if match.status == MatchStatus.COMPLETED:
                winner = await self.bot.fetch_user(match.winner)
                status = f"✅ Complete - {match.score} - Winner: {winner.display_name}"
            elif match.status == MatchStatus.AWAITING_CONFIRMATION:
                status = f"🟠 Waiting for confirmation - {match.score}"
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
        
        # Add progress information
        total_rounds = self._calculate_total_rounds(tournament.config["top_cut"])
        embed.set_footer(text=f"Elimination Round {tournament.current_round} of {total_rounds} | "
                              f"Top Cut: {tournament.config['top_cut']} players")
        
        return embed
    
    async def _create_generic_bracket_embed(self, tournament: Tournament) -> discord.Embed:
        """Create a generic bracket visualization for any tournament type"""
        # Get current round matches
        current_matches = [m for m in tournament.matches.values() 
                         if m.round_num == tournament.current_round]
        
        # Create embed
        embed = discord.Embed(
            title=f"Tournament Bracket - Round {tournament.current_round}",
            description=f"Tournament: {tournament.name} | "
                        f"Format: {tournament.config['tournament_mode'].replace('_', ' ').title()}",
            color=discord.Color.blue()
        )
        
        # Add match info
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
            
            embed.add_field(
                name=f"Match {match.match_id}",
                value=f"{player1.mention} vs {player2.mention}\n{status}",
                inline=False
            )
        
        # Add info
        embed.set_footer(text=f"Round {tournament.current_round} | "
                            f"Active Players: {len([p for p in tournament.participants.values() if p.active])}")
        
        return embed
    
    async def create_stats_embed(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create tournament statistics embed"""
        # Create main embed
        embed = discord.Embed(
            title=f"Tournament Statistics: {tournament.name}",
            color=discord.Color.blue()
        )
        
        # Add tournament info
        status = "In Progress" if tournament.is_started else "Not Started"
        if tournament.meta["end_time"]:
            status = "Completed"
        
        embed.add_field(
            name="Status",
            value=status,
            inline=True
        )
        
        embed.add_field(
            name="Mode",
            value=tournament.config["tournament_mode"].replace("_", " ").title(),
            inline=True
        )
        
        embed.add_field(
            name="Format",
            value=f"Best of {tournament.config['best_of']}",
            inline=True
        )
        
        # Add participation stats
        active_players = len([p for p in tournament.participants.values() if p.active])
        
        embed.add_field(
            name="Participants",
            value=f"Total: {len(tournament.participants)}\nActive: {active_players}",
            inline=True
        )
        
        # Add match stats
        completed_matches = len([m for m in tournament.matches.values() 
                               if m.status in [MatchStatus.COMPLETED, MatchStatus.DRAW, MatchStatus.DQ]])
        pending_matches = len([m for m in tournament.matches.values() if m.status == MatchStatus.PENDING])
        
        embed.add_field(
            name="Matches",
            value=f"Total: {len(tournament.matches)}\nCompleted: {completed_matches}\nPending: {pending_matches}",
            inline=True
        )
        
        # Add scheduled matches count
        scheduled_matches = len([m for m in tournament.matches.values() 
                               if m.status == MatchStatus.PENDING and m.scheduled_time])
        if scheduled_matches > 0:
            embed.add_field(
                name="Scheduled",
                value=f"{scheduled_matches} matches",
                inline=True
            )
        
        # Add current phase info
        if tournament.is_started:
            phase_info = f"Current Phase: {tournament.meta['current_phase'].replace('_', ' ').title()}\n"
            phase_info += f"Current Round: {tournament.current_round}"
            
            if tournament.config["tournament_mode"] == TournamentMode.SWISS:
                phase_info += f" of {tournament.config['rounds_swiss']}"
                
            embed.add_field(
                name="Progress",
                value=phase_info,
                inline=True
            )
        
        # Add timing info
        timing_info = ""
        if tournament.meta["start_time"]:
            start_time = datetime.fromisoformat(tournament.meta["start_time"])
            timing_info += f"Started: {start_time.strftime('%Y-%m-%d %H:%M')}\n"
            
            if tournament.meta["end_time"]:
                end_time = datetime.fromisoformat(tournament.meta["end_time"])
                timing_info += f"Ended: {end_time.strftime('%Y-%m-%d %H:%M')}\n"
                timing_info += f"Duration: {tournament.calculate_tournament_duration()}"
            else:
                # Calculate current duration
                current_time = datetime.now()
                duration = current_time - start_time
                hours, remainder = divmod(duration.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                timing_info += f"Duration: {int(hours)}h {int(minutes)}m (ongoing)"
        else:
            timing_info = "Not started yet"
        
        embed.add_field(
            name="Timing",
            value=timing_info,
            inline=False
        )
        
        # Add top players
        if tournament.participants:
            sorted_players = sorted(
                tournament.participants.items(),
                key=lambda x: (x[1].match_points, x[1].wins),
                reverse=True
            )
            
            top_players = ""
            for i, (player_id, player_info) in enumerate(sorted_players[:5], 1):
                player = await self.bot.fetch_user(player_id)
                active_status = "✓" if player_info.active else "⛔"
                top_players += f"{i}. {player.display_name} {active_status} - " \
                              f"{player_info.wins}-{player_info.losses}" \
                              f"{f'-{player_info.draws}' if player_info.draws > 0 else ''}\n"
            
            embed.add_field(
                name="Top Players",
                value=top_players or "No player data",
                inline=False
            )
        
        return embed
        
    def _calculate_total_rounds(self, player_count: int) -> int:
        """Calculate the total number of rounds needed for a bracket"""
        if player_count <= 1:
            return 0
        return math.ceil(math.log2(player_count))
