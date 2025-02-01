import asyncio
import logging
from typing import List, Optional
from urllib.parse import quote

import discord
from discord import Interaction, SelectOption, app_commands
from discord.app_commands import Choice
from discord.ui import Select, View
from discord.ext import commands

from ..core.registry import CardRegistry
from ..core.user_config import UserConfig
from ..utils.embeds import EmbedBuilder as CardBuilder
from ..utils.parser import CardParser
from ..core.models import Pokemon
from ..utils.fsearch import fuzzy_search, fuzzy_search_multi

class CardSelectMenu(Select):
    """Menu for selecting a Pokemon card from search results and previewing it."""
    def __init__(self, cards: List[Pokemon], registry: CardRegistry, config: UserConfig, 
                 parser: CardParser, builder: CardBuilder):
        options = [
            SelectOption(label=c.name, value=str(i))
            for i, c in enumerate(cards[:25])
        ]
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
        self.view = None  # Set by CardSelectView

    async def callback(self, interaction: Interaction):
        """Handle card selection."""
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
    """Button for selecting a card after preview."""
    def __init__(self, idx: int, card: Pokemon, callback):
        super().__init__(
            label="Select",
            style=discord.ButtonStyle.primary,
            custom_id=f"select_{idx}"
        )
        self.card = card
        self.select_callback = callback

    async def callback(self, interaction: discord.Interaction):
        await self.select_callback(interaction, self.card)

class CardSelectView(View):
    """View containing the card selection menu and handling final selection."""
    def __init__(self, cards: List[Pokemon], registry: CardRegistry, config: UserConfig,
                 parser: CardParser, builder: CardBuilder, final_callback):
        super().__init__(timeout=None)
        self.menu = CardSelectMenu(cards, registry, config, parser, builder)
        self.menu.view = self
        self.add_item(self.menu)
        self.final_callback = final_callback

class CardCommands:
    """Handles Pokemon TCG card-related commands."""
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
        self.logger = log or logging.getLogger("red.pokemontcg.commands")
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        """Initialize command dependencies."""
        self.logger.debug("Initializing card commands")

    async def close(self):
        """Cleanup resources."""
        self.logger.debug("Cleaning up card commands")

    async def search_cards(
        self,
        query: str,
        *,
        is_autocomplete: bool = False
    ) -> List[Pokemon]:
        """Search for cards using the registry and fuzzy search."""
        if not query:
            return []
        try:
            self.logger.debug(f"Searching for cards: {query}")
            all_cards = await self.registry.get_all_cards()
            card_dicts = [
                {
                    'id': card.id,
                    'name': card.name,
                    'set_name': card.set_name,
                    'number': card.number,
                    '_card': card  # Store original Pokemon object
                }
                for card in all_cards
            ]
            search_configs = [
                {
                    'key': 'name',
                    'weight': 1.0,
                    'exact_bonus': 0.4
                },
                {
                    'key': 'set_name',
                    'weight': 0.3,
                    'exact_bonus': 0.2
                },
                {
                    'key': 'number',
                    'weight': 0.2,
                    'exact_bonus': 0.2
                }
            ]
            results = fuzzy_search_multi(
                query=query,
                items=card_dicts,
                search_configs=search_configs,
                threshold=0.3,
                max_results=25 if not is_autocomplete else 10
            )
            return [result['_card'] for result in results]
        except Exception as e:
            self.logger.error(f"Error searching cards: {e}", exc_info=True)
            return []

    async def card_name_autocomplete(
        self,
        interaction: Interaction,
        current: str
    ) -> List[Choice[str]]:
        """Provide autocomplete suggestions for card names."""
        try:
            current = current.strip()
            if not current or len(current) < 3:
                return []

            cards = await self.search_cards(current, is_autocomplete=True)
            return [
                Choice(name=card.name, value=card.name)
                for card in cards[:10]
            ]
        except Exception as e:
            self.logger.error(f"Autocomplete error: {e}", exc_info=True)
            return []

    async def text_card(self, ctx: commands.Context, *, query: str = None):
        """Handle text-based card search command."""
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
                embed = await self.builder.build_card_embed(chosen_card, as_full_art=True)
                await interaction.message.edit(embed=embed, view=None)
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
        except Exception as e:
            self.logger.error(f"Error in text_card: {e}", exc_info=True)
            await ctx.send("Something went wrong... 😔")

    async def display_art(
        self,
        ctx: commands.Context,
        card_name: str,
        variant: Optional[int] = 1
    ):
        """Handle card art display command."""
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
                await interaction.message.edit(embed=embed, view=None)

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

        except ValueError as e:
            await ctx.send(f"Art not found for '{card_name}'.")
        except Exception as e:
            self.logger.error(f"Error displaying art: {e}", exc_info=True)
            await ctx.send("Something went wrong while fetching the card art.")

    async def handle_card_mentions(self, message: discord.Message):
        """Handle card mentions in messages using <<card name>> syntax."""
        if message.author.bot:
            return

        try:
            card_names = self.parser.extract_card_names(message.content)
            if not card_names:
                return

            self.logger.debug(f"Found card mentions: {card_names}")
            found_cards = []
            for name in card_names[:5]:  # Limit to 5 cards per message
                cards = await self.search_cards(name)
                if cards:
                    found_cards.append(cards[0])

            if found_cards:
                self.logger.info(f"Responding to {len(found_cards)} card mentions")
                embeds = []
                for pokemon in found_cards:
                    embed = await self.builder.build_card_embed(pokemon, as_full_art=False)
                    embeds.append(embed)
                await message.reply(embeds=embeds)

        except Exception as e:
            self.logger.error(f"Error handling card mentions: {e}", exc_info=True)
