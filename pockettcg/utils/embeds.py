import discord
import logging
from typing import Optional, List, Union, Any
from urllib.parse import quote
from .images import ImagePipeline
from ..core.models import Pokemon, RARITY_MAPPING

class BaseCardEmbed:
    def __init__(self, image_pipeline: ImagePipeline, *, log: Optional[logging.Logger] = None) -> None:
        self.image_pipeline = image_pipeline
        self.logger = log or logging.getLogger("red.pokemonmeta.utils.embeds")

    def _get_card_image_url(self, card: Any, variant_idx: int = 0) -> Optional[str]:
        if self.image_pipeline is None:
            self.logger.error("No image pipeline configured")
            return None
        card_id = getattr(card, '_id', None) or getattr(card, 'id', None)
        if not card_id:
            self.logger.warning(f"No ID found for card: {getattr(card, 'name', 'Unknown')}")
            return None
        try:
            url = self.image_pipeline.get_cdn_card_url(card)
            if url:
                self.logger.debug(f"Generated URL for card {card_id}: {url}")
                return url
            self.logger.warning(f"Failed to generate URL for card {card_id}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting card image URL: {e}", exc_info=True)
            return None

    def _add_footer(self, embed: discord.Embed, card: Any) -> None:
        footer_parts = []
        if set_id := getattr(card, 'id', None):
            footer_parts.append(f"Set: {set_id}")
        if mongo_id := getattr(card, '_id', None):
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
        "Colorless": "<:ColorlessEnergy:1335228335911079990>",
        None: "<:ColorlessEnergy:1335228335911079990>"
    }

    TYPE_EMOJIS = {
        "Grass": "🌿", "Fire": "🔥", "Water": "💧",
        "Lightning": "⚡", "Fighting": "👊", "Psychic": "🔮",
        "Darkness": "🌑", "Metal": "⚙️", "Fairy": "✨",
        "Dragon": "🐉", "Colorless": "⭐", None: "⭐"
    }

    TYPE_COLORS = {
        "Grass": 0x38BF4B, "Fire": 0xFF9C54, "Water": 0x4F92D6,
        "Lightning": 0xFBD100, "Fighting": 0xCE416B, "Psychic": 0xFF6675,
        "Darkness": 0x5B5466, "Metal": 0x8E8E9F, "Fairy": 0xFB8AEC,
        "Dragon": 0x7673C0, "Colorless": 0xC6C6A7,
        "Trainer": 0xE5C488, "Supporter": 0xF199A3,
        "Item": 0x9DB7F5, "Tool": 0xA7B6E5
    }

    def _format_rarity(self, rarity: Optional[str]) -> str:
        if not rarity:
            return ""
        return "♦️" * int(rarity[-1]) if rarity.startswith('d-') else RARITY_MAPPING.get(rarity, rarity)

    async def build_card_embed(self, card: Any, *, as_full_art: bool = False) -> discord.Embed:
        try:
            if isinstance(card, Pokemon):
                return await self.build_pokemon_embed(card, as_full_art=as_full_art)
            elif hasattr(card, 'category') and card.category in ['Trainer', 'Supporter', 'Item', 'Tool']:
                return await self.build_trainer_embed(card, as_full_art=as_full_art)
            return await self.build_generic_embed(card, as_full_art=as_full_art)
        except Exception as e:
            self.logger.error(f"Error building card embed: {e}", exc_info=True)
            return discord.Embed(title="Error", description="An error occurred while building the card embed.", color=discord.Color.red())

    def _get_type_color(self, pokemon: Pokemon) -> int:
        if pokemon.energy_type:
            return self.TYPE_COLORS.get(pokemon.energy_type[0], 0x808080)
        return 0x808080

    def _get_energy_emoji(self, energy_type: Optional[str]) -> str:
        try:
            if energy_type is None:
                return self.DISCORD_EMOJIS[None]
            energy_type = str(energy_type).strip()
            return self.DISCORD_EMOJIS.get(energy_type, self.TYPE_EMOJIS.get(energy_type, "⭐"))
        except Exception as e:
            self.logger.error(f"Error getting energy emoji for {energy_type}: {e}", exc_info=True)
            return "⭐"

    def _format_energy_cost(self, energy_list: Union[List[str], List[List[str]]]) -> str:
        if not energy_list:
            return ""
            
        try:
            emojis = []
            for energy in energy_list:
                if isinstance(energy, list):
                    alt_emojis = [self._get_energy_emoji(e) for e in energy if e is not None]
                    if alt_emojis:
                        emojis.append("/".join(alt_emojis))
                elif energy is not None:
                    if emoji := self._get_energy_emoji(energy):
                        emojis.append(emoji)
            
            return " ".join(emojis)
        except Exception as e:
            self.logger.error(f"Error formatting energy cost {energy_list}: {e}", exc_info=True)
            return str(energy_list)

    async def build_generic_embed(self, card: Any, *, as_full_art: bool = False) -> discord.Embed:
        try:
            embed = discord.Embed(title=card.name, color=0x808080)
            type_parts = []
            
            if hasattr(card, 'card_type'):
                type_parts.append(f"Type: {card.card_type}")
            if hasattr(card, 'rarity'):
                type_parts.append(f"Rarity: {self._format_rarity(card.rarity)}")
            if type_parts:
                embed.description = " | ".join(type_parts)

            if hasattr(card, 'text') and card.text:
                embed.add_field(name="Effect", value=card.text, inline=False)
            if hasattr(card, 'rules') and card.rules:
                embed.add_field(name="Rules", value="\n".join(card.rules), inline=False)

            if image_url := self._get_card_image_url(card):
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, card)
            return embed
        except Exception as e:
            self.logger.error(f"Error building generic embed: {e}", exc_info=True)
            return discord.Embed(title="Error", description="An error occurred while building the card embed.", color=discord.Color.red())

    async def build_trainer_embed(self, card: Any, *, as_full_art: bool = False) -> discord.Embed:
        try:
            embed = discord.Embed(title=card.name, color=self.TYPE_COLORS.get(card.category, self.TYPE_COLORS["Trainer"]))
            type_parts = [f"Category: {card.category}"]
            
            if card.rarity:
                type_parts.append(f"Rarity: {self._format_rarity(card.rarity)}")
            embed.description = " | ".join(type_parts)

            if card.text:
                embed.add_field(name="Effect", value=card.text, inline=False)
            if hasattr(card, 'rules') and card.rules:
                embed.add_field(name="Rules", value="\n".join(card.rules), inline=False)

            if image_url := self._get_card_image_url(card):
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, card)
            return embed
        except Exception as e:
            self.logger.error(f"Error building trainer embed: {e}", exc_info=True)
            return discord.Embed(title="Error", description="An error occurred while building the trainer card embed.", color=discord.Color.red())

    async def build_pokemon_embed(self, pokemon: Pokemon, *, as_full_art: bool = False) -> discord.Embed:
        try:
            title = f"{pokemon.name}{' ex' if getattr(pokemon, 'ex', False) else ''}"
            embed = discord.Embed(title=title, color=self._get_type_color(pokemon))
            type_parts = []

            if pokemon.energy_type:
                type_parts.append(f"Type: {self._get_energy_emoji(pokemon.energy_type[0])}")
            if pokemon.hp:
                type_parts.append(f"HP: {pokemon.hp}")
            if pokemon.rarity:
                type_parts.append(f"Rarity: {self._format_rarity(pokemon.rarity)}")
            
            embed.description = " | ".join(type_parts)

            if pokemon.subType:
                embed.add_field(name="Stage", value=pokemon.subType, inline=False)

            if hasattr(pokemon, 'abilities') and pokemon.abilities:
                for ability in pokemon.abilities:
                    ability_text = []
                    if hasattr(ability, 'name') and hasattr(ability, 'text'):
                        ability_text.extend([f"__**{ability.name}**__", f"*{ability.text}*"])
                    elif isinstance(ability, dict):
                        if ability.get('name'):
                            ability_text.append(f"__**{ability['name']}**__")
                        if ability.get('text'):
                            ability_text.append(f"*{ability['text']}*")
                    else:
                        ability_text.append(f"*{str(ability)}*")
                    if ability_text:
                        embed.add_field(name="Ability", value="\n".join(ability_text), inline=False)

            if pokemon.moves:
                for move in pokemon.moves:
                    parts = []
                    if move.energy_cost:
                        energy = self._format_energy_cost(move.energy_cost)
                        if energy:
                            parts.append(f"Energy: {energy}")
                    if move.damage:
                        parts.append(f"Damage: {move.damage}")
                    if move.text:
                        parts.append(f"Effect: {move.text}")
                    embed.add_field(name=move.name, value="\n".join(parts), inline=False)

            additional_info = []
            if pokemon.weakness:
                weakness_text = "Weakness: " + "".join(f"{self._get_energy_emoji(weak_type)} +20" for weak_type in pokemon.weakness)
                additional_info.append(weakness_text)

            retreat_cost = getattr(pokemon, 'retreat', 0) or getattr(pokemon, 'retreat_cost', 0)
            if retreat_cost:
                colorless_emoji = self._get_energy_emoji("Colorless")
                retreat_text = f"Retreat Cost: {colorless_emoji * int(retreat_cost)}"
                additional_info.append(retreat_text)

            if additional_info:
                embed.add_field(name="Additional Info", value="\n".join(additional_info), inline=False)

            if image_url := self._get_card_image_url(pokemon):
                if as_full_art:
                    embed.set_image(url=image_url)
                else:
                    embed.set_thumbnail(url=image_url)

            self._add_footer(embed, pokemon)
            return embed
        except Exception as e:
            self.logger.error(f"Error building pokemon embed: {e}", exc_info=True)
            return discord.Embed(title="Error", description="An error occurred while building the pokemon card embed.", color=discord.Color.red())

    def build_art_embed(self, card: Any, variant_idx: int = 0) -> discord.Embed:
        try:
            title = f"{card.name}{' ex' if isinstance(card, Pokemon) and getattr(card, 'ex', False) else ''}"
            embed = discord.Embed(
                title=title,
                color=self.TYPE_COLORS.get(getattr(card, 'energy_type', [None])[0], 0x808080)
            )

            if not (image_url := self._get_card_image_url(card, variant_idx)):
                raise ValueError("No art variant available")

            embed.set_image(url=image_url)
            self._add_footer(embed, card)
            return embed
        except Exception as e:
            self.logger.error(f"Error building art embed: {e}", exc_info=True)
            raise ValueError("Failed to build art embed")
