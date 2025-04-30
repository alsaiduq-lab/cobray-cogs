from redbot.core.bot import Red

from .booru import Booru
from core.slash import BooruSlash

__red_end_user_data_statement__ = "This cog does not store end user data."


async def setup(bot: Red):
    await bot.add_cog(Booru(bot))
    await bot.add_cog(BooruSlash(bot))
