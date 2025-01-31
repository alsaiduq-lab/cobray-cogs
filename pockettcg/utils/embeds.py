"""Builds Discord embeds for Pokemon cards."""
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
        "Fairy": "✨",
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
        """Initialize the embed builder."""
        self.logger.debug("Initializing embed builder")

    async def close(self):
        """Cleanup resources."""
        self.logger.debug("Cleaning up embed builder")

    def _get_card_image_url(self, pokemon: Pokemon, variant_idx: int = 0) -> Optional[str]:
        """Get the image URL for a card."""
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

    def _format_energy(self, energy_list: list) -> str:
        """Format energy list with emojis."""
        return " ".join(self.TYPE_EMOJIS.get(e, '⭐') for e in energy_list)

    async def build_card_embed(self, pokemon: Pokemon, *, as_full_art: bool = False) -> discord.Embed:
        """Build a Discord embed for a Pokemon card."""
        try:
            # Build title with name only, no emoji prefix
            embed = discord.Embed(
                title=f"{pokemon.name}",
                color=self._get_type_color(pokemon)
            )

            # Card Type Info - now matching the screenshot format
            type_parts = []
            if pokemon.type:
                type_parts.append(f"Type: {self.TYPE_EMOJIS.get(pokemon.type, '')}")
            if pokemon.hp:
                type_parts.append(f"HP: {pokemon.hp}")
            if pokemon.rarity:
                rarity = "♦" * int(pokemon.rarity[-1]) if pokemon.rarity.startswith('d-') else pokemon.rarity
                type_parts.append(f"Rarity: {rarity}")
            
            if type_parts:
                embed.description = " | ".join(type_parts)

            # Stage
            if pokemon.subtype:
                embed.add_field(name="Stage", value=pokemon.subtype, inline=True)

            # Moves - formatted like the screenshot
            if pokemon.moves:
                for move in pokemon.moves:
                    # Title is just the move name
                    title = move.name
                    
                    # Format energy and details
                    lines = []
                    if move.energy_cost:
                        lines.append(f"Energy: {self._format_energy(move.energy_cost)}")
                    if move.damage:
                        lines.append(f"Damage: {move.damage}x")
                    if move.text:
                        lines.append(f"Effect: {move.text}")
                    
                    embed.add_field(
                        name=title,
                        value="\n".join(lines),
                        inline=False
                    )

            # Additional Info section
            metadata = []
            if pokemon.weakness:
                weakness_text = ", ".join(f"{self.TYPE_EMOJIS.get(w, '❓')}" for w in pokemon.weakness)
                metadata.append(f"Weakness: {weakness_text}")
            if hasattr(pokemon, 'retreat') and pokemon.retreat is not None:
                metadata.append(f"Retreat Cost: {'⭐'}")

            if metadata:
                embed.add_field(name="Additional Info", value="\n".join(metadata), inline=False)

            # Card Image
            if image_url := self._get_card_image_url(pokemon):
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            # Footer
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
            embed = discord.Embed(
                title=f"{pokemon.name}",
                color=self._get_type_color(pokemon)
            )

            if image_url := self._get_card_image_url(pokemon, variant_idx):
                embed.set_image(url=image_url)
            else:
                raise ValueError("No art variant available")

            # Footer with just the card ID
            if pokemon.id:
                embed.set_footer(text=f"Card ID: {pokemon.id}")

            return embed

        except Exception as e:
            self.logger.error(f"Error building art embed: {e}", exc_info=True)
            raise ValueError("Failed to build art embed")
