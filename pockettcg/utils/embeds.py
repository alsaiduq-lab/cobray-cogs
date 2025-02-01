import discord
import logging
from typing import Optional
from urllib.parse import quote
from ..core.models import Pokemon, RARITY_MAPPING

class EmbedBuilder:
    """Handles building Discord embeds for Pokemon cards."""

    CDN_BASE = "https://s3.duellinksmeta.com"

    DISCORD_EMOJIS = {
        "Grass": "<:GrassEnergy:1335228242046488707>",
        "Fire": "<:FireEnergy:1335228250812579910>",
        "Water": "<:WaterEnergy:1335228194940387418>",
        "Lightning": "<:LightningEnergy:1335228231653261442>",
        "Fighting": "<:FightingEnergy:1335228265190785158>", 
        "Psychic": "<:PsychicEnergy:1335228211017023488>",
        "Darkness": "<:DarknessEnergy:1335228325139972107>",
        "Metal": "<:MetalEnergy:1335228220886224936>",
        "Fairy": "<:FairyEnergy:1335228293208604734>",
        "Dragon": "<:DragonEnergy:1335228306563399754>",
        "Colorless": "<:ColorlessEnergy:1335228333591107990>"
    }

    def _get_energy_emoji(self, energy_type: str) -> str:
        """Get energy emoji, falling back to unicode if discord emoji fails."""
        try:
            # Use Discord emoji directly since these are bot emojis
            if energy_type in self.DISCORD_EMOJIS:
                return self.DISCORD_EMOJIS[energy_type]
            
            # Fall back to Unicode emojis
            return self.TYPE_EMOJIS.get(energy_type, "⭐")
        except Exception as e:
            self.logger.error(f"Error getting energy emoji: {e}", exc_info=True)
            return self.TYPE_EMOJIS.get(energy_type, "⭐")

    TYPE_EMOJIS = {
        "Grass": "🌿",  # Fallback Unicode emojis if all else fails
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
        self.logger = log or logging.getLogger("red.pokemonmeta.utils.embeds")

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
        emojis = [self._get_energy_emoji(e) for e in energy_list]
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
                type_parts.append(f"Type: {self._get_energy_emoji(pokemon.type)}")
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
                for weak_type in pokemon.weakness:
                    emoji = self._get_energy_emoji(weak_type)
                    weakness_part += f"{emoji} +20"
                additional_info.append(weakness_part)

            # Handle retreat cost
            retreat_part = "Retreat Cost: "
            retreat_cost = 0
            
            if hasattr(pokemon, 'retreat') and pokemon.retreat:
                retreat_cost = int(pokemon.retreat)
            elif hasattr(pokemon, 'retreat_cost') and pokemon.retreat_cost:
                retreat_cost = int(pokemon.retreat_cost)
                
            if retreat_cost > 0:
                retreat_emojis = [self._get_energy_emoji("Colorless") for _ in range(retreat_cost)]
                retreat_part += " ".join(retreat_emojis)
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
