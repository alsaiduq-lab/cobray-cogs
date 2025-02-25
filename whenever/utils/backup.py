import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class TournamentBackup:
    def __init__(self, backup_dir: str = "tournament_backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)

    def save_tournament_state(self, guild_id: int, state_data: Dict[str, Any]):
        """Save current tournament state"""
        backup_file = self.backup_dir / f"tournament_{guild_id}.json"
        temp_file = self.backup_dir / f"tournament_{guild_id}.tmp"
        with temp_file.open('w') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "state": state_data
            }, f, indent=2)
        temp_file.replace(backup_file)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        history_file = self.backup_dir / f"tournament_{guild_id}_{timestamp}.json"
        with history_file.open('w') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "state": state_data
            }, f, indent=2)
        history_files = sorted(
            self.backup_dir.glob(f"tournament_{guild_id}_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        for old_file in history_files[5:]:
            old_file.unlink()

    def load_tournament_state(self, guild_id: int) -> Dict[str, Any]:
        """Load tournament state from backup"""
        backup_file = self.backup_dir / f"tournament_{guild_id}.json"
        if not backup_file.exists():
            return {}
        with backup_file.open('r') as f:
            data = json.load(f)
            return data.get("state", {})
