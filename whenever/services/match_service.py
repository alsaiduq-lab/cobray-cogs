import discord
from discord.ext import commands
from typing import Dict, Optional, List, Any, Union
from datetime import datetime

from ..core.models import Tournament, Match, Participant
from ..utils.constants import MatchStatus, ERROR_MESSAGES


class MatchService:
    """
    Service for handling match-related operations
    """
    def __init__(self, bot, logger, backup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
    async def find_match(self, tournament: Tournament, player1_id: int, player2_id: int) -> Optional[int]:
        """Find a match between two players"""
        for match_id, match in tournament.matches.items():
            if match.status != MatchStatus.PENDING and match.status != MatchStatus.AWAITING_CONFIRMATION:
                continue
            if (match.player1 == player1_id and match.player2 == player2_id) or \
               (match.player2 == player1_id and match.player1 == player2_id):
                return match_id
        return None
    async def report_result(self, ctx, tournament: Tournament,
                           opponent: discord.Member, wins: int,
                           losses: int, draws: int = 0) -> Dict[str, Any]:
        """Report a match result"""
        is_interaction = hasattr(ctx, 'response')
        user = ctx.user if is_interaction else ctx.author
        if not tournament.is_started:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            else:
                await ctx.send(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            return None

        match_id = await self.find_match(tournament, user.id, opponent.id)

        if match_id is None:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["NO_MATCH_FOUND"])
            else:
                await ctx.send(ERROR_MESSAGES["NO_MATCH_FOUND"])
            return None

        best_of = tournament.config["best_of"]
        max_wins = (best_of // 2) + 1
        if wins > max_wins or losses > max_wins:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["INVALID_SCORE"](best_of))
            else:
                await ctx.send(ERROR_MESSAGES["INVALID_SCORE"](best_of))
            return None
        if draws > 0 and not tournament.config["allow_draws"]:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["DRAWS_NOT_ALLOWED"])
            else:
                await ctx.send(ERROR_MESSAGES["DRAWS_NOT_ALLOWED"])
            return None

        match = tournament.matches[match_id]
        if tournament.config["require_confirmation"] and match.status == MatchStatus.AWAITING_CONFIRMATION:
            if match.reported_by != user.id:
                return await self._confirm_match_result(ctx, tournament, match_id, draws)
            else:
                # Can't confirm your own report
                if is_interaction:
                    await ctx.response.send_message(ERROR_MESSAGES["ALREADY_REPORTED"])
                else:
                    await ctx.send(ERROR_MESSAGES["ALREADY_REPORTED"])
                return None
        score_str = f"{wins}-{losses}" if draws == 0 else f"{wins}-{losses}-{draws}"
        match.score = score_str
        if draws == 0:
            winner_id = user.id if wins > losses else opponent.id
            loser_id = opponent.id if wins > losses else user.id
            match.winner = winner_id
            match.loser = loser_id
        else:
            match.status = MatchStatus.DRAW
            winner_id = None
            loser_id = None
        if tournament.config["require_confirmation"]:
            return await self._await_confirmation(ctx, tournament, match_id, user.id, opponent, winner_id, score_str)
        return await self._complete_match(ctx, tournament, match_id, winner_id, loser_id, score_str, draws)
    async def _await_confirmation(self, ctx, tournament: Tournament, match_id: int,
                                reporter_id: int, opponent: discord.Member,
                                winner_id: Optional[int], score_str: str) -> Dict[str, Any]:
        """Set match to awaiting confirmation state"""
        is_interaction = hasattr(ctx, 'response')
        match = tournament.matches[match_id]
        match.status = MatchStatus.AWAITING_CONFIRMATION
        match.reported_by = reporter_id
        embed = discord.Embed(
            title="Match Result Reported - Waiting for Confirmation",
            description=f"Match {match_id}: <@{match.player1}> vs <@{match.player2}>",
            color=discord.Color.orange()
        )
        embed.add_field(name="Score", value=score_str)
        if winner_id:
            embed.add_field(name="Reported Winner", value=f"<@{winner_id}>")
        else:
            embed.add_field(name="Result", value="Draw")
        embed.add_field(
            name="Confirmation Required",
            value=f"{opponent.mention} needs to confirm this result",
            inline=False
        )
        # Save state
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        self.logger.log_tournament_event(tournament.meta["guild_id"], "match_reported", {
            "match_id": match_id,
            "reported_by": reporter_id,
            "opponent_id": opponent.id,
            "score": score_str,
            "needs_confirmation": True
        })
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return {
            "match_id": match_id,
            "status": "awaiting_confirmation"
        }
    async def _confirm_match_result(self, ctx, tournament: Tournament,
                                  match_id: int, draws: int = 0) -> Dict[str, Any]:
        """Confirm a match result that was previously reported"""
        is_interaction = hasattr(ctx, 'response')
        user = ctx.user if is_interaction else ctx.author
        match = tournament.matches[match_id]
        match.confirmed_by = user.id
        match.status = MatchStatus.COMPLETED
        winner_id = match.winner
        loser_id = match.loser
        result = await self._complete_match(
            ctx, tournament, match_id, winner_id, loser_id, match.score, draws, is_confirmation=True
        )
        embed = discord.Embed(
            title="Match Result Confirmed",
            description=f"Match {match_id}: <@{match.player1}> vs <@{match.player2}>",
            color=discord.Color.green()
        )
        embed.add_field(name="Score", value=match.score)
        if winner_id:
            embed.add_field(name="Winner", value=f"<@{winner_id}>")
        else:
            embed.add_field(name="Result", value="Draw")
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return result
    async def _complete_match(self, ctx, tournament: Tournament, match_id: int,
                            winner_id: Optional[int], loser_id: Optional[int],
                            score: str, draws: int = 0,
                            is_confirmation: bool = False) -> Dict[str, Any]:
        """Complete a match and update player statistics"""
        is_interaction = hasattr(ctx, 'response')
        match = tournament.matches[match_id]
        match.completed_time = datetime.now().isoformat()
        if winner_id is None and loser_id is None:
            match.status = MatchStatus.DRAW
            p1_id = match.player1
            p2_id = match.player2
            tournament.participants[p1_id].draws += 1
            tournament.participants[p2_id].draws += 1
            tournament.participants[p1_id].match_points += 1
            tournament.participants[p2_id].match_points += 1
            self.logger.log_tournament_event(tournament.meta["guild_id"], "match_draw", {
                "match_id": match_id,
                "players": [match.player1, match.player2],
                "score": score
            })
        else:
            match.status = MatchStatus.COMPLETED
            tournament.participants[winner_id].wins += 1
            tournament.participants[loser_id].losses += 1
            tournament.participants[winner_id].match_points += 3
            self.logger.log_tournament_event(tournament.meta["guild_id"], "match_result", {
                "match_id": match_id,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "score": score
            })
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        if not is_confirmation:
            embed = discord.Embed(
                title="Match Result Reported",
                description=f"Match {match_id}: <@{match.player1}> vs <@{match.player2}>",
                color=discord.Color.green()
            )
            embed.add_field(name="Score", value=score)
            if winner_id:
                embed.add_field(name="Winner", value=f"<@{winner_id}>")
            else:
                embed.add_field(name="Result", value="Draw")
            if is_interaction:
                await ctx.response.send_message(embed=embed)
            else:
                await ctx.send(embed=embed)
        current_matches = [m for m in tournament.matches.values()
                          if m.round_num == tournament.current_round]
        round_complete = all(m.status != MatchStatus.PENDING and
                           m.status != MatchStatus.AWAITING_CONFIRMATION
                           for m in current_matches)
        return {
            "match_id": match_id,
            "status": "completed",
            "round_complete": round_complete
        }
    async def disqualify_player(self, ctx, tournament: Tournament,
                               player: discord.Member,
                               reason: str = "Disqualified by moderator") -> Dict[str, Any]:
        """Disqualify a player from the tournament"""
        is_interaction = hasattr(ctx, 'response')
        mod_user = ctx.user if is_interaction else ctx.author
        if not tournament.is_started:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            else:
                await ctx.send(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            return None
        if player.id not in tournament.participants:
            if is_interaction:
                await ctx.response.send_message("This player is not participating in the tournament.")
            else:
                await ctx.send("This player is not participating in the tournament.")
            return None
        if not tournament.participants[player.id].active:
            if is_interaction:
                await ctx.response.send_message("This player is already disqualified or inactive.")
            else:
                await ctx.send("This player is already disqualified or inactive.")
            return None
        tournament.participants[player.id].active = False
        tournament.participants[player.id].dq_info = {
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "dq_by": mod_user.id
        }
        affected_matches = []
        for match_id, match in tournament.matches.items():
            if match.status == MatchStatus.PENDING and (match.player1 == player.id or match.player2 == player.id):
                match.status = MatchStatus.DQ
                
                # Determine winner (the other player)
                if match.player1 == player.id:
                    match.winner = match.player2
                    match.loser = match.player1
                    # Award the win to the opponent
                    tournament.participants[match.player2].wins += 1
                    tournament.participants[match.player2].match_points += 3
                else:
                    match.winner = match.player1
                    match.loser = match.player2
                    # Award the win to the opponent
                    tournament.participants[match.player1].wins += 1
                    tournament.participants[match.player1].match_points += 3
                
                match.score = "DQ"
                match.completed_time = datetime.now().isoformat()
                affected_matches.append(match_id)
        self.logger.log_tournament_event(tournament.meta["guild_id"], "player_dq", {
            "user_id": player.id,
            "reason": reason,
            "dq_by": mod_user.id,
            "affected_matches": affected_matches
        })
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        embed = discord.Embed(
            title="Player Disqualified",
            description=f"{player.mention} has been disqualified from the tournament.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Disqualified By", value=mod_user.mention)
        if affected_matches:
            embed.add_field(
                name=f"Affected Matches ({len(affected_matches)})",
                value="All pending matches have been automatically decided by DQ.",
                inline=False
            )
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        current_matches = [m for m in tournament.matches.values()
                          if m.round_num == tournament.current_round]
        round_complete = all(m.status != MatchStatus.PENDING and
                           m.status != MatchStatus.AWAITING_CONFIRMATION
                           for m in current_matches)
        return {
            "player_id": player.id,
            "status": "disqualified",
            "affected_matches": affected_matches,
            "round_complete": round_complete
        }
