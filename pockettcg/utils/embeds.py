import discord
import logging
from typing import Optional, List, Union
from urllib.parse import quote
from .images import ImagePipeline
from ..core.models import Pokemon, RARITY_MAPPING

class EmbedBuilder:
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
        "Colorless": "<:ColorlessEnergy:1335228335911079990>"
    }

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

    def __init__(self, image_pipeline: ImagePipeline, *, log=None):
        """Initialize the EmbedBuilder with an image pipeline and logger."""
        self.image_pipeline = image_pipeline
        self.logger = log or logging.getLogger("red.pokemonmeta.utils.embeds")

    def _get_energy_emoji(self, energy_type: str) -> str:
        """Get energy emoji, falling back to unicode if discord emoji fails."""
        try:
            energy_type = energy_type.strip()
            if energy_type in self.DISCORD_EMOJIS:
                emoji_str = self.DISCORD_EMOJIS[energy_type]
                if not emoji_str.startswith('<:') and not emoji_str.endswith('>'):
                    emoji_str = f"<:{energy_type}Energy:{emoji_str}>"
                return emoji_str
            return self.TYPE_EMOJIS.get(energy_type, "⭐")
        except Exception as e:
            self.logger.error(f"Error getting energy emoji for {energy_type}: {e}", exc_info=True)
            return self.TYPE_EMOJIS.get(energy_type, "⭐")

    def _format_energy_cost(self, energy_list: Union[List[str], List[List[str]]]) -> str:
        """Format all energy costs for a move."""
        if not energy_list:
            return ""
        try:
            emojis = []
            for energy in energy_list:
                if isinstance(energy, list):
                    alt_emojis = []
                    for alt_energy in energy:
                        emoji = self._get_energy_emoji(alt_energy)
                        if emoji:
                            alt_emojis.append(emoji)
                    if alt_emojis:
                        emojis.append("/".join(alt_emojis))
                else:
                    emoji = self._get_energy_emoji(energy)
                    if emoji:
                        emojis.append(emoji)
            return " ".join(emojis)
        except Exception as e:
            self.logger.error(f"Error formatting energy cost {energy_list}: {e}", exc_info=True)
            return str(energy_list)

    def _get_type_color(self, pokemon: Pokemon) -> int:
        if pokemon.type:
            return self.TYPE_COLORS.get(pokemon.type, 0x808080)
        elif pokemon.energy_type and len(pokemon.energy_type) > 0:
            return self.TYPE_COLORS.get(pokemon.energy_type[0], 0x808080)
        return 0x808080

    def _get_card_image_url(self, pokemon: Pokemon, variant_idx: int = 0) -> Optional[str]:
        try:
            if self.image_pipeline is None:
                self.logger.error("No image pipeline configured")
                return None
            return self.image_pipeline.get_cdn_card_url(pokemon)
        except Exception as e:
            self.logger.error(f"Error getting card image URL: {e}", exc_info=True)
            return None

    async def build_card_embed(self, pokemon: Pokemon, *, as_full_art: bool = False) -> discord.Embed:
        """Build a Discord embed for a Pokemon card."""
        try:
            title = pokemon.name
            if getattr(pokemon, 'ex', False):
                title += " ex"
            embed = discord.Embed(
                title=title,
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

            retreat_part = "Retreat Cost: "
            retreat_cost = 0
            if hasattr(pokemon, 'retreat') and pokemon.retreat:
                retreat_cost = int(pokemon.retreat)
            elif hasattr(pokemon, 'retreat_cost') and pokemon.retreat_cost:
                retreat_cost = int(pokemon.retreat_cost)
            if retreat_cost > 0:
                colorless_emoji = self._get_energy_emoji("Colorless")
                retreat_part += (colorless_emoji + " ") * retreat_cost
            retreat_part = retreat_part.rstrip()
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
