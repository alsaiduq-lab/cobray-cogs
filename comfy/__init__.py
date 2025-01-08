from redbot.core.bot import Red

from .comfy import Comfy


async def setup(bot: Red):
    """Load the Comfy cog."""
    await bot.add_cog(Comfy(bot))
