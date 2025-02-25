import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class TournamentLogger:
    def __init__(self, log_dir: str = "tournament_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        log_file = self.log_dir / f"tournament_{datetime.now().strftime('%Y%m%d')}.log"
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("TournamentBot")

    def log_tournament_event(self, guild_id: int, event_type: str, data: Dict[str, Any]):
        """Log tournament events with structured data"""
        log_entry = {
            "guild_id": guild_id,
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        self.logger.info(json.dumps(log_entry))

    def log_deck_submission(self, guild_id: int, user_id: int, deck_info: Dict[str, Any]):
        """Log deck submissions"""
        self.log_tournament_event(guild_id, "deck_submission", {
            "user_id": user_id,
            "deck_info": deck_info
        })

    def log_match_result(self, guild_id: int, match_id: int, winner_id: int, loser_id: int, score: str):
        """Log match results"""
        self.log_tournament_event(guild_id, "match_result", {
            "match_id": match_id,
            "winner_id": winner_id,
            "loser_id": loser_id,
            "score": score
        })

    def log_error(self, guild_id: int, error_type: str, error_msg: str):
        """Log errors"""
        self.log_tournament_event(guild_id, "error", {
            "error_type": error_type,
            "error_message": error_msg
        })
