from discord import app_commands
from discord.app_commands import Choice
import discord
import logging
from typing import List, Optional

from .registry import CardRegistry
from .bonk import BonkAPI
from ..utils.builder import CardBuilder
from ..utils.parser import CardParser
from .user_config import UserConfig

log = logging.getLogger("red.dlm.interactions")

class InteractionHandler:
    """Handles Discord application commands and interactions."""
    
    def __init__(self, bot, card_registry: CardRegistry, user_config: UserConfig):
        self.bot = bot
        self.registry = card_registry
        self.config = user_config
        self.builder = CardBuilder()
        self.bonk = BonkAPI()
        
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        """Initialize components."""
        await self.builder.initialize()
        await self.bonk.initialize()

    async def close(self):
        """Clean up components."""
        await self.builder.close()
        await self.bonk.close()

    def get_commands(self) -> List[app_commands.Command]:
        """Get all application commands."""
        return [
            self._card_command(),
            self._art_command(),
        ]

    def _card_command(self) -> app_commands.Command:
        """Create the card info command."""
        @app_commands.command(
            name="card",
            description="Get Yu-Gi-Oh! card info"
        )
        @app_commands.describe(
            name="Search a card by name",
            format="Which format of the card game (remembers your last choice)"
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
                cards = self.registry.get_card(name)
                if not cards:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                card = cards[0]

                if card.type == "skill":
                    format = "sd"
                elif format:
                    await self.config.update_last_format(interaction.user.id, format)
                else:
                    format = await self.config.get_user_format(interaction.user.id)

                embed = await self.builder.build_card_embed(card, format)
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error handling card command: {str(e)}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        return card

    def _art_command(self) -> app_commands.Command:
        """Create the card art command."""
        @app_commands.command(
            name="art",
            description="Get Yu-Gi-Oh! card art"
        )
        @app_commands.describe(
            name="Search a card by name",
            ocg="Show the OCG art (not available for all cards)"
        )
        async def art(
            interaction: discord.Interaction, 
            name: str, 
            ocg: bool = False
        ):
            if ocg and not await self.bonk.is_valid_user(interaction.user.id):
                embed = self.builder.build_ocg_reminder_embed(interaction.user.id)
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            try:
                cards = self.registry.get_card(name)
                if not cards:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                card = cards[0]
                card.ocg = ocg

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
                log.error(f"Error handling art command: {str(e)}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        return art

    async def autocomplete_card(
        self, 
        interaction: discord.Interaction, 
        current: str
    ) -> List[Choice[str]]:
        """Handle card name autocomplete."""
        if not current:
            return []
        cards = self.registry.search_cards(current)
        return [
            Choice(name=card.name, value=card.id)
            for card in cards[:25]  # Discord limit
        ]
    async def handle_card_mentions(self, message: discord.Message):
        """Handle card mentions in messages."""
        if message.author.bot:
            return
        card_names = CardParser.extract_card_names(message.content)
        if not card_names:
            return

        try:
            cards = []
            for name in card_names[:10]:
                if found := self.registry.get_card(name):
                    cards.append(found[0])

            if cards:
                embeds = [
                    await self.builder.build_card_embed(card) 
                    for card in cards
                ]
                await message.reply(embeds=embeds)

        except Exception as e:
            log.error(f"Error handling card mentions: {str(e)}", exc_info=True)
