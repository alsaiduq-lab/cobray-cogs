import asyncio
import logging
from typing import List, Optional
from urllib.parse import quote

import discord
from discord import Interaction, SelectOption, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.ui import Select, View

from ..core.models import RARITY_MAPPING, Pokemon
from ..core.registry import CardRegistry
from ..core.user_config import UserConfig
from ..utils.embeds import EmbedBuilder as CardBuilder
from ..utils.fsearch import fuzzy_search_multi
from ..utils.parser import CardParser

log = logging.getLogger("red.pokemontcg.commands")

class CardSelectMenu(Select):
    def __init__(self, cards: List[Pokemon], registry: CardRegistry, config: UserConfig,
                 parser: CardParser, builder: CardBuilder):
        options = []
        for i, card in enumerate(cards[:25]):
            rarity_symbol = RARITY_MAPPING.get(card.rarity, card.rarity)
            label = f"{card.name}"
            if len(label) > 80:
                label = label[:77] + "..."

            description = f"{card.set} | {rarity_symbol}"
            if len(description) > 100:
                description = description[:97] + "..."

            options.append(
                SelectOption(
                    label=label,
                    description=description,
                    value=str(i)
                )
            )

        super().__init__(
            placeholder="Choose a card to preview...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.cards = cards
        self.registry = registry
        self.config = config
        self.parser = parser
        self.builder = builder
        self._view = None

    @property
    def view(self):
        return self._view

    @view.setter
    def view(self, value):
        self._view = value

    async def callback(self, interaction: Interaction):
        idx = int(self.values[0])
        chosen_card = self.cards[idx]
        embed = await self.builder.build_card_embed(chosen_card, as_full_art=False)
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            view=discord.ui.View().add_item(
                SelectButton(idx, chosen_card, self.view.final_callback)
            )
        )

class SelectButton(discord.ui.Button):
    def __init__(self, idx: int, card: Pokemon, callback):
        rarity_symbol = RARITY_MAPPING.get(card.rarity, card.rarity)
        super().__init__(
            label=f"Select {card.name} ({rarity_symbol})",
            style=discord.ButtonStyle.primary,
            custom_id=f"select_{idx}"
        )
        self.card = card
        self.select_callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self.select_callback(interaction, self.card)

class CardSelectView(View):
    def __init__(self, cards: List[Pokemon], registry: CardRegistry, config: UserConfig,
                 parser: CardParser, builder: CardBuilder, final_callback):
        super().__init__(timeout=None)
        self.menu = CardSelectMenu(cards, registry, config, parser, builder)
        self.menu.view = self
        self.add_item(self.menu)
        self.final_callback = final_callback

class CardCommands:
    def __init__(
        self,
        bot: commands.Bot,
        registry: CardRegistry,
        user_config: UserConfig,
        parser: CardParser,
        builder: CardBuilder,
        *,
        log=None
    ):
        self.bot = bot
        self.registry = registry
        self.config = user_config
        self.parser = parser
        self.builder = builder
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        pass

    async def close(self):
        pass



    def _are_alt_variants(self, card1: Pokemon, card2: Pokemon) -> bool:
        """Check if two cards are alt art variants of each other."""
        # Split ID into base components (e.g., "A1-115" -> ["1", "115"])
        def get_base_id(card_id: str) -> tuple:
            parts = card_id.split('-')
            if len(parts) != 2:
                return (card_id,)
            num = parts[0].lstrip('A')  # Remove 'A' prefix if present
            return (num, parts[1])

        return (card1.name == card2.name and
                get_base_id(card1.id) == get_base_id(card2.id) and
                card1.set == card2.set)

    async def search_cards(self, query: str, *, is_autocomplete: bool = False) -> List[Pokemon]:
        if not query:
            return []
        try:
            registry_results = await self.registry.search_cards(query)

            grouped_results = []
            processed_ids = set()

            def add_card(card: Pokemon):
                for idx, existing in enumerate(grouped_results):
                    if self._are_alt_variants(card, existing):
                        if card.is_alternative_art and not existing.is_alternative_art:
                            grouped_results[idx] = card
                        return
                grouped_results.append(card)
                processed_ids.add(card.id)

            for card in registry_results:
                add_card(card)

            if len(grouped_results) < (10 if is_autocomplete else 25) and self.registry.api:
                try:
                    api_results = await self.registry.api.search_cards(query)
                    if api_results:
                        for card_data in api_results:
                            card = Pokemon.from_api(card_data)
                            if card.id not in processed_ids:
                                add_card(card)
                                if card.id not in self.registry._cards:
                                    self.registry._add_card_to_indices(card)
                                    self.registry.cache.set(card.id, card_data)

                            if len(grouped_results) >= (10 if is_autocomplete else 25):
                                break
                except Exception:
                    log.warning("Failed to fetch additional results from API", exc_info=True)

            return grouped_results[:25 if not is_autocomplete else 10]

        except Exception:
            log.error("Error in search_cards", exc_info=True)
            return []

    async def card_name_autocomplete(self, interaction: Interaction, current: str) -> List[Choice[str]]:
        try:
            current = current.strip()
            if not current or len(current) < 3:
                return []

            cards = await self.search_cards(current, is_autocomplete=True)
            return [
                Choice(name=card.name, value=card.name)
                for card in cards[:10]
            ]
        except Exception:
            log.error("Error in card_name_autocomplete", exc_info=True)
            return []

    async def text_card(self, ctx: commands.Context, *, query: str = None):
        if not query:
            return await ctx.send("❗ You must provide a card name!")
        try:
            cards = await self.search_cards(query)
            if not cards:
                return await ctx.send(f"No results found for '{query}'.")

            if exact_match := next((c for c in cards if c.name.lower() == query.lower()), None):
                embed = await self.builder.build_card_embed(exact_match, as_full_art=True)
                return await ctx.send(embed=embed)

            async def handle_final_selection(interaction: discord.Interaction, chosen_card: Pokemon):
                try:
                    embed = await self.builder.build_card_embed(chosen_card, as_full_art=True)
                    try:
                        await interaction.message.edit(embed=embed, view=None)
                    except discord.NotFound:
                        await interaction.response.send_message(embed=embed)
                    except Exception:
                        await interaction.response.send_message(embed=embed)
                except Exception:
                    log.error("Error in handle_final_selection", exc_info=True)
                    await interaction.response.send_message("Something went wrong... 😔", ephemeral=True)

            view = CardSelectView(
                cards=cards,
                registry=self.registry,
                config=self.config,
                parser=self.parser,
                builder=self.builder,
                final_callback=handle_final_selection
            )
            await ctx.send(
                f"Found {len(cards)} cards matching '{query}'. Preview each card and select the one you want:",
                view=view
            )
        except Exception:
            log.error("Error in text_card", exc_info=True)
            await ctx.send("Something went wrong... 😔")

    async def display_art(self, ctx: commands.Context, card_name: str, variant: Optional[int] = 1):
        try:
            cards = await self.search_cards(card_name)
            if not cards:
                return await ctx.send(f"No results found for '{card_name}'.")

            if exact_match := next((c for c in cards if c.name.lower() == card_name.lower()), None):
                if not exact_match.art_variants:
                    return await ctx.send(f"No art variants found for '{exact_match.name}'.")
                variant_idx = (variant or 1) - 1
                if variant_idx < 0 or variant_idx >= len(exact_match.art_variants):
                    return await ctx.send(
                        f"Invalid variant number. Available variants: 1-{len(exact_match.art_variants)}"
                    )

                embed = self.builder.build_art_embed(exact_match, variant_idx)
                return await ctx.send(embed=embed)

            async def handle_final_selection(interaction: discord.Interaction, chosen_card: Pokemon):
                try:
                    if not chosen_card.art_variants:
                        return await interaction.response.send_message(
                            f"No art variants found for '{chosen_card.name}'.",
                            ephemeral=True
                        )
                    variant_idx = (variant or 1) - 1
                    if variant_idx < 0 or variant_idx >= len(chosen_card.art_variants):
                        return await interaction.response.send_message(
                            f"Invalid variant number. Available variants: 1-{len(chosen_card.art_variants)}",
                            ephemeral=True
                        )

                    embed = self.builder.build_art_embed(chosen_card, variant_idx)
                    try:
                        await interaction.message.edit(embed=embed, view=None)
                    except discord.NotFound:
                        await interaction.response.send_message(embed=embed)
                    except Exception:
                        await interaction.response.send_message(embed=embed)
                except Exception:
                    log.error("Error in art display final selection", exc_info=True)
                    await interaction.response.send_message("Something went wrong... 😔", ephemeral=True)

            view = CardSelectView(
                cards=cards,
                registry=self.registry,
                config=self.config,
                parser=self.parser,
                builder=self.builder,
                final_callback=handle_final_selection
            )
            await ctx.send(
                f"Found {len(cards)} cards matching '{card_name}'. Preview each card and select the one you want:",
                view=view
            )

        except ValueError:
            await ctx.send(f"Art not found for '{card_name}'.")
        except Exception:
            log.error("Error in display_art", exc_info=True)
            await ctx.send("Something went wrong while fetching the card art.")

    async def handle_card_mentions(self, message: discord.Message):
        if message.author.bot:
            return

        try:
            card_names = self.parser.extract_card_names(message.content)
            if not card_names:
                return

            found_cards = []
            for name in card_names[:5]:
                cards = await self.search_cards(name)
                if cards:
                    found_cards.append(cards[0])

            if found_cards:
                embeds = []
                for pokemon in found_cards:
                    embed = await self.builder.build_card_embed(pokemon, as_full_art=False)
                    embeds.append(embed)
                await message.reply(embeds=embeds)

        except Exception:
            log.error("Error in handle_card_mentions", exc_info=True)
