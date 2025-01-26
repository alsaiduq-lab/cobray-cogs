from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
from ..core.api import DLMApi, DLMAPIError
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.decks")

class DeckCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.group(name="decks")
    async def decks_group(self, ctx):
        """Deck-related commands."""
        pass

    @decks_group.command(name="skill")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_skill(self, ctx, *, skill_name: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self.api.request("top-decks", params)
                results = [deck for deck in decks if deck.get("skillName", "").lower() == skill_name.lower()]
                if not results:
                    results = fuzzy_search(skill_name, decks, key="skillName")
                if not results:
                    return await ctx.send("No decks found with that skill.")

                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=f"{deck.get('name', 'Unnamed Deck')} ({deck.get('skillName')})",
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        color=discord.Color.blue()
                    )
                    if "author" in deck:
                        embed.add_field(name="Author", value=deck["author"], inline=True)
                    if "price" in deck:
                        embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
                    embeds.append(embed)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="budget")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def budget_decks(self, ctx, max_gems: int = 30000):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self.api.request("top-decks", params)
                results = [deck for deck in decks if deck.get("price", float('inf')) <= max_gems]
                if not results:
                    return await ctx.send(f"No decks found under {max_gems:,} gems.")

                results.sort(key=lambda x: x.get("price", 0))
                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=deck.get("name", "Unnamed Deck"),
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        description=f"💎 {deck.get('price', 'N/A'):,} gems",
                        color=discord.Color.blue()
                    )
                    if "author" in deck:
                        embed.add_field(name="Author", value=deck["author"], inline=True)
                    if "skillName" in deck:
                        embed.add_field(name="Skill", value=deck["skillName"], inline=True)
                    embeds.append(embed)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="author")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_author(self, ctx, *, author_name: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self.api.request("top-decks", params)
                results = [deck for deck in decks if deck.

    @decks_group.command(name="author")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_author(self, ctx, *, author_name: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self.api.request("top-decks", params)
                results = [deck for deck in decks if deck.get("author", "").lower() == author_name.lower()]
                if not results:
                    results = fuzzy_search(author_name, decks, key="author")
                if not results:
                    return await ctx.send("No decks found by that author.")

                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=deck.get("name", "Unnamed Deck"),
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        color=discord.Color.blue()
                    )
                    if "skillName" in deck:
                        embed.add_field(name="Skill", value=deck["skillName"], inline=True)
                    if "price" in deck:
                        embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
                    embed.set_footer(text=f"By {deck.get('author')}")
                    embeds.append(embed)

                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")
