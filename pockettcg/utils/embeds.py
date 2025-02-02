import discord
import logging
from typing import Optional, List, Union
from urllib.parse import quote
from .images import ImagePipeline
from ..core.models import Pokemon, RARITY_MAPPING

class BaseCardEmbed:
    def __init__(self, image_pipeline: ImagePipeline, *, log=None):
        self.image_pipeline = image_pipeline
        self.logger = log or logging.getLogger("red.pokemonmeta.utils.embeds")

    def _get_card_image_url(self, card, variant_idx: int = 0) -> Optional[str]:
        """Get the CDN URL for a card image."""
        try:
            if self.image_pipeline is None:
                self.logger.error("No image pipeline configured")
                return None
            card_id = getattr(card, '_id', None) or getattr(card, 'id', None)
            if not card_id:
                self.logger.warning(f"No ID found for card: {getattr(card, 'name', 'Unknown')}")
                return None
            url = self.image_pipeline.get_cdn_card_url(card)
            if url:
                self.logger.debug(f"Generated URL for card {card_id}: {url}")
            else:
                self.logger.warning(f"Failed to generate URL for card {card_id}")
            return url
        except Exception as e:
            self.logger.error(f"Error getting card image URL: {e}", exc_info=True)
            return None

    def _add_footer(self, embed: discord.Embed, card) -> None:
        footer_parts = []
        set_id = getattr(card, 'id', None)
        mongo_id = getattr(card, '_id', None)
        if set_id:
            footer_parts.append(f"Set: {set_id}")
        if mongo_id:
            footer_parts.append(f"ID: {mongo_id}")
        if hasattr(card, 'release_date') and card.release_date:
            footer_parts.append(card.release_date.strftime('%Y-%m-%d'))
        if footer_parts:
            embed.set_footer(text=" | ".join(footer_parts))

class EmbedBuilder(BaseCardEmbed):
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
        "Grass": "🌿", "Fire": "🔥", "Water": "💧",
        "Lightning": "⚡", "Fighting": "👊", "Psychic": "🔮",
        "Darkness": "🌑", "Metal": "⚙️", "Fairy": "✨",
        "Dragon": "🐉", "Colorless": "⭐"
    }

    TYPE_COLORS = {
        "Grass": 0x38BF4B, "Fire": 0xFF9C54, "Water": 0x4F92D6,
        "Lightning": 0xFBD100, "Fighting": 0xCE416B, "Psychic": 0xFF6675,
        "Darkness": 0x5B5466, "Metal": 0x8E8E9F, "Fairy": 0xFB8AEC,
        "Dragon": 0x7673C0, "Colorless": 0xC6C6A7,
        "Trainer": 0xE5C488, "Supporter": 0xF199A3,
        "Item": 0x9DB7F5, "Tool": 0xA7B6E5
    }

    async def build_card_embed(self, card, *, as_full_art: bool = False) -> discord.Embed:
        """Build an embed for any card type."""
        try:
            if isinstance(card, Pokemon):
                return await self.build_pokemon_embed(card, as_full_art=as_full_art)
            elif hasattr(card, 'category') and card.category in ['Trainer', 'Supporter', 'Item', 'Tool']:
                return await self.build_trainer_embed(card, as_full_art=as_full_art)
            else:
                return await self.build_generic_embed(card, as_full_art=as_full_art)
        except Exception as e:
            self.logger.error(f"Error building card embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the card embed.",
                color=discord.Color.red()
            )

    def _get_type_color(self, pokemon: Pokemon) -> int:
        if pokemon.energy_type:
            return self.TYPE_COLORS.get(pokemon.energy_type[0], 0x808080)
        return 0x808080

    def _get_energy_emoji(self, energy_type: str) -> str:
        """Get the emoji for a given energy type."""
        try:
            if energy_type is None:
                return "⭐"
            energy_type = str(energy_type).strip()
            if energy_type in self.DISCORD_EMOJIS:
                return self.DISCORD_EMOJIS[energy_type]
            return self.TYPE_EMOJIS.get(energy_type, "⭐")
        except Exception as e:
            self.logger.error(f"Error getting energy emoji for {energy_type}: {e}", exc_info=True)
            return "⭐"

    def _format_energy_cost(self, energy_list: Union[List[str], List[List[str]]]) -> str:
        if not energy_list:
            return ""
        try:
            self.logger.debug(f"Formatting energy cost: {energy_list}")
            emojis = []
            for energy in energy_list:
                if isinstance(energy, list):
                    self.logger.debug(f"Processing energy list: {energy}")
                    alt_emojis = [self._get_energy_emoji(e) for e in energy if self._get_energy_emoji(e)]
                    if alt_emojis:
                        emojis.append("/".join(alt_emojis))
                else:
                    self.logger.debug(f"Processing single energy: {energy}")
                    emoji = self._get_energy_emoji(energy)
                    if emoji:
                        emojis.append(emoji)
            result = " ".join(emojis)
            self.logger.debug(f"Formatted energy result: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Error formatting energy cost {energy_list}: {e}", exc_info=True)
            return str(energy_list)

    async def build_generic_embed(self, card, *, as_full_art: bool = False) -> discord.Embed:
        try:
            embed = discord.Embed(
                title=card.name,
                color=0x808080
            )

            type_parts = []
            if hasattr(card, 'card_type'):
                type_parts.append(f"Type: {card.card_type}")
            if hasattr(card, 'rarity'):
                rarity = "♦" * int(card.rarity[-1]) if card.rarity.startswith('d-') else card.rarity
                type_parts.append(f"Rarity: {rarity}")
            if type_parts:
                embed.description = " | ".join(type_parts)

            if hasattr(card, 'text') and card.text:
                embed.add_field(name="Effect", value=card.text, inline=False)

            if hasattr(card, 'rules') and card.rules:
                embed.add_field(name="Rules", value="\n".join(card.rules), inline=False)

            if image_url := self._get_card_image_url(card):
                self.logger.debug(f"Setting {card.name} image URL: {image_url}")
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, card)
            return embed

        except Exception as e:
            self.logger.error(f"Error building generic embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the card embed.",
                color=discord.Color.red()
            )

    async def build_trainer_embed(self, card, *, as_full_art: bool = False) -> discord.Embed:
        try:
            embed = discord.Embed(
                title=card.name,
                color=self.TYPE_COLORS.get(card.category, self.TYPE_COLORS["Trainer"])
            )

            type_parts = [f"Category: {card.category}"]
            if card.rarity:
                rarity = "♦" * int(card.rarity[-1]) if card.rarity.startswith('d-') else card.rarity
                type_parts.append(f"Rarity: {rarity}")
            embed.description = " | ".join(type_parts)

            if card.text:
                embed.add_field(name="Effect", value=card.text, inline=False)

            if hasattr(card, 'rules') and card.rules:
                embed.add_field(name="Rules", value="\n".join(card.rules), inline=False)

            if image_url := self._get_card_image_url(card):
                self.logger.debug(f"Setting {card.name} image URL: {image_url}")
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, card)
            return embed

        except Exception as e:
            self.logger.error(f"Error building trainer embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the trainer card embed.",
                color=discord.Color.red()
            )

    async def build_pokemon_embed(self, pokemon: Pokemon, *, as_full_art: bool = False) -> discord.Embed:
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

            if pokemon.subType:
                embed.add_field(name="Stage", value=pokemon.subType, inline=False)

            if hasattr(pokemon, 'abilities') and pokemon.abilities:
                for ability in pokemon.abilities:
                    ability_text = []
                    if hasattr(ability, 'name') and hasattr(ability, 'text'):
                        ability_text.append(f"__**{ability.name}**__")
                        ability_text.append(f"*{ability.text}*")
                    elif isinstance(ability, dict):
                        if ability.get('name'):
                            ability_text.append(f"__**{ability['name']}**__")
                        if ability.get('text'):
                            ability_text.append(f"*{ability['text']}*")
                    else:
                        ability_text.append(f"*{str(ability)}*")

                    if ability_text:
                        embed.add_field(
                            name="Ability",
                            value="\n".join(ability_text),
                            inline=False
                        )

            if pokemon.moves:
                for move in pokemon.moves:
                    move_text = []
                    parts = []
                    if move.energy_cost:
                        energy = self._format_energy_cost(move.energy_cost)
                        if energy:
                            parts.append(f"Energy: {energy}")
                    if move.damage:
                        parts.append(f"Damage: {move.damage}")
                    if move.text:
                        parts.append(f"Effect: {move.text}")
                    move_text = "\n".join(parts)
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
            retreat_cost = getattr(pokemon, 'retreat', 0) or getattr(pokemon, 'retreat_cost', 0)
            if retreat_cost:
                colorless_emoji = self._get_energy_emoji("Colorless")
                retreat_part += (colorless_emoji + " ") * int(retreat_cost)
            retreat_part = retreat_part.rstrip()
            additional_info.append(retreat_part)

            if additional_info:
                embed.add_field(
                    name="Additional Info",
                    value="\n".join(additional_info),
                    inline=False
                )

            if image_url := self._get_card_image_url(pokemon):
                self.logger.debug(f"Setting {pokemon.name} image URL: {image_url}")
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, pokemon)
            return embed

        except Exception as e:
            self.logger.error(f"Error building pokemon embed: {e}", exc_info=True)
            return discord.Embed(
                title="Error",
                description="An error occurred while building the pokemon card embed.",
                color=discord.Color.red()
            )

    def build_art_embed(self, card, variant_idx: int = 0) -> discord.Embed:
        try:
            title = card.name
            if isinstance(card, Pokemon) and getattr(card, 'ex', False):
                title += " ex"
            embed = discord.Embed(
                title=title,
                color=self.TYPE_COLORS.get(getattr(card, 'type', None), 0x808080)
            )

            if image_url := self._get_card_image_url(card, variant_idx):
                self.logger.debug(f"Setting art embed image URL for {card.name}: {image_url}")
                embed.set_image(url=image_url)
            else:
                self.logger.warning(f"No art variant available for {card.name}")
                raise ValueError("No art variant available")

            self._add_footer(embed, card)
            return embed

        except Exception as e:
            self.logger.error(f"Error building art embed: {e}", exc_info=True)
            raise ValueError("Failed to build art embed")
