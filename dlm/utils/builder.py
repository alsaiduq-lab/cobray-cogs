import discord
from typing import Optional, List, Dict
from ..core.models import Card, CardSet
from ..utils.images import ImagePipeline

class CardBuilder:
    """Builds Discord embeds for cards and related content."""
    
    FALLBACK_ICONS = {
        "spell": "[Spell]",
        "trap": "[Trap]",
        "skill": "[Skill]",
        "normal": "[N]", 
        "rare": "[R]",
        "super": "[SR]",
        "ultra": "[UR]",
        "semilimited": "[2]",
        "limited": "[1]",
        "forbidden": "[0]",
        "DARK": "[DARK]",
        "DIVINE": "[DIVINE]",
        "EARTH": "[EARTH]",
        "FIRE": "[FIRE]",
        "LIGHT": "[LIGHT]",
        "WATER": "[WATER]",
        "WIND": "[WIND]",
        "Quick-Play": "[Quick]",
        "Ritual": "[Ritual]",
        "Field": "[Field]",
        "Equip": "[Equip]",
        "Continuous": "[Cont]",
        "Counter": "[Counter]"
    }

    TOKEN = "../assets/token.jpg"
    SET_BASE_URL = "https://yugipedia.com/wiki/"

    def __init__(self):
        self.image_pipeline = ImagePipeline()
        self.emoji_cache = {}

    async def initialize(self):
        await self.image_pipeline.initialize()

    async def validate_emojis(self, guild: discord.Guild) -> None:
        """Validate that required emojis exist in the guild."""
        self.emoji_cache = {}
        for emoji in guild.emojis:
            if emoji.name in self.FALLBACK_ICONS:
                self.emoji_cache[emoji.name] = str(emoji)

    def get_icon(self, key: str) -> str:
        """Get emoji if available, otherwise return fallback text."""
        return self.emoji_cache.get(key, self.FALLBACK_ICONS.get(key, ""))

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


    async def get_card_image(self, card_id: int, ocg: bool = False) -> tuple[bool, str]:
        """
        Fetch the card image from the image pipeline.
        Returns OCG art if enabled, otherwise returns TCG art.
        """
        success, url = await self.image_pipeline.get_image_url(card_id, [], ocg=ocg)
        return success, url

    def _add_card_metadata(self, embed: discord.Embed, card: Card, format: str):
        """Add card type, attribute, level, etc to embed."""
        if card.type == "monster":
            level_name = {
                "xyz": "Rank",
                "link": "Link"
            }.get(card.monster_type, "Level")

            attribute_text = f"**Attribute**: {self.get_icon(card.attribute)}"
            if format in ["md", "dl"]:
                rarity = getattr(card, f"rarity_{format}")
                if rarity:
                    attribute_text += f" {self.get_icon(rarity)}"

            description = [
                attribute_text,
                f"**{level_name}**: {card.level} **Type**: {'/'.join([card.race] + (card.monster_types or []))}",
                self._get_status_text(card, format)
            ]
            embed.description = "\n".join(filter(None, description))
        else:
            type_text = f"**Type**: {self.get_icon(card.type)}"
            if card.race:
                type_text += f" {self.get_icon(card.race)}"
            if format in ["md", "dl"]:
                rarity = getattr(card, f"rarity_{format}")
                if rarity:
                    type_text += f" {self.get_icon(rarity)}"

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
                f"**TCG Status**: {self.get_icon(card.status_tcg)}",
                f"**OCG Status**: {self.get_icon(card.status_ocg)}"
            ])
        elif format in ["md", "dl"]:
            status = getattr(card, f"status_{format}")
            return f"**Status**: {self.get_icon(status)}"
        return ""

    def _get_status_icon(self, status: str) -> str:
        """Get icon for card status."""
        return self.get_icon(status) if status else "Unlimited"

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
