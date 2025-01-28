from discord import app_commands, Interaction, Embed, ui, ButtonStyle
from discord.app_commands import Choice
import discord
from redbot.core import commands
import logging
import asyncio
from typing import List, Optional

from .registry import CardRegistry
from ..utils.builder import CardBuilder
from ..utils.parser import CardParser
from .user_config import UserConfig

log = logging.getLogger("red.dlm.interactions")

class CardSearchModal(ui.Modal, title="Search Cards"):
    def __init__(self, view: 'CardSearchView'):
        super().__init__()
        self.view = view
        self.name = ui.TextInput(
            label="Card Name",
            placeholder="Type to search...",
            min_length=2,
            max_length=100
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.search_and_update(self.name.value)

class CardSearchView(ui.View):
    def __init__(self, registry: CardRegistry, builder: CardBuilder):
        super().__init__(timeout=180)
        self.registry = registry
        self.builder = builder
        self.message = None
        self.current_card = None
        self.search_task = None
        self.name = None

    @ui.button(label="Search", style=ButtonStyle.primary)
    async def search_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = CardSearchModal(self)
        await interaction.response.send_modal(modal)

    async def search_and_update(self, value: str):
        if len(value) < 2:
            return
        self.name = value
        if self.search_task and not self.search_task.done():
            self.search_task.cancel()
        await asyncio.sleep(0.5)
        cards = self.registry.search_cards(value)
        if not cards:
            await self.update_preview(None)
            return
        self.current_card = cards[0]
        await self.update_preview(self.current_card)

    async def update_preview(self, card):
        if not self.message:
            return
        if not card:
            await self.message.edit(content="No cards found.", embed=None)
            return
        embed = await self.builder.build_card_embed(card)
        await self.message.edit(content=None, embed=embed)

    @ui.button(label="Previous", style=ButtonStyle.gray)
    async def previous_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        cards = self.registry.search_cards(self.name)
        if not cards:
            return
        current_idx = next((i for i, c in enumerate(cards) if c.id == self.current_card.id), -1)
        if current_idx > 0:
            self.current_card = cards[current_idx - 1]
            await self.update_preview(self.current_card)

    @ui.button(label="Next", style=ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        cards = self.registry.search_cards(self.name)
        if not cards:
            return
        current_idx = next((i for i, c in enumerate(cards) if c.id == self.current_card.id), -1)
        if current_idx < len(cards) - 1:
            self.current_card = cards[current_idx + 1]
            await self.update_preview(self.current_card)

    async def on_timeout(self):
        if self.message:
            await self.message.edit(view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user == self.message.interaction.user

class InteractionHandler:
    def __init__(self, bot: commands.Bot, card_registry: CardRegistry, user_config: UserConfig):
        self.bot = bot
        self.registry = card_registry
        self.config = user_config
        self.builder = CardBuilder()
        self.parser = CardParser()
        self.bot.listen('on_message')(self.handle_card_mentions)

    def _get_card_url(self, card_name: str) -> str:
        clean_name = card_name.lower()
        url_name = clean_name.replace(" ", "-")
        return f"https://www.duellinksmeta.com/cards/{url_name}"

    async def search_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete function to suggest card names
        based on whatever user has typed into "card_name."
        """
        if not current:
            return []
        cards = self.registry.search_cards(current)
        return [
            app_commands.Choice(name=card.name, value=card.name)
            for card in cards[:25]
        ]

    async def initialize(self):
        await self.builder.initialize()

    async def close(self):
        await self.builder.close()

    def get_commands(self) -> List[app_commands.Command]:
        return [
            self._card_command(),
            self._art_command(),
            self._search_command(),
        ]

    def _search_command(self) -> app_commands.Command:
        @app_commands.command(
            name="search",
            description="Search for cards with live preview"
        )
        async def search(interaction: discord.Interaction, card_name: str = None):
            """
            Actual "search" slash command logic.
            Using autocomplete for 'card_name' with self.search_autocomplete.
            """
            if card_name:
                card = await self.registry.get_card(card_name)
                if card:
                    embed = await self.builder.build_card_embed(card)
                    embed.url = self._get_card_url(card.name)
                    await interaction.response.send_message(embed=embed)
                    return

            view = CardSearchView(self.registry, self.builder)
            await interaction.response.send_message(
                "Search for a card:",
                view=view,
                ephemeral=True
            )
            view.message = await interaction.original_response()

        search.autocomplete("card_name")(self.search_autocomplete)
        return search

    def _card_command(self) -> app_commands.Command:
        @app_commands.command(
            name="card",
            description="Get Yu-Gi-Oh! card info"
        )
        @app_commands.describe(
            name="Name of the card you want",
            format="Which version of the card game (remembers your last choice)"
        )
        @app_commands.choices(format=[
            Choice(name="Paper", value="paper"),
            Choice(name="Master Duel", value="md"),
            Choice(name="Duel Links", value="dl")
        ])
        async def card(
            interaction: discord.Interaction,
            name: str,
            format: Optional[str] = None
        ):
            await interaction.response.defer()

            try:
                parsed = self.parser.parse_card_query(name)
                card = await self.registry.get_card(parsed["query"])
                if not card:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                if card.type == "skill":
                    format = "sd"
                elif format:
                    await self.config.update_last_format(interaction.user.id, format)
                else:
                    format = await self.config.get_user_format(interaction.user.id)

                embed = await self.builder.build_card_embed(card, format)
                embed.url = self._get_card_url(card.name)
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error handling /card command: {str(e)}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )
        return card

    def _art_command(self) -> app_commands.Command:
        @app_commands.command(
            name="art",
            description="Get Yu-Gi-Oh! card art"
        )
        @app_commands.describe(
            name="Name of the card",
            ocg="Show the OCG art (not available for all cards)"
        )
        async def art(
            interaction: discord.Interaction,
            name: str,
            ocg: bool = False
        ):
            await interaction.response.defer()

            try:
                parsed = self.parser.parse_card_query(name)
                card = await self.registry.get_card(parsed["query"])
                if not card:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                success, url = await self.builder.get_card_image(card.id, ocg)
                if not success:
                    await interaction.followup.send(
                        f"{'OCG ' if ocg else ''}Art for `{card.name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                embed = self.builder.build_art_embed(card, url)
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error handling /art command: {str(e)}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )
        return art

    async def handle_card_mentions(self, message: discord.Message):
        if message.author.bot:
            return

        try:
            card_names = self.parser.extract_card_names(message.content)
            if not card_names:
                return

            found_cards = []
            for name in card_names[:10]:
                card = await self.registry.get_card(name)
                if card:
                    found_cards.append(card)

            if found_cards:
                embeds = [
                    await self.builder.build_card_embed(card)
                    for card in found_cards
                ]
                for embed in embeds:
                    embed.url = self._get_card_url(embed.title)
                await message.reply(embeds=embeds)

        except Exception as e:
            log.error(f"Error handling card mentions: {str(e)}", exc_info=True)
