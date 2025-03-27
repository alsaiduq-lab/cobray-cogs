import logging
from typing import Optional

import discord
from redbot.core import Config
from redbot.core.bot import Red

DEFAULT_USER = {
    "preferred_art": 0,
    "mention_mode": True,
    "compact_view": False,
}

class UserConfig:
    """Manages user-specific configurations."""
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            None,
            identifier=893427812,
            force_registration=True,
            cog_name="PokemonMeta"
        )
        self.config.register_user(**DEFAULT_USER)
    async def get_art_preference(self, user_id: int) -> int:
        """Get user's preferred art variant index."""
        data = await self.config.user_from_id(user_id).all()
        return data.get("preferred_art", 0)
    async def set_art_preference(self, user_id: int, preference: int):
        """Set user's preferred art variant index."""
        await self.config.user_from_id(user_id).preferred_art.set(preference)
    async def get_mention_mode(self, user_id: int) -> bool:
        """Get whether user wants card mention responses."""
        data = await self.config.user_from_id(user_id).all()
        return data.get("mention_mode", True)
    async def set_mention_mode(self, user_id: int, enabled: bool):
        """Set whether user wants card mention responses."""
        await self.config.user_from_id(user_id).mention_mode.set(enabled)
    async def get_compact_view(self, user_id: int) -> bool:
        """Get whether user wants compact card view."""
        data = await self.config.user_from_id(user_id).all()
        return data.get("compact_view", False)
    async def set_compact_view(self, user_id: int, enabled: bool):
        """Set whether user wants compact card view."""
        await self.config.user_from_id(user_id).compact_view.set(enabled)
    async def reset_user(self, user_id: int):
        """Reset all settings for a user to defaults."""
        await self.config.user_from_id(user_id).clear()
