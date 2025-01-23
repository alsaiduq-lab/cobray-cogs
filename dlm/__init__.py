from .dlm import dlm

async def setup(bot):
    await bot.add_cog(dlm(bot))
