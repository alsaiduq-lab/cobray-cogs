import discord
import logging
from typing import Optional
from urllib.parse import quote

from ..core.models import Pokemon, RARITY_MAPPING

class EmbedBuilder:
    """Handles building Discord embeds for Pokemon cards."""

    CDN_BASE = "https://s3.duellinksmeta.com"

    TYPE_EMOJIS = {
        "Grass": "🌿",
        "Fire": "🔥",
        "Water": "💧",
        "Lightning": "⚡",
        "Fighting": "👊",
        "Psychic": "🔮",
        "Darkness": "🌑",
        "Metal": "⚙️",
        "Fairy": "✨", # lol just in case
        "Dragon": "🐉",
        "Colorless": "⭐"
    }

    TYPE_COLORS = {
        "Grass": 0x38BF4B,
        "Fire": 0xFF9C54,
        "Water": 0x4F92D6,
        "Lightning": 0xFBD100,
        "Fighting": 0xCE416B,
        "Psychic": 0xFF6675,
        "Darkness": 0x5B5466,
        "Metal": 0x8E8E9F,
        "Fairy": 0xFB8AEC,
        "Dragon": 0x7673C0,
        "Colorless": 0xC6C6A7
    }

    def __init__(self, *, log=None):
        self.logger = log or logging.getLogger("red.pokemonmeta.embeds")

    async def initialize(self):
        self.logger.debug("Initializing embed builder")

    async def close(self):
        self.logger.debug("Cleaning up embed builder")

    def _get_card_image_url(self, pokemon: Pokemon, variant_idx: int = 0) -> Optional[str]:
        try:
            mongo_id = getattr(pokemon, '_id', None)
            self.logger.debug(f"Card mongo_id: {mongo_id}")
            if mongo_id:
                url = f"{self.CDN_BASE}/pkm_img/cards/{mongo_id}_w420.webp"
                self.logger.debug(f"Generated image URL: {url}")
                return url
            self.logger.warning("No MongoDB _id found for card")
            return None

        except Exception as e:
            self.logger.error(f"Error generating card image URL: {e}", exc_info=True)
            return None

    def _get_type_color(self, pokemon: Pokemon) -> int:
        if pokemon.type:
            return self.TYPE_COLORS.get(pokemon.type, 0x808080)
        elif pokemon.energy_type and len(pokemon.energy_type) > 0:
            return self.TYPE_COLORS.get(pokemon.energy_type[0], 0x808080)
        return 0x808080

    def _format_energy_cost(self, energy_list: list) -> str:
        """Format all energy costs for a move."""
        if not energy_list:
            return ""
        emojis = [self.TYPE_EMOJIS.get(e, '⭐') for e in energy_list]
        return " ".join(emojis)

    async def build_card_embed(self, pokemon: Pokemon, *, as_full_art: bool = False) -> discord.Embed:
        """Build a Discord embed for a Pokemon card."""
        try:
            title = pokemon.name
            if getattr(pokemon, 'ex', False):
                title += " ex"
            embed = discord.Embed(
                title=f"{title}",
                color=self._get_type_color(pokemon)
            )

            type_parts = []
            if pokemon.type:
                type_parts.append(f"Type: {self.TYPE_EMOJIS.get(pokemon.type, '⭐')}")
            if pokemon.hp:
                type_parts.append(f"HP: {pokemon.hp}")
            if pokemon.rarity:
                rarity = "♦" * int(pokemon.rarity[-1]) if pokemon.rarity.startswith('d-') else pokemon.rarity
                type_parts.append(f"Rarity: {rarity}")
            embed.description = " | ".join(type_parts)

            if pokemon.subtype:
                embed.add_field(name="Stage", value=pokemon.subtype, inline=False)

            if pokemon.moves:
                for move in pokemon.moves:
                    move_text = []
                    parts = []
                    if move.energy_cost:
                        energy = self._format_energy_cost(move.energy_cost)
                        if energy:
                            parts.append(f"Energy: {energy}")
                    if move.damage:
                        parts.append(f"\nDamage: {move.damage}")
                    if move.text:
                        parts.append(f"\nEffect: {move.text}")
                    move_text = " ".join(parts)
                    embed.add_field(
                        name=move.name,
                        value=move_text,
                        inline=False
                    )

            additional_info = []
            if pokemon.weakness:
                weakness_part = "Weakness: "
                if "Fighting" in pokemon.weakness:
                    weakness_part += "👊"
                additional_info.append(weakness_part)
            retreat_part = "Retreat Cost: "
            if hasattr(pokemon, 'retreat') and pokemon.retreat > 0:
                retreat_part += "⭐"
            additional_info.append(retreat_part)

            if additional_info:
                embed.add_field(
                    name="Additional Info",
                    value="\n".join(additional_info),
                    inline=False
                )

            if image_url := self._get_card_image_url(pokemon):
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            footer_parts = []
            if pokemon.id:
                footer_parts.append(f"Card ID: {pokemon.id}")
            if hasattr(pokemon, 'release_date') and pokemon.release_date:
                footer_parts.append(f"Released: {pokemon.release_date.strftime('%Y-%m-%d')}")
            if footer_parts:
                embed.set_footer(text=" | ".join(footer_parts))

            return embed

        except Exception as e:
            self.logger.error(f"Error building card embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the card embed.",
                color=discord.Color.red()
            )

    def build_art_embed(self, pokemon: Pokemon, variant_idx: int = 0) -> discord.Embed:
        """Build a Discord embed for card artwork."""
        try:
            title = pokemon.name
            if getattr(pokemon, 'ex', False):
                title += " ex"
            embed = discord.Embed(
                title=title,
                color=self._get_type_color(pokemon)
            )

            if image_url := self._get_card_image_url(pokemon, variant_idx):
                embed.set_image(url=image_url)
            else:
                raise ValueError("No art variant available")

            if pokemon.id:
                embed.set_footer(text=f"Card ID: {pokemon.id}")

            return embed

        except Exception as e:
            self.logger.error(f"Error building art embed: {e}", exc_info=True)
            raise ValueError("Failed to build art embed")
