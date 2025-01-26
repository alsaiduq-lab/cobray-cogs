import aiohttp
import logging
from typing import List, Dict, Optional
import pathlib

log = logging.getLogger("red.dlm.bonk")

class BonkAPI:
    """Handles OCG art verification (optional external service)."""
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.enabled = False
        self.url = None
        self.auth_token = None
        try:
            config_path = pathlib.Path(__file__).parent / "config.yaml"
            if config_path.exists():
                import yaml
                with open(config_path, "r") as f:
                    config = yaml.safe_load(f)
                    if "api" in config and "bonk" in config["api"]:
                        self.url = config["api"]["bonk"].get("url")
                        self.auth_token = config["api"]["bonk"].get("auth_token")
                        if self.url and self.auth_token:
                            self.enabled = True
        except Exception as e:
            log.info(f"Bonk service not configured: {str(e)}")

    async def initialize(self):
        """Initialize aiohttp session if service is enabled."""
        if self.enabled and not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close aiohttp session if it exists."""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_valid_users(self) -> List[Dict[str, str]]:
        """Get list of users with OCG art access."""
        if not self.enabled:
            return []
        if not self.session:
            await self.initialize()

        try:
            async with self.session.get(
                self.url,
                params={"auth": self.auth_token}
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    log.error(f"Failed to get valid users: {resp.status}")
                    return []
        except Exception as e:
            log.error(f"Error getting valid users: {str(e)}")
            return []

    async def is_valid_user(self, user_id: int) -> bool:
        """Check if user has OCG art access.
        If Bonk service is disabled, returns True to allow all users access.
        """
        if not self.enabled:
            return True
        valid_users = await self.get_valid_users()
        return str(user_id) in [user.get("discord_id") for user in valid_users]
