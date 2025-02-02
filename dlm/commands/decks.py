from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
from typing import List, Optional, Dict, Any
from ..core.api import DLMApi, DLMAPIError
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.decks")

class DeckCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api
        self.BASE_URL = "https://www.duellinksmeta.com/top-decks"
        self.DEFAULT_LIMIT = 50
        self.MAX_DISPLAY = 5

    async def _fetch_decks(self, ctx) -> List[Dict[str, Any]]:
        """Helper method to fetch decks with error handling."""
        params = {"limit": self.DEFAULT_LIMIT}
        return await self.api.request("top-decks", params)

    def _create_deck_embed(self, deck: Dict[str, Any]) -> discord.Embed:
        """Create a standardized embed for deck display."""
        embed = discord.Embed(
            title=deck.get("name", "Unnamed Deck"),
            url=f"{self.BASE_URL}/{deck.get('id')}",
            color=discord.Color.blue()
        )
        if "author" in deck:
            embed.add_field(name="Author", value=deck["author"], inline=True)
        if "skillName" in deck:
            embed.add_field(name="Skill", value=deck["skillName"], inline=True)
        if "price" in deck:
            embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
        return embed

    async def _send_deck_embeds(self, ctx, decks: List[Dict[str, Any]], message: Optional[str] = None):
        """Helper method to send deck embeds with pagination."""
        if not decks:
            await ctx.send(message or "No decks found.")
            return

        embeds = [self._create_deck_embed(deck) for deck in decks[:self.MAX_DISPLAY]]
        if len(embeds) == 1:
            await ctx.send(embed=embeds[0])
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.group(name="decks")
    async def decks_group(self, ctx):
        """Deck-related commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @decks_group.command(name="skill")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_skill(self, ctx, *, skill_name: str):
        try:
            async with ctx.typing():
                decks = await self._fetch_decks(ctx)
                results = [deck for deck in decks if deck.get("skillName", "").lower() == skill_name.lower()]
                if not results:
                    results = fuzzy_search(skill_name, decks, key="skillName")
                await self._send_deck_embeds(ctx, results, "No decks found with that skill.")
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="budget")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def budget_decks(self, ctx, max_gems: int = 30000):
        if max_gems <= 0:
            return await ctx.send("Maximum gems must be greater than 0.")
        try:
            async with ctx.typing():
                decks = await self._fetch_decks(ctx)
                results = [deck for deck in decks if deck.get("price", float('inf')) <= max_gems]
                results.sort(key=lambda x: x.get("price", 0))
                await self._send_deck_embeds(ctx, results, f"No decks found under {max_gems:,} gems.")
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="author")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_author(self, ctx, *, author_name: str):
        try:
            async with ctx.typing():
                decks = await self._fetch_decks(ctx)
                results = [deck for deck in decks if deck.get("author", "").lower() == author_name.lower()]
                if not results:
                    results = fuzzy_search(author_name, decks, key="author")
                await self._send_deck_embeds(ctx, results, "No decks found by that author.")
        except DLMAPIError as e:
            await ctx.send(f"Error fetching decks: {str(e)}")
