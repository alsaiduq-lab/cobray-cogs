import aiohttp
import logging
from typing import List, Dict
import yaml

log = logging.getLogger("red.dlm.bonk")

class BonkAPI:
    """Handles OCG art whitelist verification."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        # Load config
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
            self.url = config["api"]["bonk"]["url"]
            self.auth_token = config["api"]["bonk"]["auth_token"]

    async def initialize(self):
        """Initialize aiohttp session."""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()

    async def get_valid_users(self) -> List[Dict[str, str]]:
        """Get list of users with OCG art access."""
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
        """Check if a user has OCG art access."""
        valid_users = await self.get_valid_users()
        return str(user_id) in [user.get("discord_id") for user in valid_users]
