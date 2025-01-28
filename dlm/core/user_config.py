from redbot.core import Config
from typing import Optional, Dict, Any
import logging

class UserConfig:
    """Manages user-specific configurations."""
    
    def __init__(self, bot, *, log=None):
        """Initialize UserConfig.
        
        Args:
            bot: The Red bot instance
            log: Optional logger instance. If not provided, uses default logger.
        """
        self.bot = bot
        self.logger = log or logging.getLogger("red.dlm.config")
        self.config = Config.get_conf(
            None,
            identifier=8675309991,
            force_registration=True
        )
        default_user = {
            "default_format": "dl",  # paper, md, dl, sd
            "last_used_format": 'dl',  # Remembers last used format
            "use_last_format": True,   # Whether to use last used format as default
            "ocg_access": True,       # Whether user has OCG art access
            "image_mode": "art"   # standard, art, ocg
        }
        default_guild = {
            "auto_search": True,       # Whether to auto-search <card name> mentions
            "preferred_format": None    # Guild-wide format preference
        }
        self.config.register_user(**default_user)
        self.config.register_guild(**default_guild)

    async def get_user_format(self, user_id: int) -> str:
        """Get user's preferred format, considering last used if enabled."""
        try:
            async with self.config.user_from_id(user_id).all() as user_data:
                if user_data["use_last_format"] and user_data["last_used_format"]:
                    return user_data["last_used_format"]
                return user_data["default_format"]
        except Exception as e:
            self.logger.error(f"Error getting user format for {user_id}: {str(e)}", exc_info=True)
            return "dl"  # Default fallback

    async def set_user_format(self, user_id: int, format: str) -> None:
        """Set user's default format."""
        try:
            async with self.config.user_from_id(user_id).all() as user_data:
                user_data["default_format"] = format
        except Exception as e:
            self.logger.error(f"Error setting user format for {user_id}: {str(e)}", exc_info=True)

    async def update_last_format(self, user_id: int, format: str) -> None:
        """Update user's last used format."""
        try:
            async with self.config.user_from_id(user_id).all() as user_data:
                user_data["last_used_format"] = format
        except Exception as e:
            self.logger.error(f"Error updating last format for {user_id}: {str(e)}", exc_info=True)

    async def toggle_format_memory(self, user_id: int) -> bool:
        """Toggle whether to remember last used format."""
        try:
            async with self.config.user_from_id(user_id).all() as user_data:
                user_data["use_last_format"] = not user_data["use_last_format"]
                return user_data["use_last_format"]
        except Exception as e:
            self.logger.error(f"Error toggling format memory for {user_id}: {str(e)}", exc_info=True)
            return True  # Default fallback

    async def has_ocg_access(self, user_id: int) -> bool:
        """Check if user has OCG art access."""
        try:
            user_data = await self.config.user_from_id(user_id).all()
            return user_data["ocg_access"]
        except Exception as e:
            self.logger.error(f"Error checking OCG access for {user_id}: {str(e)}", exc_info=True)
            return True  # Default fallback

    async def set_ocg_access(self, user_id: int, has_access: bool) -> None:
        """Set user's OCG art access."""
        try:
            async with self.config.user_from_id(user_id).all() as user_data:
                user_data["ocg_access"] = has_access
        except Exception as e:
            self.logger.error(f"Error setting OCG access for {user_id}: {str(e)}", exc_info=True)

    async def get_guild_format(self, guild_id: int) -> Optional[str]:
        """Get guild's preferred format."""
        try:
            guild_data = await self.config.guild_from_id(guild_id).all()
            return guild_data["preferred_format"]
        except Exception as e:
            self.logger.error(f"Error getting guild format for {guild_id}: {str(e)}", exc_info=True)
            return None  # Default fallback

    async def set_guild_format(self, guild_id: int, format: Optional[str]) -> None:
        """Set guild's preferred format."""
        try:
            async with self.config.guild_from_id(guild_id).all() as guild_data:
                guild_data["preferred_format"] = format
        except Exception as e:
            self.logger.error(f"Error setting guild format for {guild_id}: {str(e)}", exc_info=True)

    async def get_auto_search(self, guild_id: int) -> bool:
        """Check if guild has auto-search enabled."""
        try:
            guild_data = await self.config.guild_from_id(guild_id).all()
            return guild_data["auto_search"]
        except Exception as e:
            self.logger.error(f"Error getting auto search for {guild_id}: {str(e)}", exc_info=True)
            return True  # Default fallback

    async def toggle_auto_search(self, guild_id: int) -> bool:
        """Toggle guild's auto-search setting."""
        try:
            async with self.config.guild_from_id(guild_id).all() as guild_data:
                guild_data["auto_search"] = not guild_data["auto_search"]
                return guild_data["auto_search"]
        except Exception as e:
            self.logger.error(f"Error toggling auto search for {guild_id}: {str(e)}", exc_info=True)
            return True  # Default fallback
