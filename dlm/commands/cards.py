import discord
from discord import app_commands, Interaction, Embed, SelectOption
from discord.ui import View, Select
import logging
from typing import List, Optional, Tuple
from discord.app_commands import Choice

from ..core.models import Card, ALTERNATE_SEARCH_NAMES
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.commands.cards")


def get_level_symbols(card: Card) -> Tuple[str, str]:
    if not card.level:
        return "", ""
    if card.type:
        card_type = card.type.lower()
        if "xyz" in card_type:
            return "★", "Rank"
        elif "link" in card_type:
            return "↯", "Link Rating"
    return "★", "Level"


class CardSelectMenu(Select):
    """
    A dropdown menu of Card objects for ephemeral preview.
    """

    def __init__(self, cards: List[Card]):
        options = []
        for i, card in enumerate(cards[:25]):
            description = []

            # Build short description
            type_parts = []
            if card.attribute:
                type_parts.append(card.attribute)
            if card.race:
                type_parts.append(card.race)
            if card.type:
                type_parts.append(card.type)
            if type_parts:
                description.append(" | ".join(type_parts))

            stats = []
            if card.level:
                symbol, label = get_level_symbols(card)
                stats.append(f"{label} {card.level}")
            if card.atk is not None:
                stats.append(f"ATK:{card.atk}")
            if card.def_ is not None and "link" not in card.type.lower():
                stats.append(f"DEF:{card.def_}")
            if stats:
                description.append(" ".join(stats))

            status = []
            if card.status_tcg:
                status.append(f"TCG:{card.status_tcg}")
            if card.status_ocg:
                status.append(f"OCG:{card.status_ocg}")
            if card.status_md:
                status.append(f"MD:{card.status_md}")
            if card.status_dl:
                status.append(f"DL:{card.status_dl}")
            if status:
                description.append(" ".join(status))

            options.append(
                SelectOption(
                    label=card.name[:100],
                    value=str(i),
                    description=" | ".join(d for d in description if d)[:100],
                )
            )

        super().__init__(
            placeholder="Choose a card to preview...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.cards = cards

    async def callback(self, interaction: Interaction):
        chosen_card = self.cards[int(self.values[0])]
        embed = await self.create_card_embed(chosen_card)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def create_card_embed(self, card: Card) -> Embed:
        embed = Embed(title=card.name, color=self.get_card_color(card))

        # Type/attribute/level, etc.
        type_parts = []
        if card.monster_types:
            type_parts.extend(card.monster_types)
        if card.race:
            type_parts.append(card.race)
        if card.type:
            type_parts.append(card.type)
        if type_parts:
            embed.add_field(name="Type", value=" / ".join(type_parts), inline=True)

        if card.attribute:
            embed.add_field(name="Attribute", value=card.attribute, inline=True)

        if card.level:
            symbol, label = get_level_symbols(card)
            embed.add_field(name=label, value=symbol * card.level, inline=True)

        stats = []
        if card.atk is not None:
            stats.append(f"ATK: {card.atk}")
        if card.def_ is not None and "link" not in card.type.lower():
            stats.append(f"DEF: {card.def_}")
        if card.arrows:
            stats.append(f"Link Arrows: {', '.join(card.arrows)}")
        if stats:
            embed.add_field(name="Stats", value=" / ".join(stats), inline=True)

        if card.scale is not None:
            embed.add_field(name="Pendulum Scale", value=str(card.scale), inline=True)

        # Status fields
        status_fields = []
        if card.status_tcg:
            status_fields.append(("TCG Status", card.status_tcg))
        if card.status_ocg:
            status_fields.append(("OCG Status", card.status_ocg))
        if card.status_goat:
            status_fields.append(("GOAT Status", card.status_goat))
        if card.status_md:
            status_fields.append(("Master Duel", f"Status: {card.status_md}"))
            if card.rarity_md:
                status_fields[-1] = (
                    status_fields[-1][0],
                    f"{status_fields[-1][1]}\nRarity: {card.rarity_md}"
                )
        if card.status_dl:
            status_fields.append(("Duel Links", f"Status: {card.status_dl}"))
            if card.rarity_dl:
                status_fields[-1] = (
                    status_fields[-1][0],
                    f"{status_fields[-1][1]}\nRarity: {card.rarity_dl}"
                )
        for game, status in status_fields:
            embed.add_field(name=game, value=status, inline=True)

        # Text/effect
        if card.description:
            if card.pendulum_effect:
                embed.add_field(
                    name="Pendulum Effect",
                    value=self.format_card_text(card.pendulum_effect),
                    inline=False
                )
                embed.add_field(
                    name="Monster Effect",
                    value=self.format_card_text(card.description),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Effect",
                    value=self.format_card_text(card.description),
                    inline=False
                )

        # Sets
        if card.sets_paper:
            embed.add_field(
                name="TCG/OCG Sets",
                value=", ".join(card.sets_paper)[:1024],
                inline=False
            )
        if card.sets_md:
            embed.add_field(
                name="Master Duel Sets",
                value=", ".join(card.sets_md)[:1024],
                inline=False
            )
        if card.sets_dl:
            embed.add_field(
                name="Duel Links Sets",
                value=", ".join(card.sets_dl)[:1024],
                inline=False
            )

        if card.image_url:
            embed.set_image(url=card.image_url)
        if card.url:
            embed.url = card.url

        return embed

    def get_card_color(self, card: Card) -> int:
        """Assign saved color codes based on card type."""
        colors = {
            "divine-beast": 0xFCBF00,
            "ritual": 0x3B76FF,
            "fusion": 0x7E1CD4,
            "synchro": 0xFFFFFF,
            "xyz": 0x000000,
            "link": 0x00008B,
            "pendulum": 0x7CBA3B,
            "effect": 0xC65F09,
            "normal": 0xF7E99D,
            "spell": 0x1D9E74,
            "trap": 0xBC5C8F,
            "skill": 0x4A4A4A,
        }

        if not card.type:
            return 0x000000

        card_type = card.type.lower()
        for key, color in colors.items():
            if key in card_type:
                return color
        return 0x000000

    def format_card_text(self, text: str) -> str:
        """Split up text for readability."""
        if not text:
            return ""
        text = text.replace(" ● ", "\n● ")
        text = text.replace(":\n", ": ")
        text = text.replace(". ", ".\n")
        text = text.replace("; ", ";\n")

        markers = ["[", "]", "(", ")", "●"]
        for marker in markers:
            text = text.replace(f" {marker}", marker)
            text = text.replace(f"{marker} ", marker)

        if "Once per turn" in text:
            text = text.replace("Once per turn", "\nOnce per turn")
        if "Once while face-up" in text:
            text = text.replace("Once while face-up", "\nOnce while face-up")

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)[:1024]


class CardCommands:
    """
    Commands for searching/previewing Yugioh cards, integrated with your registry.
    """

    def __init__(
        self,
        bot: "Red",
        registry,
        user_config=None
    ):
        self.bot = bot
        self.registry = registry
        self.user_config = user_config

    def get_commands(self) -> List[app_commands.Command]:
        """
        Return all slash commands to register.
        (No 'manager' needed now; we rely on self.registry).
        """
        return [
            self._card_command(),
            self._art_command(),
            self._preview_command()
        ]

    async def card_name_autocomplete(self, interaction: Interaction, current: str) -> List[Choice[str]]:
        """
        Provides autocomplete suggestions by searching in the registry.
        """
        try:
            if not current or len(current) < 2:
                return []

            # 1) exact match
            exact_cards = await self.registry.search_cards(current)
            if exact_cards:
                return [
                    Choice(name=card.name, value=card.name)
                    for card in exact_cards[:25]
                ]

            # 2) fuzzy match
            fuzzy_cards = await self.registry.search_cards(current)
            query_lower = current.lower()
            alt_cards = [
                card for card in ALTERNATE_SEARCH_NAMES
                if fuzzy_search([query_lower], card.name.lower(), threshold=0.3)
            ]

            all_cards = fuzzy_cards + alt_cards
            return [
                Choice(name=card.name, value=card.name)
                for card in all_cards[:25]
            ]

        except Exception as e:
            log.error(f"Autocomplete error: {e}", exc_info=True)
            return []

    def _preview_command(self) -> app_commands.Command:
        """
        /preview <query>
        Allows ephemeral dropdown selection of multiple matched cards.
        """

        @app_commands.command(
            name="preview",
            description="Preview multiple cards matching a search"
        )
        @app_commands.describe(query="Card name to search for")
        async def preview(interaction: Interaction, query: str):
            await interaction.response.defer()
            try:
                # Fuzzy search with the registry
                cards = await self.registry.search_cards(query)
                query_lower = query.lower()
                alt_cards = [
                    c for c in ALTERNATE_SEARCH_NAMES
                    if fuzzy_search([query_lower], c.name.lower(), threshold=0.3)
                ]
                cards.extend(alt_cards)

                if not cards:
                    return await interaction.followup.send(
                        f"No cards found matching '{query}'",
                        ephemeral=True
                    )

                menu = CardSelectMenu(cards)
                view = View()
                view.add_item(menu)
                await interaction.followup.send(
                    f"Found {len(cards)} cards matching '{query}':",
                    view=view,
                    ephemeral=True
                )

            except Exception as e:
                log.error(f"Error in preview command: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while searching for cards",
                    ephemeral=True
                )

        return preview

    def _card_command(self) -> app_commands.Command:
        """
        /card <name>
        Search for a single card by name, or ephemeral dropdown if multiple matches.
        """

        @app_commands.command(
            name="card",
            description="Search for a Yu-Gi-Oh! card by name"
        )
        @app_commands.describe(name="Card name to search for")
        @app_commands.autocomplete(name=self.card_name_autocomplete)
        async def card(interaction: Interaction, name: str):
            await interaction.response.defer()
            try:
                cards = await self.registry.search_cards(name)
                if not cards:
                    # fallback fuzzy
                    cards = await self.registry.search_cards(name)
                    name_lower = name.lower()
                    alt_cards = [
                        c for c in ALTERNATE_SEARCH_NAMES
                        if fuzzy_search([name_lower], c.name.lower(), threshold=0.3)
                    ]
                    cards.extend(alt_cards)

                if not cards:
                    return await interaction.followup.send(
                        f"No cards found matching '{name}'",
                        ephemeral=True
                    )

                if len(cards) == 1:
                    single_card = cards[0]
                    menu = CardSelectMenu([single_card])
                    embed = await menu.create_card_embed(single_card)
                    await interaction.followup.send(embed=embed)
                else:
                    menu = CardSelectMenu(cards)
                    view = View()
                    view.add_item(menu)
                    await interaction.followup.send(
                        f"Found {len(cards)} cards matching '{name}':",
                        view=view,
                        ephemeral=True
                    )

            except Exception as e:
                log.error(f"Error in card command: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while searching for the card",
                    ephemeral=True
                )

        return card

    def _art_command(self) -> app_commands.Command:
        """
        /art <name>
        Show direct artwork or ephemeral list if multiple matches.
        """

        @app_commands.command(
            name="art",
            description="Show card artwork by name"
        )
        @app_commands.describe(name="Card name to search for")
        async def art(interaction: Interaction, name: str):
            await interaction.response.defer()
            try:
                cards = await self.registry.search_cards(name)
                if not cards:
                    # fallback fuzzy
                    cards = await self.registry.search_cards(name)
                    name_lower = name.lower()
                    alt_cards = [
                        c for c in ALTERNATE_SEARCH_NAMES
                        if fuzzy_search([name_lower], c.name.lower(), threshold=0.3)
                    ]
                    cards.extend(alt_cards)

                if not cards:
                    return await interaction.followup.send(
                        f"No cards found matching '{name}'",
                        ephemeral=True
                    )

                if len(cards) == 1:
                    # Send single card art
                    card_data = cards[0]
                    embed = discord.Embed(title=card_data.name)
                    if card_data.image_url:
                        embed.set_image(url=card_data.image_url)
                    else:
                        embed.description = "No art URL found."
                    await interaction.followup.send(embed=embed)
                else:
                    # Show ephemeral dropdown
                    menu = CardSelectMenu(cards)
                    view = View()
                    view.add_item(menu)
                    await interaction.followup.send(
                        f"Found {len(cards)} cards matching '{name}':",
                        view=view,
                        ephemeral=True
                    )

            except Exception as e:
                log.error(f"Error in art command: {e}", exc_info=True)
                await interaction.followup.send(
                    "An error occurred while fetching card art.",
                    ephemeral=True
                )

        return art
