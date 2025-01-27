import discord
from discord import Embed, Color
from datetime import datetime
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

def clean_url(text: str) -> str:
    """Convert text to URL-friendly format."""
    return text.lower().translate(str.maketrans("", "", "\"'!?,."))

def format_article_embed(article: Dict[str, Any]) -> Embed:
    """Format an article into a Discord embed."""
    if not article:
        raise ValueError("Article data cannot be empty")
    embed = Embed(
        title=article.get("title", "Alert"),
        url=f"https://www.duellinksmeta.com{article.get('url', '')}",
        description=article.get("description", "No description available."),
        color=Color.blue(),
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

def format_card_embed(card: Any) -> Embed:
    """Format a card object into a Discord embed."""
    name = getattr(card, 'name', 'Unknown Card')
    embed = Embed(
        title=name,
        url=f"https://www.duellinksmeta.com/cards/{name.replace(' ', '%20')}",
        description=getattr(card, 'description', 'No description available.'),
        color=Color.blue()
    )

    field_mappings = {
        "Type": ("type", lambda x: x.title()),
        "Attribute": ("attribute", str),
        "Level": ("level", str),
        "ATK": ("atk", lambda x: str(x) if x >= 0 else "?"),
        "DEF": ("def_", lambda x: str(x) if x >= 0 else "?"),
        "Duel Links Status": ("status_dl", str),
        "Master Duel Status": ("status_md", str),
        "Duel Links Rarity": ("rarity_dl", str),
        "Master Duel Rarity": ("rarity_md", str),
        "Subtype": ("race", str),
        "Monster Type": ("monster_type", lambda x: x.title())
    }

    for field_name, (attr, formatter) in field_mappings.items():
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

    return embed

def format_deck_embed(deck: Dict[str, Any]) -> Embed:
    """Format a deck into a Discord embed."""
    # Get deck name from deckType
    deck_name = "Unknown Deck"
    if deck_type := deck.get("deckType"):
        if isinstance(deck_type, dict):
            deck_name = deck_type.get("name", "Unknown Deck")
    
    # Create embed with blue color
    embed = Embed(
        title=deck_name,
        color=Color.blue()
    )

    # Add URL if available
    if deck.get("url"):
        embed.url = f"https://www.duellinksmeta.com{deck['url']}"

    # Author information with proper dict handling
    if author := deck.get("author"):
        if isinstance(author, dict):
            author_value = author.get("username", "Unknown")
        else:
            author_value = str(author)
        embed.add_field(name="Author", value=author_value, inline=True)

    # Skill information
    if skill := deck.get("skill"):
        if isinstance(skill, dict):
            skill_name = skill.get("name", "Unknown Skill")
            embed.add_field(name="Skill", value=skill_name, inline=True)

    # Ranked information if available
    if ranked := deck.get("rankedType"):
        if isinstance(ranked, dict):
            ranked_name = ranked.get("name", "Unknown")
            embed.add_field(name="Format", value=ranked_name, inline=True)

    # Price/Gems
    if gems := deck.get("gemsPrice"):
        embed.add_field(name="Price", value=f"{gems:,} gems", inline=True)

    # Date created
    if created := deck.get("created"):
        try:
            date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            embed.add_field(name="Created", value=date.strftime("%Y-%m-%d"), inline=True)
        except ValueError:
            pass

    # Main deck list
    if main := deck.get("main"):
        cards = []
        for card in main:
            amount = card.get("amount", 0)
            card_info = card.get("card", {})
            card_name = card_info.get("name", "Unknown Card") if isinstance(card_info, dict) else str(card_info)
            cards.append(f"{amount}x {card_name}")
        
        if cards:
            embed.add_field(name="Main Deck", value="\n".join(cards), inline=False)

    return embed
