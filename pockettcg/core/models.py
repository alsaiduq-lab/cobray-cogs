"""Data models for Pokemon TCG cards."""
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime

@dataclass
class Move:
    name: str
    energy_cost: List[str]
    damage: Optional[str] = None
    text: Optional[str] = None

    def calculate_energy_cost(self) -> Dict[str, int]:
        """Calculate the total energy cost for the move."""
        energy_cost_dict = {}
        for energy in self.energy_cost:
            if energy in energy_cost_dict:
                energy_cost_dict[energy] += 1
            else:
                energy_cost_dict[energy] = 1
        return energy_cost_dict

    def get_energy_cost_description(self) -> str:
        """Get a human-readable description of the energy cost."""
        cost_dict = self.calculate_energy_cost()
        if not cost_dict:
            return "No energy cost"
        return ", ".join([f"{count} {energy}" for energy, count in cost_dict.items()])

@dataclass
class ArtVariant:
    id: str
    name: str

@dataclass
class Source:
    id: str
    type: str
    name: str
    expires: Optional[datetime] = None
    image: Optional[str] = None
    url: Optional[str] = None

@dataclass
class ObtainInfo:
    source: Source
    amount: int
    type: str

@dataclass
class Pokemon:
    id: str  # pokemonId
    name: str
    card_type: str  # cardType (e.g. Pokemon, Trainer, Energy)
    pack: str
    hp: str
    abilities: List[str]
    alternate_art: bool
    energy_type: List[str]  # Pokemon's energy type(s)
    obtain: List[ObtainInfo]
    rarity: str
    retreat: int
    skills: List[str]
    moves: List[Move]
    subtype: str  # Basic, Stage 1, etc.
    release_date: datetime
    weakness: List[str]
    art_variants: List[ArtVariant]
    limitless_id: Optional[str] = None
    image_url: Optional[str] = None
    url: Optional[str] = None

    @property
    def type(self) -> Optional[str]:
        """Get the primary energy type of the Pokemon."""
        return self.energy_type[0] if self.energy_type else None

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> 'Pokemon':
        """Create a Pokemon instance from API data."""
        moves = []
        for move_data in data.get("moves", []):
            move = Move(
                name=move_data["name"],
                energy_cost=move_data.get("energyCost", []),
                damage=move_data.get("hp"),
                text=move_data.get("text")
            )
            moves.append(move)

        obtain_info = []
        for obtain in data.get("obtain", []):
            if source_data := obtain.get("source"):
                linked_article = source_data.get("linkedArticle", {})
                source = Source(
                    id=source_data.get("_id", ""),
                    type=source_data.get("type", ""),
                    name=source_data.get("name", ""),
                    expires=datetime.fromisoformat(source_data["expires"].replace("Z", "+00:00")) 
                        if source_data.get("expires") else None,
                    image=linked_article.get("image"),
                    url=linked_article.get("url")
                )
                obtain_info.append(ObtainInfo(
                    source=source,
                    amount=obtain.get("amount", 1),
                    type=obtain.get("type", "")
                ))

        art_variants = []
        for variant in data.get("artVariants", []):
            art_variants.append(ArtVariant(
                id=variant["_id"],
                name=variant["name"]
            ))

        # Handle energy types
        energy_types = []
        if main_type := data.get("energyType"):
            if isinstance(main_type, list):
                energy_types.extend(main_type)
            else:
                energy_types.append(main_type)

        pokemon = cls(
            id=data["pokemonId"],
            name=data["name"],
            card_type=data["cardType"],
            pack=data["pack"],
            hp=data["hp"],
            abilities=data.get("abilities", []),
            alternate_art=data.get("alternateArt", False),
            energy_type=energy_types,
            obtain=obtain_info,
            rarity=data["rarity"],
            retreat=data.get("retreat", 0),
            skills=data.get("skills", []),
            moves=moves,
            subtype=data["subType"],
            release_date=datetime.fromisoformat(data["release"].replace("Z", "+00:00")),
            weakness=data.get("weakness", []),
            art_variants=art_variants,
            limitless_id=data.get("limitlessId")
        )
        # Set MongoDB _id if available
        if "_id" in data:
            pokemon._id = data["_id"]
        return pokemon

RARITY_MAPPING = {
    "d-1": "♦",
    "d-2": "♦♦",
    "d-3": "♦♦♦",
    "d-4": "♦♦♦♦",
    "s-1": "⭐",
    "s-2": "⭐⭐",
    "s-3": "⭐⭐⭐",
    "crown": "👑"
}

ENERGY_TYPES = [
    "Grass", "Fire", "Water", "Lightning", 
    "Fighting", "Psychic", "Darkness", "Metal", "Dragon", "Colorless"
]

# Example placeholder cards for testing if needed
EXTRA_CARDS = []
