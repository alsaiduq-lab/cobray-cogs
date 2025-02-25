from abc import ABC, abstractmethod
import discord
from typing import List, Optional, Dict, Any

from ..core.models import Tournament


class BaseTournamentFormat(ABC):
    """
    Base class for tournament formats that defines the common interface
    """
    def __init__(self, bot, logger, backup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
        self.format_name = "Base Format"
    @abstractmethod
    async def start_tournament(self, ctx, tournament: Tournament) -> bool:
        """Start the tournament with registered players"""
        pass
    @abstractmethod
    async def check_round_completion(self, ctx, tournament: Tournament):
        """Check if the current round is complete and start the next round if needed"""
        pass
    @abstractmethod
    async def create_bracket_visualization(self, ctx, tournament: Tournament) -> discord.Embed:
        """Create a visualization of the tournament bracket"""
        pass
    async def handle_match_result(self, ctx, tournament: Tournament, match_id: int,
                                 winner_id: Optional[int], loser_id: Optional[int],
                                 score: str, draws: int = 0) -> Dict[str, Any]:
        """
        Handle a match result - can be overridden by specific format implementations
        Returns result info including if the round is complete
        """
        match = tournament.matches[match_id]
        match.status = "completed"
        match.winner = winner_id
        match.loser = loser_id
        match.score = score
        if winner_id is None or loser_id is None:
            return {"match_id": match_id, "status": "draw"}
        tournament.participants[winner_id].wins += 1
        tournament.participants[loser_id].losses += 1
        tournament.participants[winner_id].match_points += 3
        current_matches = [m for m in tournament.matches.values() 
                          if m.round_num == tournament.current_round]
        round_complete = all(m.status != "pending" and m.status != "awaiting_confirmation" 
                           for m in current_matches)
        self.backup.save_tournament_state(
            tournament.meta["guild_id"],
            tournament.to_dict()
        )
        self.logger.log_tournament_event(
            tournament.meta["guild_id"],
            "match_completed",
            {
                "match_id": match_id,
                "winner_id": winner_id,
                "loser_id": loser_id,
                "score": score
            }
        )
        return {
            "match_id": match_id,
            "status": "completed",
            "round_complete": round_complete
        }
