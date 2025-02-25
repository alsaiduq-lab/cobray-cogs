from abc import ABC, abstractmethod
import discord
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

class BaseTournamentFormat(ABC):
    """Base class for all tournament format implementations"""
    
    def __init__(self, bot, logger, backup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
        self.format_name = "Base Format"
    
    @abstractmethod
    async def start_tournament(self, ctx, tournament) -> bool:
        """Start the tournament with registered players"""
        pass
    
    @abstractmethod
    async def check_round_completion(self, ctx, tournament):
        """Check if the current round is complete and start the next round if needed"""
        pass
    
    @abstractmethod
    async def create_bracket_visualization(self, ctx, tournament) -> discord.Embed:
        """Create a visualization of the tournament bracket"""
        pass
    
    @abstractmethod
    async def _handle_tournament_completion(self, ctx, tournament, winner_id: int):
        """Handle tournament completion and winner determination"""
        pass
    
    def _calculate_total_rounds(self, player_count: int) -> int:
        """Calculate the total number of rounds needed for a bracket"""
        import math
        if player_count <= 1:
            return 0
        return math.ceil(math.log2(player_count))
