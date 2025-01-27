from discord import app_commands
from discord.app_commands import Choice
import discord
import logging
from typing import List, Optional

from .registry import CardRegistry
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
        # Listen for card mentions in normal chat messages
        self.bot.listen('on_message')(self.handle_card_mentions)

    async def initialize(self):
        """Initialize components and register slash commands."""
        await self.builder.initialize()

        # Register slash commands
        commands = self.get_commands()
        command_tree = self.bot.tree

        for command in commands:
            log.info(f"Registering slash command '{command.name}'")
            command_tree.add_command(command)

        # Sync global slash commands
        log.info("Syncing global slash commands...")
        await command_tree.sync()

        # Optional: If you want them as guild commands for instant updates,
        # replace the above sync() call with:
        # guild_id = 123456789012345678  # your testing guild
        # await command_tree.sync(guild=discord.Object(id=guild_id))
        # This will make them appear immediately in that guild
        # rather than taking up to an hour to propagate globally.

    async def close(self):
        """Clean up components."""
        await self.builder.close()

    def get_commands(self) -> List[app_commands.Command]:
        """Return a list of all slash commands in this handler."""
        return [
            self._card_command(),
            self._art_command(),
        ]

    def _card_command(self) -> app_commands.Command:
        """Create the 'card' slash command."""
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
                # Always await get_card if it's async and returns a single Card/None
                card = await self.registry.get_card(name)
                if not card:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                # If the card is a Skill, force format = 'sd'
                if card.type == "skill":
                    format = "sd"
                elif format:
                    await self.config.update_last_format(interaction.user.id, format)
                else:
                    # If the user didn't specify, get their preferred format
                    format = await self.config.get_user_format(interaction.user.id)

                embed = await self.builder.build_card_embed(card, format)
                await interaction.followup.send(embed=embed)

            except Exception as e:
                log.error(f"Error handling /card command: {str(e)}", exc_info=True)
                await interaction.followup.send(
                    "Something went wrong... :pensive:",
                    ephemeral=True
                )

        return card

    def _art_command(self) -> app_commands.Command:
        """Create the 'art' slash command."""
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
                card = await self.registry.get_card(name)
                if not card:
                    await interaction.followup.send(
                        f"`{name}` not found... :pensive:",
                        ephemeral=True
                    )
                    return

                # Mark the card to use OCG art if requested
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
                log.error(f"Error handling /art command: {str(e)}", exc_info=True)
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
        """Handle card name autocomplete (if your /card command has autocomplete)."""
        if not current:
            return []
        # If your registry has a synchronous search_cards, it's fine to call it directly.
        # If it’s async, await it here.
        cards = self.registry.search_cards(current)
        return [
            Choice(name=card.name, value=card.id)
            for card in cards[:25]
        ]

    async def handle_card_mentions(self, message: discord.Message):
        """
        Automatically embed card details if someone types "[card name]" in chat.
        This only runs for normal chat messages (not slash commands).
        """
        if message.author.bot:
            return
        card_names = CardParser.extract_card_names(message.content)
        if not card_names:
            return

        try:
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
                await message.reply(embeds=embeds)

        except Exception as e:
            log.error(f"Error handling card mentions: {str(e)}", exc_info=True)
