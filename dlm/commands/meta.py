from redbot.core import commands
import discord
import logging
from ..core.api import DLMApi, DLMAPIError

log = logging.getLogger("red.dlm.meta")

class MetaCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.group(name="meta")
    async def meta_group(self, ctx):
        """Meta analysis commands."""
        pass

    @commands.command(name="tier")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tier_list(self, ctx):
        try:
            async with ctx.typing():
                data = await self.api.request("tier-list")
                embed = discord.Embed(
                    title="Current DLM Tier List",
                    url="https://www.duellinksmeta.com/tier-list/",
                    color=discord.Color.blue()
                )
                for tier in data.get("tiers", []):
                    decks = ", ".join(deck["name"] for deck in tier.get("decks", []))
                    if decks:
                        embed.add_field(
                            name=f"Tier {tier['name']}",
                            value=decks,
                            inline=False
                        )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching tier list: {str(e)}")

    @meta_group.command(name="skills")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def top_skills(self, ctx):
        try:
            async with ctx.typing():
                params = {"limit": 100}
                decks = await self.api.request("top-decks", params)
                skill_counts = {}
                for deck in decks:
                    skill = deck.get("skillName")
                    if skill:
                        skill_counts[skill] = skill_counts.get(skill, 0) + 1
                sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
                embed = discord.Embed(
                    title="Most Used Skills in Current Meta",
                    color=discord.Color.blue()
                )
                for skill, count in sorted_skills[:10]:
                    percentage = (count / len(decks)) * 100
                    embed.add_field(
                        name=skill,
                        value=f"Used in {count} decks ({percentage:.1f}%)",
                        inline=False
                    )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error analyzing meta data: {str(e)}")
