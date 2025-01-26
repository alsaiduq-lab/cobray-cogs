import discord
from typing import Optional, List, Dict
from ..core.models import Card, CardSet
from ..utils.images import ImagePipeline

class CardBuilder:
    """Builds Discord embeds for cards and related content."""

    SPELL_TRAP_ICONS = {
        "spell": "<:spell:948992874438070342>",
        "trap": "<:trap:948992874438074428>",
        "skill": "Skill"
    }

    RARITY_ICONS = {
        "normal": "<:normalrare:948990033321414678>",
        "rare": "<:rare:948990141786095667>",
        "super": "<:superrare:948990076111712356>",
        "ultra": "<:ultrarare:948990098920333332>"
    }

    STATUS_ICONS = {
        "semilimited": "<:semilimited:948990692842156043>",
        "limited": "<:limited:948990713272602695>",
        "forbidden": "<:forbidden:948990744373387386>"
    }

    ATTRIBUTE_ICONS = {
        "DARK": "<:DARK:948992874400346152>",
        "DIVINE": "<:DIVINE:948992874089947136>",
        "EARTH": "<:EARTH:948992874442285096>",
        "FIRE": "<:FIRE:948992874375176212>",
        "LIGHT": "<:LIGHT:948992874396151879>",
        "WATER": "<:WATER:948992874136096768>",
        "WIND": "<:WIND:948992874123505775>"
    }

    CARD_TYPE_ICONS = {
        "Normal": "",
        "Quick-Play": "<:quickplay:948992874366771240>",
        "Ritual": "<:ritual:948992874580680786>",
        "Field": "<:field:948992874169630750>",
        "Equip": "<:equip:948992874039623741>",
        "Continuous": "<:continuous:948992874421305385>",
        "Counter": "<:counter:948992874400321617>"
    }

    HAT_TOKEN = "https://s3.lain.dev/ygo/hat-token.webp"
    SET_BASE_URL = "https://yugipedia.com/wiki/"

    def __init__(self):
        self.image_pipeline = ImagePipeline()

    async def initialize(self):
        await self.image_pipeline.initialize()

    async def close(self):
        await self.image_pipeline.close()

    async def build_card_embed(self, card: Card, format: str = "paper") -> discord.Embed:
        """Build a Discord embed for a card."""
        embed = discord.Embed(title=card.name, url=card.url)

        success, url = await self.image_pipeline.get_image_url(card.id, card.monster_types or [])
        embed.set_thumbnail(url=url if success else self.HAT_TOKEN)

        if color := self._get_card_color(card):
            embed.color = color

        self._add_card_metadata(embed, card, format)
        if card.pendulum_effect:
            embed.add_field(name="Pendulum Effect", value=card.pendulum_effect)

        self._add_card_description(embed, card)

        if card.scale:
            embed.add_field(name="Scale", value=str(card.scale), inline=True)
        if card.arrows:
            embed.add_field(name="Arrows", value=" ".join(card.arrows), inline=True)

        self._add_monster_stats(embed, card)

        if sets := self._build_sets_text(card, format):
            embed.add_field(name="Released in", value=sets)

        embed.set_footer(text=f"Format: {format.title()}")

        return embed

    def _add_card_metadata(self, embed: discord.Embed, card: Card, format: str):
        """Add card type, attribute, level, etc to embed."""
        if card.type == "monster":
            level_name = {
                "xyz": "Rank",
                "link": "Link"
            }.get(card.monster_type, "Level")

            attribute_text = f"**Attribute**: {self.ATTRIBUTE_ICONS.get(card.attribute, '')}"
            if format in ["md", "dl"]:
                rarity = getattr(card, f"rarity_{format}")
                if rarity:
                    attribute_text += f" {self.RARITY_ICONS.get(rarity, '')}"

            description = [
                attribute_text,
                f"**{level_name}**: {card.level} **Type**: {'/'.join([card.race] + (card.monster_types or []))}",
                self._get_status_text(card, format)
            ]
            embed.description = "\n".join(filter(None, description))
        else:
            type_text = f"**Type**: {self.SPELL_TRAP_ICONS.get(card.type, '')}"
            if card.race:
                type_text += f" {self.CARD_TYPE_ICONS.get(card.race, '')}"
            if format in ["md", "dl"]:
                rarity = getattr(card, f"rarity_{format}")
                if rarity:
                    type_text += f" {self.RARITY_ICONS.get(rarity, '')}"

            description = [
                type_text,
                self._get_status_text(card, format)
            ]
            embed.description = "\n".join(filter(None, description))

    def _add_card_description(self, embed: discord.Embed, card: Card):
        """Add card description to embed."""
        if card.type == "monster" and "Normal" in (card.monster_types or []):
            embed.add_field(name="Flavor Text", value=card.description)
        elif card.type == "monster":
            embed.add_field(name="Monster Effect", value=card.description)
        else:
            embed.add_field(name="Effect", value=card.description)

    def _add_monster_stats(self, embed: discord.Embed, card: Card):
        """Add ATK/DEF or Link stats for monsters."""
        if card.type != "monster":
            return
        if card.monster_type == "link" and card.atk:
            embed.add_field(name="ATK", value=str(card.atk), inline=True)
        elif card.atk and hasattr(card, "def_"):
            embed.add_field(name="ATK / DEF", value=f"{card.atk} / {card.def_}", inline=True)

    def _get_status_text(self, card: Card, format: str) -> str:
        """Get ban status text for format."""
        if format == "paper":
            return "\n".join([
                f"**TCG Status**: {self._get_status_icon(card.status_tcg)}",
                f"**OCG Status**: {self._get_status_icon(card.status_ocg)}"
            ])
        elif format in ["md", "dl"]:
            status = getattr(card, f"status_{format}")
            return f"**Status**: {self._get_status_icon(status)}"
        return ""

    def _get_status_icon(self, status: str) -> str:
        """Get icon for card status."""
        return self.STATUS_ICONS.get(status, "Unlimited")

    def _build_sets_text(self, card: Card, format: str) -> Optional[str]:
        """Build text showing card's set releases."""
        sets = []
        if format in ["paper", "sd"]:
            sets = [f"[{s}]({self.SET_BASE_URL}{s})" for s in (card.sets_paper or [])]
        elif format == "md":
            sets = [s.name for s in (card.sets_md or [])]
        elif format == "dl":
            sets = [s.name for s in (card.sets_dl or [])]

        if not sets:
            return "Unreleased"

        sets = sets[:5]
        text = ", ".join(sets)
        return text

    @staticmethod
    def _get_card_color(card: Card) -> Optional[int]:
        """Get embed color based on card type."""
        if card.type == "spell":
            return 0x1DA353
        elif card.type == "trap":
            return 0xBC5A84
        elif card.type == "skill":
            return 0x6694
        elif card.type == "monster":
            return {
                "normal": 0xE4C77B,
                "effect": 0xB85C1C,
                "fusion": 0x7E1DDB,
                "ritual": 0x2A5B98,
                "synchro": 0xBEBEBE,
                "xyz": 0x000000,
                "link": 0x00008B,
                "pendulum": 0x40E0D0
            }.get(card.monster_type)
        return None
