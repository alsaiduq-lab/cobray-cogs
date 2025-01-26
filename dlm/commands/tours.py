from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
from datetime import datetime
from ..core.api import DLMApi, DLMAPIError

log = logging.getLogger("red.dlm.tours")

class TournamentCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.group(name="tournament")
    async def tournament_group(self, ctx):
        """Tournament related commands."""
        pass

    @tournament_group.command(name="recent")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def recent_tournaments(self, ctx, limit: int = 5):
        try:
            if limit > 10:
                limit = 10
                await ctx.send("Limiting results to 10 tournaments maximum.")

            async with ctx.typing():
                params = {
                    "limit": limit,
                    "sort": "-date"
                }
                tournaments = await self.api.request("tournaments", params)
                if not tournaments:
                    return await ctx.send("No tournament data found.")

                embeds = []
                for tourney in tournaments:
                    embed = discord.Embed(
                        title=tourney.get("name", "Unnamed Tournament"),
                        url=f"https://www.duellinksmeta.com/tournaments/{tourney.get('id')}",
                        color=discord.Color.blue(),
                        timestamp=datetime.fromisoformat(tourney["date"].replace("Z", "+00:00"))
                    )
                    if "participants" in tourney:
                        embed.add_field(
                            name="Participants",
                            value=str(tourney["participants"]),
                            inline=True
                        )
                    if "winner" in tourney:
                        embed.add_field(
                            name="Winner",
                            value=tourney["winner"],
                            inline=True
                        )
                    if "format" in tourney:
                        embed.add_field(
                            name="Format",
                            value=tourney["format"],
                            inline=True
                        )
                    embeds.append(embed)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching tournament data: {str(e)}")
