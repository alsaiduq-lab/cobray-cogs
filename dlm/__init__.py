from .dlm import DLM

async def setup(bot):
    await bot.add_cog(DLM(bot))
