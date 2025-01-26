from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
import asyncio
from typing import List, Optional, Dict
from ..core.api import DLMApi, MDMApi, YGOProApi, DLMAPIError, DLMNotFoundError
from ..utils.embeds import format_card_embed
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.cards")

class CardCommands(commands.Cog):
    """Card lookup and information commands."""

    def __init__(self, bot):
        self.bot = bot
        self.dlm_api = DLMApi()
        self.mdm_api = MDMApi()
        self.ygopro_api = YGOProApi()
        self.card_cache = {}
        self.last_update = None

    @commands.group(name="card", aliases=["c"])
    async def card_group(self, ctx: commands.Context):
        """Card lookup commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @card_group.command(name="search", aliases=["s"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def search_card(self, ctx: commands.Context, *, query: str):
        """Search for a card by name"""
        try:
            async with ctx.typing():
                cards = await self.ygopro_api.search_cards(query)
                if not cards:
                    return await ctx.send(f"No cards found matching '{query}'")
                if len(cards) == 1:
                    card = cards[0]
                    try:
                        dlm_data = await self.dlm_api.get_card_details(card["name"])
                        card.update(dlm_data)
                    except DLMNotFoundError:
                        pass  # Not all cards will have doo doo duel links data
                    embed = await format_card_embed(card)
                    return await ctx.send(embed=embed)
                pages = []
                for i in range(0, len(cards), 10):
                    chunk = cards[i:i + 10]
                    embed = discord.Embed(
                        title="Card Search Results",
                        description=f"Found {len(cards)} cards matching '{query}'",
                        color=discord.Color.blue()
                    )
                    for idx, card in enumerate(chunk, start=i+1):
                        embed.add_field(
                            name=f"{idx}. {card['name']}",
                            value=f"Type: {card.get('type', 'Unknown')}",
                            inline=False
                        )
                    pages.append(embed)
                await menu(ctx, pages, DEFAULT_CONTROLS)

        except Exception as e:
            log.exception("Error in card search")
            await ctx.send(f"An error occurred while searching: {str(e)}")

    @card_group.command(name="info", aliases=["i"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def card_info(self, ctx: commands.Context, *, card_name: str):
        """Get detailed information about a specific card"""
        try:
            async with ctx.typing():
                card = await self.ygopro_api.get_card(card_name)
                if not card:
                    similar_cards = await self.ygopro_api.search_cards(card_name)
                    if similar_cards:
                        suggestions = [c["name"] for c in similar_cards[:3]]
                        suggestion_msg = "\n\nDid you mean one of these cards?\n" + "\n".join(f"• {name}" for name in suggestions)
                        return await ctx.send(f"Card '{card_name}' not found.{suggestion_msg}")
                    return await ctx.send(f"Card '{card_name}' not found.")

                try:
                    dlm_data = await self.dlm_api.get_card_details(card["name"])
                    card.update(dlm_data)
                except DLMNotFoundError:
                    pass

                try:
                    mdm_data = await self.mdm_api.get_card_details(card["name"])
                    card.update(mdm_data)
                except Exception:
                    pass  # optional, who is playing MD anymore

                embed = await format_card_embed(card)
                await ctx.send(embed=embed)

        except Exception as e:
            log.exception("Error fetching card info")
            await ctx.send(f"An error occurred while fetching card information: {str(e)}")

    @card_group.command(name="random")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def random_card(self, ctx: commands.Context):
        """Get a random card"""
        try:
            async with ctx.typing():
                card = await self.ygopro_api.get_random_card()
                if not card:
                    return await ctx.send("Error fetching random card.")
                try:
                    dlm_data = await self.dlm_api.get_card_details(card["name"])
                    card.update(dlm_data)
                except DLMNotFoundError:
                    pass

                embed = await format_card_embed(card)
                await ctx.send(embed=embed)
        except Exception as e:
            log.exception("Error fetching random card")
            await ctx.send(f"Error fetching random card: {str(e)}")

    @card_group.command(name="box")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def cards_from_box(self, ctx: commands.Context, *, box_name: str):
        """List all cards from a specific box"""
        try:
            async with ctx.typing():
                box_name = box_name.strip().lower()
                cards = await self.dlm_api.get_box_cards(box_name)
                if not cards:
                    boxes = await self.dlm_api.get_boxes(limit=50)
                    similar_boxes = fuzzy_search(box_name, boxes, key="name", threshold=0.6)
                    if similar_boxes:
                        suggestions = [box["name"] for box in similar_boxes[:3]]
                        suggestion_msg = "\n\nDid you mean one of these boxes?\n" + "\n".join(f"• {name}" for name in suggestions)
                        return await ctx.send(f"Box '{box_name}' not found.{suggestion_msg}")
                    return await ctx.send(f"No box found matching '{box_name}'.")

                cards_by_rarity = {}
                for card in cards:
                    rarity = card.get("rarity", "Unknown")
                    if rarity not in cards_by_rarity:
                        cards_by_rarity[rarity] = []
                    cards_by_rarity[rarity].append(card["name"])

                pages = []
                embed = discord.Embed(
                    title=f"Cards in {box_name}",
                    color=discord.Color.blue()
                )

                for rarity, card_list in sorted(cards_by_rarity.items()):
                    card_names = ", ".join(sorted(card_list))
                    if len(card_names) > 1024:
                        chunks = [card_list[i:i + 20] for i in range(0, len(card_list), 20)]
                        for i, chunk in enumerate(chunks):
                            embed.add_field(
                                name=f"{rarity} Cards (Part {i+1})",
                                value=", ".join(sorted(chunk)),
                                inline=False
                            )
                    else:
                        embed.add_field(
                            name=f"{rarity} Cards",
                            value=card_names,
                            inline=False
                        )

                    if len(embed.fields) >= 25:
                        pages.append(embed)
                        embed = discord.Embed(
                            title=f"Cards in {box_name} (Continued)",
                            color=discord.Color.blue()
                        )

                if len(embed.fields) > 0:
                    pages.append(embed)

                if len(pages) == 1:
                    await ctx.send(embed=pages[0])
                else:
                    await menu(ctx, pages, DEFAULT_CONTROLS)

        except DLMAPIError as e:
            log.exception("Error fetching box cards")
            error_msg = "An error occurred while fetching box cards."
            if "not found" in str(e).lower():
                error_msg = f"Box '{box_name}' not found."
            await ctx.send(error_msg)
