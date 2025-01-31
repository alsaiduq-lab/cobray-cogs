import re
import discord
from discord import Embed, Color
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
import logging
from ..core.models import Card
from ..utils.images import ImagePipeline

URL_CLEAN_PATTERN = re.compile(r'["\'\?\.,!]|%20')


def create_tournament_embeds(tournaments: List[Dict[str, Any]], title: str) -> List[Embed]:
    """Format tournaments into Discord embeds.
    
    Args:
        tournaments: List of tournament dictionaries containing tournament data
        title: Title to use for the embed series
        
    Returns:
        List of Discord Embed objects
    """
    embeds = []
    
    for tournament in tournaments:
        if not tournament or not tournament.get("name") or not tournament.get("start_date"):
            continue

        try:
            start_dt = datetime.fromisoformat(tournament["start_date"].replace("Z", "+00:00"))
            start_timestamp = f"<t:{int(start_dt.timestamp())}:F>"

            embed = Embed(
                title=tournament["name"],
                url=f"https://www.duellinksmeta.com{tournament.get('url', '')}",
                description=tournament.get("description", "No description available."),
                color=Color.gold()
            )

            if status := tournament.get("status"):
                embed.add_field(name="Status", value=status.title(), inline=True)

            if format := tournament.get("format"):
                embed.add_field(name="Format", value=format.title(), inline=True)

            if entry_fee := tournament.get("entry_fee"):
                embed.add_field(name="Entry Fee", value=entry_fee, inline=True)

            if prize_pool := tournament.get("prize_pool"):
                embed.add_field(name="Prize Pool", value=prize_pool, inline=True)

            if players := tournament.get("players"):
                embed.add_field(name="Players", value=str(players), inline=True)

            embed.add_field(name="Start Time", value=start_timestamp, inline=True)

            if image := tournament.get("image"):
                embed.set_thumbnail(url=f"https://www.duellinksmeta.com{image}")

            embeds.append(embed)
        except Exception as e:
            log.error(f"Failed to create tournament embed: {str(e)}")
            continue
            
    return embeds

def clean_url(text: str) -> str:
    """Convert text to URL-friendly format."""
    cleaned = URL_CLEAN_PATTERN.sub('', text.lower())
    return cleaned.replace(' ', '%20')

def format_article_embed(article: Dict[str, Any]) -> Embed:
    """Format an article into a Discord embed."""
    if not article or not article.get("title"):
        raise ValueError("Invalid article data")

    try:
        embed = Embed(
            title=article["title"],
            url=f"https://www.duellinksmeta.com{article.get('url', '')}",
            description=article.get("description", "No description available."),
            color=Color.blue(),
            timestamp=datetime.fromisoformat(article.get("date", "").replace("Z", "+00:00"))
                if article.get("date") else None
        )

        if authors := article.get("authors"):
            author_names = ", ".join(author["username"] for author in authors)
            embed.add_field(name="Authors", value=author_names, inline=False)

        if category := article.get("category"):
            embed.add_field(name="Category", value=category.title(), inline=True)

        if image := article.get("image"):
            embed.set_thumbnail(url=f"https://www.duellinksmeta.com{image}")

        return embed
    except Exception as e:
        raise ValueError(f"Failed to create article embed: {str(e)}")

class CardBuilder:
    """Builds Discord embeds for cards and related content."""
    FALLBACK_ICONS = {
        "spell": "📗",
        "trap": "📕",
        "skill": "⚡",
        "normal": "N",
        "rare": "R",
        "super": "SR",
        "ultra": "UR",
        "semilimited": "2️⃣",
        "limited": "1️⃣",
        "limited_3": "3️⃣",
        "forbidden": "🚫",
        "DARK": "⚫",
        "DIVINE": "✨",
        "EARTH": "🌍",
        "FIRE": "🔥",
        "LIGHT": "💡",
        "WATER": "💧",
        "WIND": "🌪️",
        "Quick-Play": "⚡",
        "Ritual": "🔷",
        "Field": "🏟️",
        "Equip": "⚔️",
        "Continuous": "♾️",
        "Counter": "↩️"
    }

    def __init__(self, *, log=None):
        self.logger = log or logging.getLogger("red.dlm.builder")
        self.image_pipeline = ImagePipeline(log=self.logger)
        self.emoji_cache = {}

    async def initialize(self):
        try:
            await self.image_pipeline.initialize()
        except Exception as e:
            self.logger.error(f"Error initializing card builder: {e}", exc_info=True)
            raise

    async def validate_emojis(self, guild: discord.Guild) -> None:
        try:
            self.emoji_cache = {
                emoji.name: str(emoji)
                for emoji in guild.emojis
                if emoji.name in self.FALLBACK_ICONS
            }
            self.logger.debug(f"Cached {len(self.emoji_cache)} emojis from guild {guild.id}")
        except Exception as e:
            self.logger.error(f"Error validating emojis for guild {guild.id}: {e}", exc_info=True)

    def get_icon(self, key: str) -> str:
        if not key:
            return ""
        return self.emoji_cache.get(key, self.FALLBACK_ICONS.get(key, ""))

    async def close(self):
        try:
            await self.image_pipeline.close()
        except Exception as e:
            self.logger.error(f"Error closing card builder: {e}", exc_info=True)

    @staticmethod
    def build_art_embed(card: Card, image_url: str) -> discord.Embed:
        """
        Build a Discord embed for displaying card artwork.
        Args:
            card: Card object containing card information
            image_url: URL to the card's artwork
        Returns:
            discord.Embed: Formatted embed with card art
        """
        embed = discord.Embed(
            title=f"{card.name}",
            color=CardBuilder._get_card_color(card)
        )
        embed.set_image(url=image_url)
        return embed

    async def build_card_embed(self, card: Card, format: str = "paper") -> discord.Embed:
        try:
            embed = discord.Embed(
                title=card.name,
                url=f"https://www.duellinksmeta.com/cards/{clean_url(card.name)}"
            )
            try:
                success, url = await self.image_pipeline.get_image_url(card.id, card.monster_types or [])
                if success and url:
                    embed.set_thumbnail(url=url)
            except Exception as e:
                self.logger.warning(f"Failed to get image for card {card.id}: {e}")

            if color := self._get_card_color(card):
                embed.color = color

            self._add_card_metadata(embed, card, format)
            if card.pendulum_effect:
                embed.add_field(name="Pendulum Effect", value=card.pendulum_effect, inline=False)

            self._add_card_description(embed, card)

            if card.scale:
                embed.add_field(name="Scale", value=str(card.scale), inline=True)
            if card.arrows:
                embed.add_field(name="Arrows", value=" ".join(card.arrows), inline=True)

            self._add_monster_stats(embed, card)

            if sets := self._build_sets_text(card, format):
                embed.add_field(name="Released in", value=sets, inline=False)

            embed.set_footer(text=f"Format: {format.title()}")

            return embed
        except Exception as e:
            self.logger.error(f"Error building card embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the card embed.",
                color=discord.Color.red)

    async def get_card_image(self, card_id: int, ocg: bool = False) -> Tuple[bool, str]:
        try:
            return await self.image_pipeline.get_image_url(card_id, [], ocg=ocg)
        except Exception as e:
            self.logger.error(f"Error getting card image {card_id}: {e}", exc_info=True)
            return False, ""

    def _add_card_metadata(self, embed: discord.Embed, card: Card, format: str):
        try:
            if card.type == "monster":
                level_name = {
                    "xyz": "Rank",
                    "link": "Link"
                }.get(card.monster_type, "Level")

                attribute_text = f"**Attribute**: {self.get_icon(card.attribute)}"
                if format in ["md", "dl"]:
                    rarity = getattr(card, f"rarity_{format}", None)
                    if rarity:
                        attribute_text += f" {self.get_icon(rarity)}"

                description = [
                    attribute_text,
                    f"**{level_name}**: {card.level} **Type**: {'/'.join(filter(None, [card.race] + (card.monster_types or [])))}",
                    self._get_status_text(card, format)
                ]
                embed.description = "\n".join(filter(None, description))
            else:
                type_text = f"**Type**: {self.get_icon(card.type)}"
                if card.race:
                    type_text += f" {self.get_icon(card.race)}"
                if format in ["md", "dl"]:
                    rarity = getattr(card, f"rarity_{format}", None)
                    if rarity:
                        type_text += f" {self.get_icon(rarity)}"

                description = [
                    type_text,
                    self._get_status_text(card, format)
                ]
                embed.description = "\n".join(filter(None, description))
        except Exception as e:
            self.logger.error(f"Error adding metadata for card {card.id}: {e}", exc_info=True)

    def _add_card_description(self, embed: discord.Embed, card: Card):
        try:
            if not card.description:
                return
            if card.type == "monster" and card.monster_types and "Normal" in card.monster_types:
                embed.add_field(name="Flavor Text", value=card.description, inline=False)
            elif card.type == "monster":
                embed.add_field(name="Monster Effect", value=card.description, inline=False)
            else:
                embed.add_field(name="Effect", value=card.description, inline=False)
        except Exception as e:
            self.logger.error(f"Error adding description for card {card.id}: {e}", exc_info=True)

    def _add_monster_stats(self, embed: discord.Embed, card: Card):
        try:
            if card.type != "monster":
                return
            if card.monster_type == "link" and card.atk is not None:
                embed.add_field(name="ATK", value=str(card.atk), inline=True)
            elif card.atk is not None and hasattr(card, "def_"):
                embed.add_field(name="ATK / DEF", value=f"{card.atk} / {card.def_}", inline=True)
        except Exception as e:
            self.logger.error(f"Error adding monster stats for card {card.id}: {e}", exc_info=True)

    def _get_status_text(self, card: Card, format: str) -> str:
        try:
            if format == "paper":
                status_lines = []
                if hasattr(card, "status_tcg"):
                    status_lines.append(f"**TCG Status**: {self.get_icon(card.status_tcg)}")
                if hasattr(card, "status_ocg"):
                    status_lines.append(f"**OCG Status**: {self.get_icon(card.status_ocg)}")
                return "\n".join(status_lines)
            elif format in ["md", "dl"]:
                status = getattr(card, f"status_{format}", None)
                return f"**Status**: {self.get_icon(status)}" if status else ""
            return ""
        except Exception as e:
            self.logger.error(f"Error getting status text for card {card.id}: {e}", exc_info=True)
            return ""

    def _build_sets_text(self, card: Card, format: str) -> Optional[str]:
        try:
            sets = []
            if format in ["paper", "sd"]:
                sets = card.sets_paper or []
            elif format == "md":
                sets = getattr(card, "sets_md", []) or []
            elif format == "dl":
                sets = getattr(card, "sets_dl", []) or []

            if not sets:
                return "Unreleased"

            return ", ".join(sets[:5])
        except Exception as e:
            self.logger.error(f"Error building sets text for card {card.id}: {e}", exc_info=True)
            return None

    @staticmethod
    def _get_card_color(card: Card) -> Optional[int]:
        try:
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
        except Exception as e:
            return None
