from .whenever import DuelLinksTournament
from redbot.core.bot import Red

async def setup(bot: Red):
    try:
        import dateparser
    except ImportError:
        await bot.send_to_owners("The 'dateparser' package is required for the whenever cog to work properly. Please install it using 'pip install dateparser'.")
        return
    await bot.add_cog(DuelLinksTournament(bot))
