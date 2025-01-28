import re
import discord
from discord import Embed, Color
from datetime import datetime
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass

MONSTER_CARD = "Monster"
SPELL_CARD = "Spell Card"
TRAP_CARD = "Trap Card"

URL_CLEAN_PATTERN = re.compile(r'["\'\?\.,!]')

def clean_url(text: str) -> str:
    """Convert text to URL-friendly format."""
    return URL_CLEAN_PATTERN.sub('', text.lower()).replace(' ', '%20')


MONSTER_FIELDS = {
    "Type": ("type", lambda x: x.title()),
    "Attribute": ("attribute", str),
    "Level": ("level", str),
    "ATK": ("atk", lambda x: str(x) if x >= 0 else "?"),
    "DEF": ("def_", lambda x: str(x) if x >= 0 else "?"),
    "Monster Type": ("race", str),
    "Monster Class": ("monster_type", lambda x: x.title())
}

SPELL_TRAP_FIELDS = {
    "Type": ("type", lambda x: x.title()),
    "Property": ("property", str)
}

STATUS_FIELDS = {
    "Duel Links Status": ("status_dl", str),
    "Master Duel Status": ("status_md", str),
    "Duel Links Rarity": ("rarity_dl", str),
    "Master Duel Rarity": ("rarity_md", str),
}

def format_article_embed(article: Dict[str, Any]) -> Embed:
    """Format an article into a Discord embed."""
    if not article:
        raise ValueError("Article data cannot be empty")
    embed = Embed(
        title=article.get("title", "Alert"),
        url=f"https://www.duellinksmeta.com{article.get('url', '')}",
        description=article.get("description", "No description available."),
        color=Color.blue(),
        # Convert ISO date string to a datetime; remove 'Z' and treat as UTC
        timestamp=datetime.fromisoformat(article["date"].replace("Z", "+00:00")) if "date" in article else None
    )

    if authors := article.get("authors"):
        author_names = ", ".join(author["username"] for author in authors)
        embed.add_field(name="Authors", value=author_names, inline=False)

    if category := article.get("category"):
        embed.add_field(name="Category", value=category.title(), inline=True)

    if image := article.get("image"):
        embed.set_thumbnail(url=f"https://www.duellinksmeta.com{image}")

    return embed

def build_art_embed(card: Any, variation: Optional[str] = None) -> Embed:
    """
    Format a card's artwork into a Discord embed.
    If an alternate art (variation) is given, it will use that field on the card,
    e.g. card.art_alternate if card has "art_alternate".
    """
    name = getattr(card, 'name', 'Unknown Card')
    card_type = getattr(card, 'type', '')

    embed = Embed(
        title=f"{name} - {'Alternate ' if variation else ''}Artwork",
        url=f"https://www.duellinksmeta.com/cards/{clean_url(name)}",
        color=Color.gold()
    )

    # The card might have .art or .art_alternate, etc.
    # This logic picks the appropriate attribute based on “variation”
    art_url = getattr(card, f"art_{variation}" if variation else "art", None)
    if art_url:
        embed.set_image(url=art_url)

    embed.add_field(name="Card Type", value=card_type, inline=True)

    # In case you want to show which variations exist on the card
    variations = []
    for attr in dir(card):
        if attr.startswith("art_") and attr != "art":
            # i.e. "art_alternate" → "Alternate"
            variations.append(attr.replace("art_", "").title())

    if variations:
        embed.add_field(name="Available Variations", value=", ".join(variations), inline=False)

    return embed

def format_card_embed(card: Any) -> Embed:
    """Format a card object into a Discord embed."""
    name = getattr(card, 'name', 'Unknown Card')
    card_type = getattr(card, 'type', '')
    embed = Embed(
        title=name,
        url=f"https://www.duellinksmeta.com/cards/{clean_url(name)}",
        description=getattr(card, 'description', 'No description available.'),
        color=Color.blue()
    )

    field_mappings = MONSTER_FIELDS if MONSTER_CARD in card_type else SPELL_TRAP_FIELDS

    for field_name, (attr, formatter) in field_mappings.items():
        if hasattr(card, attr) and (value := getattr(card, attr)):
            embed.add_field(name=field_name, value=formatter(value), inline=True)

    for field_name, (attr, formatter) in STATUS_FIELDS.items():
        if hasattr(card, attr) and (value := getattr(card, attr)):
            embed.add_field(name=field_name, value=formatter(value), inline=True)

    for game in ["dl", "md"]:
        sets_attr = f"sets_{game}"
        if hasattr(card, sets_attr) and (sets := getattr(card, sets_attr)):
            formatted_sets = ', '.join(sets[:3])
            if len(sets) > 3:
                formatted_sets += f" (+{len(sets) - 3} more)"
            embed.add_field(
                name=f"{'Duel Links' if game == 'dl' else 'Master Duel'} Sets",
                value=formatted_sets,
                inline=False
            )

    if art_url := getattr(card, 'art', None):
        embed.set_thumbnail(url=art_url)

    return embed
