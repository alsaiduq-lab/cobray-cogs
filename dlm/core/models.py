from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Card:
    id: str
    type: str
    race: Optional[str] = None
    monster_type: Optional[str] = None
    monster_types: List[str] = None
    attribute: Optional[str] = None
    level: Optional[int] = None
    name: str = None
    description: str = None
    pendulum_effect: Optional[str] = None
    atk: Optional[int] = None
    def_: Optional[int] = None
    scale: Optional[int] = None
    arrows: Optional[List[str]] = None
    status_md: Optional[str] = None
    status_dl: Optional[str] = None
    status_tcg: Optional[str] = None
    status_ocg: Optional[str] = None
    status_goat: Optional[str] = None
    rarity_md: Optional[str] = None
    rarity_dl: Optional[str] = None
    image_url: Optional[str] = None
    url: Optional[str] = None
    sets_paper: List[str] = None
    sets_md: List[str] = None
    sets_dl: List[str] = None
    ocg: bool = False

@dataclass
class CardSet:
    id: str
    name: str
    type: str
    url: Optional[str] = None
    image_url: Optional[str] = None

EXTRA_CARDS = [
    Card(
        id="skill-issue",
        url="https://www.wikihow.com/Play-Yu-Gi-Oh!",
        image_url="https://s3.lain.dev/ygo/skill-issue.webp",
        name="Skill Issue",
        type="spell",
        status_md="limited",
        race="Equip",
        description="The equipped player has issues with their skill.",
        sets_md=["misplay"]
    )
]

EXTRA_SETS = [
    CardSet(
        id="dummy",
        name="Dummy Set",
        url="https://example.com",
        type="special"
    )
]

ALTERNATE_SEARCH_NAMES = [
    Card(id="88581108", name="Very Fun Dragon", type="monster", url=None, image_url=None, race=None, monster_type=None, monster_types=None, attribute=None, level=None, description=None, pendulum_effect=None, atk=None, def_=None, scale=None, arrows=None, status_md=None, status_dl=None, status_tcg=None, status_ocg=None, status_goat=None, rarity_md=None, rarity_dl=None, sets_paper=None, sets_md=None, sets_dl=None, ocg=False),
    Card(id="88581108", name="VFD", type="monster", url=None, image_url=None, race=None, monster_type=None, monster_types=None, attribute=None, level=None, description=None, pendulum_effect=None, atk=None, def_=None, scale=None, arrows=None, status_md=None, status_dl=None, status_tcg=None, status_ocg=None, status_goat=None, rarity_md=None, rarity_dl=None, sets_paper=None, sets_md=None, sets_dl=None, ocg=False),
    Card(id="50588353", name="Needlefiber", type="monster", url=None, image_url=None, race=None, monster_type=None, monster_types=None, attribute=None, level=None, description=None, pendulum_effect=None, atk=None, def_=None, scale=None, arrows=None, status_md=None, status_dl=None, status_tcg=None, status_ocg=None, status_goat=None, rarity_md=None, rarity_dl=None, sets_paper=None, sets_md=None, sets_dl=None, ocg=False),
    Card(id="27204311", name="Rhongobongo", type="monster", url=None, image_url=None, race=None, monster_type=None, monster_types=None, attribute=None, level=None, description=None, pendulum_effect=None, atk=None, def_=None, scale=None, arrows=None, status_md=None, status_dl=None, status_tcg=None, status_ocg=None, status_goat=None, rarity_md=None, rarity_dl=None, sets_paper=None, sets_md=None, sets_dl=None, ocg=False),
    Card(id="55885348", name="HFD", type="spell", url=None, image_url=None, race=None, monster_type=None, monster_types=None, attribute=None, level=None, description=None, pendulum_effect=None, atk=None, def_=None, scale=None, arrows=None, status_md=None, status_dl=None, status_tcg=None, status_ocg=None, status_goat=None, rarity_md=None, rarity_dl=None, sets_paper=None, sets_md=None, sets_dl=None, ocg=False),
]
