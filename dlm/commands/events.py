from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
from datetime import datetime
from ..core.api import DLMApi, DLMAPIError


# might remove, doesnt seem like its worth it atm

class EventCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.command(name="events")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def current_events(self, ctx):
        try:
            async with ctx.typing():
                data = await self.api.request("events/active")
                if not data:
                    return await ctx.send("No active events found.")

                embeds = []
                for event in data:
                    embed = discord.Embed(
                        title=event.get("title", "Unknown Event"),
                        description=event.get("description", "No description available."),
                        color=discord.Color.blue()
                    )
                    if "startDate" in event and "endDate" in event:
                        start = datetime.fromisoformat(event["startDate"].replace("Z", "+00:00"))
                        end = datetime.fromisoformat(event["endDate"].replace("Z", "+00:00"))
                        embed.add_field(
                            name="Duration",
                            value=f"From {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
                            inline=False
                        )
                    if "image" in event:
                        embed.set_thumbnail(url=f"https://www.duellinksmeta.com{event['image']}")
                    embeds.append(embed)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching events: {str(e)}")

