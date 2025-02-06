from .whenever import DuelLinksTournament

async def setup(bot):
    await bot.add_cog(DuelLinksTournament(bot))
