import discord
from discord import app_commands, Interaction, Embed, SelectOption, NotFound
from discord.ui import View, Select
from discord.ext import commands
import logging
from typing import List, Optional
from discord.app_commands import Choice
import asyncio
from ..utils.parser import CardParser
from ..utils.embeds import format_card_embed, build_art_embed
from ..utils.builder import CardBuilder
from ..core.registry import CardRegistry
from ..core.user_config import UserConfig
from ..utils.fsearch import fuzzy_search
from ..utils.images import ImagePipeline
from ..core.models import Card

log = logging.getLogger("red.dlm.commands.cards")

class CardSelectMenu(Select):
    def __init__(self, cards, registry, builder, config, parser, image_pipeline):
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
        self.builder = builder
        self.config = config
        self.parser = parser
        self.image_pipeline = image_pipeline

    async def callback(self, interaction: Interaction):
        idx = int(self.values[0])
        chosen_card = self.cards[idx]

        if chosen_card.type == "skill":
            chosen_format = "sd"
        else:
            user_format = await self.config.get_user_format(interaction.user.id)
            chosen_format = user_format or "paper"

        embed = await self.builder.build_card_embed(chosen_card, chosen_format)
        embed.url = f"https://www.duellinksmeta.com/cards/{chosen_card.name.replace(' ', '-').lower()}"

        card_id = getattr(chosen_card, "id", None)
        monster_types = getattr(chosen_card, "monster_types", [])
        if card_id:
            found, image_url = await self.image_pipeline.get_image_url(
                card_id, monster_types, ocg=False
            )
            if found and image_url:
                embed.set_image(url=image_url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class CardSelectView(View):
    def __init__(self, cards, registry, builder, config, parser, image_pipeline):
        super().__init__(timeout=None)
        self.add_item(CardSelectMenu(
            cards, registry, builder, config, parser, image_pipeline
        ))

class CardCommands:
    def __init__(self, bot: commands.Bot, registry: CardRegistry, user_config: UserConfig):
        self.bot = bot
        self.registry = registry
        self.config = user_config
        self.parser = CardParser()
        self.builder = CardBuilder()
        self.image_pipeline = ImagePipeline()
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        await self.builder.initialize()
        await self.image_pipeline.initialize()

    async def close(self):
        await self.builder.close()
        await self.image_pipeline.close()
        if hasattr(self.registry.ygopro_api, 'cache'):
            self.registry.ygopro_api.cache.clear()

    def _get_card_url(self, card_name: str) -> str:
        clean_name = card_name.lower()
        url_name = clean_name.replace(" ", "-")
        return f"https://www.duellinksmeta.com/cards/{url_name}"

    def get_commands(self) -> List[app_commands.Command]:
        return [
            self._card_command(),
            self._art_command()
        ]

    async def quick_search(self, query: str) -> List[Card]:
        if not query:
            return []
        card_dicts = [
            {"name": card.name, "id": card.id}
            for card in self._cards.values()
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
            self._cards[res["id"]]
            for res in fuzzy_results
            if res["id"] in self._cards
        ]

    async def text_card(self, ctx: commands.Context, *, query: str = None):
        if not query:
            return await ctx.send("❗ You must provide a card name!")
        try:
            cards = await self.registry.search_cards(query)
            if not cards:
                return await ctx.send(f"No results found for '{query}'.")
            found = cards[0]
            if found.type == "skill":
                chosen_format = "sd"
            else:
                chosen_format = await self.config.get_user_format(ctx.author.id) or "paper"
            embed = await self.builder.build_card_embed(found, chosen_format)
            embed.url = self._get_card_url(found.name)
            await ctx.send(embed=embed)
        except Exception as e:
            log.error(f"Error in text_card: {e}", exc_info=True)
            await ctx.send("Something went wrong... :pensive:")

    async def card_name_autocomplete(self, interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
        try:
            current = current.strip()
            if not current or len(current) < 3:
                return []

            cached_results = await self.registry.quick_search(current)
            if cached_results:
                return [Choice(name=card.name, value=card.name) 
                       for card in cached_results[:25]]

            if ' ' in current or not current.replace(' ', '').isalnum():
                return []
            try:
                async with asyncio.timeout(1.5):
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
                            threshold=0.3,
                            max_results=25,
                            exact_bonus=0.3
                        )
                        
                        if matches:
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
            cards = await self.registry.search_cards(name)
            if not cards:
                return await interaction.response.send_message(
                    f"No results found for '{name}'.",
                    ephemeral=True
                )

            exact_match = next((c for c in cards if c.name.lower() == name.lower()), None)
            card = exact_match or cards[0]
            if card.type == "skill":
                chosen_format = "sd"
            else:
                chosen_format = await self.config.get_user_format(interaction.user.id) or "paper"
            embed = await self.builder.build_card_embed(card, chosen_format)
            embed.url = self._get_card_url(card.name)
            card_id = getattr(card, "id", None)
            if card_id:
                found, image_url = await self.image_pipeline.get_image_url(
                    card_id, card.monster_types or [], ocg=False
                )
                if found and image_url:
                    embed.set_image(url=image_url)

            await interaction.response.send_message(embed=embed)

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
        async def art(interaction: Interaction, name: str, ocg: bool = False):
            await interaction.response.defer()
            try:
                parsed = self.parser.parse_card_query(name)
                card = await self.registry.get_card(parsed["query"])
                if not card:
                    return await interaction.followup.send(
                        f"No results found for '{name}'.",
                        ephemeral=True
                    )

                found, url = await self.builder.get_card_image(card.id, ocg)

                if not found:
                    return await interaction.followup.send(
                        f"{'OCG ' if ocg else ''}Art for '{card.name}' not found.",
                        ephemeral=True
                    )

                embed = self.builder.build_art_embed(card, url)
                await interaction.followup.send(embed=embed)

            except Exception as err:
                log.error(f"Error in /art command: {err}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
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

            found_cards = []
            for name in card_names[:10]:
                c = await self.registry.get_card(name)
                if c:
                    found_cards.append(c)

            if found_cards:
                embeds = []
                for c in found_cards:
                    embed = await self.builder.build_card_embed(c)
                    embed.url = self._get_card_url(c.name)
                    embeds.append(embed)
                await message.reply(embeds=embeds)

        except Exception as err:
            log.error(f"Error handling card mentions: {err}", exc_info=True)
