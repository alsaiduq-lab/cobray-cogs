from redbot.core.bot import Red
from .poker import Poker

__red_end_user_data_statement__ = "No personal data is stored."

async def setup(bot: Red):
    await bot.add_cog(Poker(bot))
