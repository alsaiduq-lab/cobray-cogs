from .xauth import XAuth

async def setup(bot):
    await bot.add_cog(XAuth(bot))
