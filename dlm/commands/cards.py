import asyncio
import logging
from typing import List
from urllib.parse import quote

import discord
from discord import Interaction, SelectOption, app_commands
from discord.app_commands import Choice
from discord.ext import commands
from discord.ui import Select, View

from ..core.models import Card
from ..core.registry import CardRegistry
from ..core.user_config import UserConfig
from ..utils.embeds import CardBuilder
from ..utils.fsearch import fuzzy_search
from ..utils.images import ImagePipeline
from ..utils.parser import CardParser
from ..core.ygopro import YGOProAPI

log = logging.getLogger("red.dlm.commands.cards")

class CardSelectMenu(Select):
    def __init__(self, cards, registry, config, parser, card_builder, image_pipeline):
        log.debug(f"Initializing CardSelectMenu with {len(cards)} cards")
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
        self.card_builder = card_builder
        self.image_pipeline = image_pipeline

    async def callback(self, interaction: Interaction):
        log.debug(f"CardSelectMenu callback triggered by {interaction.user}")
        idx = int(self.values[0])
        chosen_card = self.cards[idx]
        log.info(f"User {interaction.user} selected card: {chosen_card.name}")

        if chosen_card.type == "skill":
            chosen_format = "sd"
        else:
            user_format = await self.config.get_user_format(interaction.user.id)
            chosen_format = user_format or "paper"
        log.debug(f"Using format {chosen_format} for card {chosen_card.name}")

        embed = await self.card_builder.build_card_embed(chosen_card, chosen_format)
        embed.url = self._get_card_url(chosen_card.name)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _get_card_url(self, card_name: str) -> str:
        safe_name = quote(card_name)
        return f"https://www.duellinksmeta.com/cards/{safe_name}"

class CardSelectView(View):
    def __init__(self, cards, registry, config, parser, card_builder, image_pipeline):
        log.debug(f"Initializing CardSelectView with {len(cards)} cards")
        super().__init__(timeout=None)
        self.add_item(CardSelectMenu(
            cards, registry, config, parser, card_builder, image_pipeline
        ))

class CardCommands:
    def __init__(self, bot: commands.Bot, registry: CardRegistry, user_config: UserConfig, *, log=None):
        """Initialize CardCommands.
        Args:
            bot: The Red bot instance
            registry: Card registry instance
            user_config: User configuration instance
            log: Optional logger instance
        """
        self.logger = log or logging.getLogger("red.dlm.commands.cards")
        self.logger.info("Initializing CardCommands")
        self.bot = bot
        self.registry = registry
        self.ygopro_api = YGOProAPI(log=self.logger)
        self.config = user_config
        self.parser = CardParser(log=self.logger)
        self.card_builder = CardBuilder(log=self.logger)
        self.image_pipeline = ImagePipeline(log=self.logger)
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        log.info("Initializing CardCommands dependencies")
        await self.image_pipeline.initialize()
        await self.ygopro_api.initialize()
        await self.card_builder.initialize()

    async def close(self):
        log.info("Closing CardCommands and cleaning up resources")
        await self.image_pipeline.close()
        await self.ygopro_api.close()
        await self.card_builder.close()
        if hasattr('cache'):
            self.core.cache.clear()

    def _get_card_url(self, card_name: str) -> str:
        safe_name = quote(card_name)
        return f"https://www.duellinksmeta.com/cards/{safe_name}"

    def get_commands(self) -> List[app_commands.Command]:
        log.debug("Registering card commands")
        return [
            self._card_command(),
            self._art_command()
        ]

    async def quick_search(self, query: str) -> List[Card]:
        log.debug(f"Performing quick search for query: {query}")
        if not query:
            return []

        all_cards = getattr(self.registry, "_cards", {})
        card_dicts = [
            {"name": card.name, "id": card.id}
            for card in all_cards.values()
        ]

        fuzzy_results = fuzzy_search(
            query=query,
            items=card_dicts,
            key="name",
            threshold=0.3,
            max_results=25,
            exact_bonus=0.3
        )

        return [
            all_cards[res["id"]]
            for res in fuzzy_results
            if res["id"] in all_cards
        ]

    async def text_card(self, ctx: commands.Context, *, query: str = None):
        log.debug(f"Text card search requested for query: {query}")
        if not query:
            return await ctx.send("❗ You must provide a card name!")
        try:
            cards = await self.search_cards(query)
            if not cards:
                log.info(f"No results found for query: {query}")
                return await ctx.send(f"No results found for '{query}'.")
            found = cards[0]
            if found.type == "skill":
                chosen_format = "sd"
            else:
                chosen_format = await self.config.get_user_format(ctx.author.id) or "paper"
            log.debug(f"Building embed for card {found.name} in format {chosen_format}")
            embed = await self.card_builder.build_card_embed(found, chosen_format)
            embed.url = self._get_card_url(found.name)
            await ctx.send(embed=embed)
        except Exception as e:
            log.error(f"Error in text_card: {e}", exc_info=True)
            await ctx.send("Something went wrong... :pensive:")

    async def card_name_autocomplete(self, interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
        log.debug(f"Autocomplete requested for query: {current}")
        try:
            current = current.strip()
            if not current or len(current) < 3:
                return []

            cached_results = await self.quick_search(current)
            if cached_results:
                log.debug(f"Found {len(cached_results)} cached results")
                return [Choice(name=card.name, value=card.name)
                       for card in cached_results[:25]]

            if ' ' in current or not current.replace(' ', '').isalnum():
                return []
            try:
                async with asyncio.timeout(1.5):
                    log.debug(f"Querying YGOPro API for: {current}")
                    result = await self.registry.ygopro_api._make_request(
                        f"{self.registry.ygopro_api.BASE_URL}/cardinfo.php",
                        params={"fname": current},
                        request_headers={'Cache-Control': 'no-cache'}
                    )
                    if result and "data" in result:
                        matches = fuzzy_search(
                            query=current,
                            items=result["data"],
                            key="name",
                            threshold=0.2,
                            max_results=25,
                            exact_bonus=0.5,
                            )
                        if matches:
                            log.debug(f"Found {len(matches)} API matches")
                            asyncio.create_task(self._cache_results(matches))
                            return [Choice(name=match["name"], value=match["name"])
                                   for match in matches]
            except asyncio.TimeoutError:
                log.warning(f"YGOPro API search timed out for query: {current}")
            except Exception as e:
                log.error(f"YGOPro API search error for query '{current}': {e}")

            return []

        except Exception as e:
            log.error(f"Autocomplete error for query '{current}': {e}", exc_info=True)
            return []

    async def _cache_results(self, results: List[dict]):
        log.debug(f"Caching {len(results)} results")
        try:
            for result in results:
                if card := await self.registry._process_card_data(result):
                    self.registry._cards[card.id] = card
                    self.registry._generate_index_for_cards([card])
        except Exception as e:
            log.error(f"Error caching results: {e}")

    def _card_command(self) -> app_commands.Command:
        @app_commands.command(
            name="card",
            description="Search for a card by name."
        )
        @app_commands.describe(
            name="Partial or full card name to find matches."
        )
        @app_commands.autocomplete(name=self.card_name_autocomplete)
        async def card_command(interaction: Interaction, name: str):
            log.debug(f"Card command invoked by {interaction.user} for {name}")
            await interaction.response.defer(ephemeral=False)

            try:
                cards = await self.search_cards(name)
                if not cards:
                    log.info(f"No results found for card search: {name}")
                    return await interaction.followup.send(
                        f"No results found for '{name}'.",
                        ephemeral=True
                    )

                exact_match = next((c for c in cards if c.name.lower() == name.lower()), None)
                card = exact_match or cards[0]
                log.info(f"Selected card: {card.name} (exact match: {bool(exact_match)})")

                if card.type == "skill":
                    chosen_format = "sd"
                else:
                    chosen_format = await self.config.get_user_format(interaction.user.id) or "paper"

                log.debug(f"Building embed for card {card.name} in format {chosen_format}")
                embed = await self.card_builder.build_card_embed(card, chosen_format)
                embed.url = self._get_card_url(card.name)

                await interaction.followup.send(embed=embed)

            except Exception as err:
                log.error(f"Error in card command: {err}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while processing your request.",
                    ephemeral=True
                )
        return card_command

    def _art_command(self) -> app_commands.Command:
        @app_commands.command(
            name="art",
            description="Get Yu-Gi-Oh! card art"
        )
        @app_commands.describe(
            name="Name of the card",
            ocg="Show OCG variant if available"
        )
        @app_commands.autocomplete(name=self.card_name_autocomplete)
        async def art(interaction: Interaction, name: str, ocg: bool = False):
            log.debug(f"Art command invoked by {interaction.user} for {name} (OCG: {ocg})")
            await interaction.response.defer()

            try:
                # First try to search for the card
                cards = await self.search_cards(name)

                # Added (fuzzy fallback):
                if not cards:
                    log.info(f"No results from registry for '{name}' (art), using local fuzzy_search")
                    cards = await self.quick_search(name)

                if not cards:
                    log.info(f"No results found (even with fuzzy) for art search: '{name}'")
                    return await interaction.followup.send(
                        f"No results found for '{name}'.",
                        ephemeral=True
                    )

                # Get exact match or first result
                exact_match = next((c for c in cards if c.name.lower() == name.lower()), None)
                card = exact_match or cards[0]

                log.debug(f"Fetching {'OCG' if ocg else 'TCG'} art for {card.name}")
                try:
                    async with asyncio.timeout(5.0):
                        found, url = await self.image_pipeline.get_image_url(
                            card.id,
                            card.monster_types or [],
                            ocg=ocg
                        )
                except asyncio.TimeoutError:
                    log.warning(f"Image fetch timed out for {card.name}")
                    return await interaction.followup.send(
                        "Request timed out while fetching card art. Please try again.",
                        ephemeral=True
                    )

                if not found:
                    log.info(f"Art not found for {card.name} (OCG: {ocg})")
                    return await interaction.followup.send(
                        f"{'OCG ' if ocg else ''}Art for '{card.name}' not found.",
                        ephemeral=True
                    )

                embed = self.card_builder.build_art_embed(card, url)
                embed.url = self._get_card_url(card.name)
                await interaction.followup.send(embed=embed)

            except Exception as err:
                log.error(f"Error in /art command: {err}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong while fetching the card art. Please try again later.",
                    ephemeral=True
                )

        return art

    async def handle_card_mentions(self, message):
        if message.author.bot:
            return
        try:
            card_names = self.parser.extract_card_names(message.content)
            if not card_names:
                return

            log.debug(f"Found card mentions in message: {card_names}")
            found_cards = []
            for name in card_names[:10]:
                c = await self.registry.get_card(name)
                if c:
                    found_cards.append(c)

            if found_cards:
                log.info(f"Responding to {len(found_cards)} card mentions")
                embeds = []
                for c in found_cards:
                    embed = await self.card_builder.build_card_embed(c)
                    embed.url = self._get_card_url(c.name)
                    embeds.append(embed)
                await message.reply(embeds=embeds)

        except Exception as err:
            log.error(f"Error handling card mentions: {err}", exc_info=True)
    async def search_cards(self, query: str, *, is_autocomplete: bool = False) -> List[Card]:
        """
        Search for cards using fuzzy matching, combining local cache and API results.
        Args:
            query: The search query string
            is_autocomplete: Whether this is an autocomplete request
        Returns:
            List[Card]: List of matching cards
        """
        if not query:
            return []

        if self.registry._cards:
            card_dicts = [
                {
                    "name": card.name,
                    "id": card.id
                }
                for card in self.registry._cards.values()
            ]
            local_matches = fuzzy_search(
                query=query,
                items=card_dicts,
                key="name",
                threshold=0.4,
                max_results=25 if is_autocomplete else 10,
                exact_bonus=0.3
            )
            if local_matches:
                return [self.registry._cards[match["id"]] for match in local_matches]

        if len(query) >= 3:
            try:
                self.logger.info(f"Searching YGOPro API for: {query}")
                async with asyncio.timeout(2.0):
                    cards = await self.ygopro_api.search_cards(query, is_autocomplete=is_autocomplete)
                    if cards:
                        self.logger.info(f"Found {len(cards)} cards from YGOPro API")
                        # Cache the results for future use
                        for card in cards:
                            if card and card.id:
                                self.registry._cards[card.id] = card
                                self.registry._generate_index_for_cards([card])
                        return cards[:10]  # Limit to first 10 results
            except asyncio.TimeoutError:
                self.logger.warning(f"YGOPro API search timed out for query: {query}")
            except Exception as e:
                self.logger.error(f"Error searching cards via API: {e}", exc_info=True)
        return []
