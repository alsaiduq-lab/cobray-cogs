from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
import asyncio
from ..core.api import DLMApi, DLMAPIError, DLMNotFoundError
from ..utils.embeds import format_card_embed
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.cards")

class CardCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.group(name="card")
    async def card_group(self, ctx):
        """Card database commands."""
        pass

    @card_group.command(name="search")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def card_search(self, ctx, *, query: str = None):
        if not query:
            prompt_msg = await ctx.send("Please enter the name of the card you want to look up:")
            try:
                response = await self.bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                )
                query = response.content
            except asyncio.TimeoutError:
                return await prompt_msg.edit(content="Search timed out. Please try again.")

        try:
            async with ctx.typing():
                try:
                    card = await self.api.request(f"cards/detail", {"name": query})
                    return await ctx.send(embed=format_card_embed(card))
                except DLMNotFoundError:
                    pass
                try:
                    results = await self.api.request("cards/search", {
                        "q": query.lower(),
                        "limit": 5
                    })
                    if results:
                        pass
                    else:
                        raise DLMNotFoundError
                except DLMNotFoundError:
                    cards = await self.api.request("cards", {"limit": 200})
                    results = fuzzy_search(query, cards, key="name", threshold=0.6)
                if not results:
                    suggestion_msg = ""
                    if len(query) > 3:
                        try:
                            similar_cards = await self.api.request(
                                "cards/search",
                                {"q": query[:3], "limit": 3}
                            )
                            if similar_cards:
                                suggestions = [card["name"] for card in similar_cards]
                                suggestion_msg = "\n\nDid you mean one of these?\n" + "\n".join(f"• {name}" for name in suggestions)
                        except DLMAPIError:
                            pass
                    return await ctx.send(f"No cards found matching '{query}'.{suggestion_msg}")

                if len(results) > 1:
                    options = "\n".join(f"{idx+1}. {card['name']}" for idx, card in enumerate(results[:5]))
                    choice_msg = await ctx.send(f"Multiple cards found. Please choose one by number:\n{options}")
                    try:
                        response = await self.bot.wait_for(
                            'message',
                            timeout=30.0,
                            check=lambda m: (
                                m.author == ctx.author and 
                                m.channel == ctx.channel and 
                                m.content.isdigit() and 
                                1 <= int(m.content) <= len(results)
                            )
                        )
                        card = results[int(response.content) - 1]
                    except asyncio.TimeoutError:
                        return await choice_msg.edit(content="Selection timed out. Please try again.")
                else:
                    card = results[0]

                await ctx.send(embed=format_card_embed(card))

        except DLMAPIError as e:
            error_msg = f"An error occurred while searching for the card."
            if isinstance(e, DLMNotFoundError):
                error_msg = f"No cards found matching '{query}'."
            elif isinstance(e, DLMRateLimitError):
                error_msg = f"Please wait before trying again."
            await ctx.send(error_msg)

    @card_group.command(name="random")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def random_card(self, ctx):
        try:
            async with ctx.typing():
                card = await self.api.request("cards/random")
                if not card:
                    return await ctx.send("Error fetching random card.")
                await ctx.send(embed=format_card_embed(card))
        except DLMAPIError as e:
            await ctx.send(f"Error fetching random card: {str(e)}")

    @card_group.command(name="box")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def cards_from_box(self, ctx, *, box_name: str):
        try:
            async with ctx.typing():
                box_name = box_name.strip().lower()
                params = {"box": box_name}
                cards = await self.api.request("cards/box", params)
                if not cards:
                    boxes = await self.api.request("boxes", {"limit": 50})
                    similar_boxes = fuzzy_search(box_name, boxes, key="name", threshold=0.6)
                    if similar_boxes:
                        suggestions = [box["name"] for box in similar_boxes[:3]]
                        suggestion_msg = "\n\nDid you mean one of these boxes?\n" + "\n".join(f"• {name}" for name in suggestions)
                        await ctx.send(f"Box '{box_name}' not found.{suggestion_msg}")
                        return
                    else:
                        await ctx.send(f"No box found matching '{box_name}'.")
                        return

                embed = discord.Embed(
                    title=f"Cards in {box_name}",
                    color=discord.Color.blue()
                )
                cards_by_rarity = {}
                for card in cards:
                    rarity = card.get("rarity", "Unknown")
                    if rarity not in cards_by_rarity:
                        cards_by_rarity[rarity] = []
                    cards_by_rarity[rarity].append(card["name"])

                for rarity, card_list in sorted(cards_by_rarity.items()):
                    card_names = ", ".join(sorted(card_list))
                    if len(card_names) > 1024:
                        card_names = card_names[:1021] + "..."
                    embed.add_field(
                        name=f"{rarity} Cards",
                        value=card_names,
                        inline=False
                    )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            error_msg = "An error occurred while fetching box cards."
            if "not found" in str(e).lower():
                error_msg = f"Box '{box_name}' not found."
            await ctx.send(error_msg)
