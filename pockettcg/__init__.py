"""Pokemon TCG cog for Red-DiscordBot."""
import logging

from redbot.core.bot import Red

from .pocket import PokemonMeta

log = logging.getLogger("red.pokemontcg")

__all__ = ["setup"]

async def setup(bot: Red):
    """Load PokemonMeta cog."""
    log.info("Setting up PokemonMeta cog")
    await bot.add_cog(PokemonMeta(bot))
    log.info("PokemonMeta cog has been loaded successfully")
