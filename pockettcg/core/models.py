from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class Set:
    id: str
    name: str
    type: str
    expires: Optional[datetime] = None
    url: Optional[str] = None
    image: Optional[str] = None

@dataclass
class TrainerCard:
    id: str
    name: str
    type: str
    effect: str
    set: str
    rarity: Optional[str] = None
    image_url: Optional[str] = None

    @classmethod
    def from_api(cls, data: Dict) -> 'TrainerCard':
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            type=data.get('supertype', 'Trainer'),
            effect=data.get('rules', [''])[0] if data.get('rules') else '',
            set=data.get('set', {}).get('name', 'Unknown Set'),
            rarity=data.get('rarity', None),
            image_url=data.get('images', {}).get('small', None)
        )

@dataclass
class Move:
    name: str
    text: str
    energy_cost: List[str]
    damage: str

    def calculate_energy_cost(self) -> Dict[str, int]:
        energy_cost_dict = {}
        for energy in self.energy_cost:
            if energy in energy_cost_dict:
                energy_cost_dict[energy] += 1
            else:
                energy_cost_dict[energy] = 1
        return energy_cost_dict

    def get_energy_cost_description(self) -> str:
        cost_dict = self.calculate_energy_cost()
        if not cost_dict:
            return "No energy cost"
        return ", ".join([f"{count} {energy}" for energy, count in cost_dict.items()])

@dataclass
class Ability:
    name: str
    text: str
    type: Optional[str] = None

@dataclass
class ArtVariant:
    id: str
    name: str

@dataclass
class Source:
    id: str
    type: str
    name: str
    expires: Optional[str]
    linked_article: Dict

@dataclass
class ObtainInfo:
    source: Source
    amount: int
    type: str

@dataclass
class Pokemon:
    id: str
    name: str
    card_type: str
    energy_type: List[str]
    _id: Optional[str] = None
    sub_type: Optional[str] = None
    hp: Optional[str] = None
    weakness: List[str] = field(default_factory=list)
    retreat: Optional[int] = None
    description: str = ""
    abilities: List[Ability] = field(default_factory=list)
    moves: List[Move] = field(default_factory=list)
    obtain: List[ObtainInfo] = field(default_factory=list)
    rarity: Optional[str] = None
    pokemon_id: Optional[str] = None
    limitless_id: Optional[str] = None
    art_variants: List[ArtVariant] = field(default_factory=list)
    is_ex: bool = False
    is_full_art: bool = False
    is_alternate_art: bool = False
    variant_types: List[str] = field(default_factory=list)
    has_variants: bool = False
    pop_rank: Optional[int] = None
    release_date: Optional[datetime] = None

    @property
    def type(self) -> str:
        return self.card_type

    @property
    def set(self) -> str:
        for obtain in self.obtain:
            if obtain.type == "sets" and obtain.source:
                return obtain.source.name
        return "Unknown Set"

    @property
    def subtype(self) -> Optional[str]:
        return self.sub_type

    @property
    def subType(self) -> Optional[str]:
        return self.sub_type

    @classmethod
    def from_api(cls, data: Dict) -> 'Pokemon':
        try:
            if data is None:
                raise ValueError("Received None instead of card data")

            print(f"Processing card: {data.get('name')} (ID: {data.get('_id')})")

            mongo_id = data.get('_id')
            card_id = (
                data.get('pokemonId') or
                data.get('id') or
                data.get('_filename') or
                data.get('filename')
            )

            if not card_id:
                print(f"Warning: No card ID found for card data: {data}")
                if isinstance(data, dict):
                    card_id = next((v for k, v in data.items() if 'id' in k.lower()), None)
                if not card_id:
                    raise ValueError(f"No valid ID field found in card data: {data}")

            card_type = data.get('cardType', data.get('type', data.get('supertype', '')))
            print(f"Card type: {card_type}")

            energy_type = data.get('energyType', [])
            if isinstance(energy_type, str):
                energy_type = [energy_type]
            elif energy_type is None:
                energy_type = []
            print(f"Energy type: {energy_type}")

            moves = []
            raw_moves = data.get('moves', [])
            if isinstance(raw_moves, dict):
                raw_moves = [raw_moves]
            for move in raw_moves or []:
                if move:
                    damage = move.get('damage', move.get('hp', ''))
                    if isinstance(damage, (int, float)):
                        damage = str(damage)
                    moves.append(Move(
                        name=move.get('name', ''),
                        text=move.get('text', ''),
                        energy_cost=move.get('energyCost', move.get('cost', [])) or [],
                        damage=damage
                    ))
            print(f"Processed {len(moves)} moves")

            abilities = []
            raw_abilities = data.get('abilities', [])
            if isinstance(raw_abilities, dict):
                raw_abilities = [raw_abilities]
            for ability in raw_abilities or []:
                if ability:
                    abilities.append(Ability(
                        name=ability.get('name', ''),
                        text=ability.get('text', ability.get('effect', '')),
                        type=ability.get('type')
                    ))
            print(f"Processed {len(abilities)} abilities")

            art_variants = []
            raw_variants = data.get('artVariants', [])
            if isinstance(raw_variants, dict):
                raw_variants = [raw_variants]
            for variant in raw_variants or []:
                if variant:
                    variant_id = variant.get('_id', variant.get('id', ''))
                    art_variants.append(ArtVariant(
                        id=variant_id,
                        name=variant.get('name', '')
                    ))
            print(f"Processed {len(art_variants)} art variants")

            obtain_info = []
            raw_obtain = data.get('obtain', [])
            if isinstance(raw_obtain, dict):
                raw_obtain = [raw_obtain]
            for obtain in raw_obtain or []:
                if obtain and (source_data := obtain.get('source')):
                    if isinstance(source_data, str):
                        source = Source(
                            id='',
                            type='sets',
                            name=source_data,
                            expires=None,
                            linked_article={}
                        )
                    else:
                        linked_article = source_data.get('linkedArticle', {}) or {}
                        source = Source(
                            id=source_data.get('_id', ''),
                            type=source_data.get('type', ''),
                            name=source_data.get('name', ''),
                            expires=source_data.get('expires'),
                            linked_article={
                                'id': linked_article.get('_id', ''),
                                'title': linked_article.get('title', ''),
                                'url': linked_article.get('url', ''),
                                'image': linked_article.get('image', '')
                            }
                        )
                    obtain_info.append(ObtainInfo(
                        source=source,
                        amount=obtain.get('amount', 1),
                        type=obtain.get('type', 'sets')
                    ))
            print(f"Processed {len(obtain_info)} obtain info entries")

            release_date = None
            if release_str := data.get('release'):
                try:
                    release_date = datetime.fromisoformat(release_str.replace('Z', '+00:00'))
                    print(f"Parsed release date: {release_date}")
                except (ValueError, TypeError) as e:
                    print(f"Failed to parse release date: {e}")
                    pass

            return cls(
                id=card_id,
                _id=mongo_id,
                name=data.get('name', ''),
                card_type=card_type,
                energy_type=energy_type,
                sub_type=data.get('subType', data.get('subtype')),
                hp=data.get('hp'),
                weakness=data.get('weakness', []) or [],
                retreat=data.get('retreat'),
                description=data.get('description', ''),
                abilities=abilities,
                moves=moves,
                obtain=obtain_info,
                rarity=data.get('rarity'),
                pokemon_id=data.get('pokemonId'),
                limitless_id=data.get('limitlessId'),
                art_variants=art_variants,
                is_ex=data.get('ex', False),
                is_alternate_art=data.get('alternateArt', False),
                pop_rank=data.get('popRank'),
                release_date=release_date,
                variant_types=data.get('variantTypes', []),
                is_full_art=data.get('fullArt', False),
                has_variants=bool(art_variants)
            )

        except Exception as e:
            print(f"Error processing card data: {data}")
            print(f"Error details: {str(e)}")
            raise ValueError(f"Failed to create Pokemon from API data: {str(e)}")

RARITY_MAPPING = {
    "d-1": "♦",
    "d-2": "♦♦",
    "d-3": "♦♦♦",
    "d-4": "♦♦♦♦",
    "s-1": "⭐",
    "s-2": "⭐⭐",
    "s-3": "⭐⭐⭐",
    "cr": "👑"
}

ENERGY_TYPES = [
    "Grass", "Fire", "Water", "Lightning",
    "Fighting", "Psychic", "Darkness", "Metal", "Dragon", "Colorless"
]

EXTRA_CARDS = []
