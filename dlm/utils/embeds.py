import discord
from datetime import datetime
from typing import Dict, Any, Optional

async def format_article_embed(article: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=article.get("title", "alart"),
        url=f"https://www.duellinksmeta.com{article.get('url', '')}",
        description=article.get("description", "No description available."),
        color=discord.Color.blue(),
        timestamp=datetime.fromisoformat(article["date"].replace("Z", "+00:00"))
    )
    authors = article.get("authors", [])
    if authors:
        author_names = ", ".join(author["username"] for author in authors)
        embed.add_field(name="Authors", value=author_names, inline=False)
    if "category" in article:
        embed.add_field(name="Category", value=article["category"].title(), inline=True)
    if "image" in article and article["image"]:
        embed.set_thumbnail(url=f"https://www.duellinksmeta.com{article['image']}")
    return embed

async def format_card_embed(card) -> discord.Embed:
    """Format a card object into a Discord embed."""
    formatted_name = getattr(card, 'name', 'Unknown Card')
    url_formatted_name = formatted_name.replace(" ", "-").replace("'", "").replace('"', "").replace("!", "").replace("?", "").replace(",", "").replace(".", "").lower()
    
    embed = discord.Embed(
        title=formatted_name,
        url=f"https://www.duellinksmeta.com/cards/{url_formatted_name}",
        description=getattr(card, 'description', 'No description available.'),
        color=discord.Color.blue()
    )

    # Basic card information
    if hasattr(card, 'type'):
        embed.add_field(name="Type", value=card.type.title(), inline=True)
    
    if hasattr(card, 'attribute') and card.attribute:
        embed.add_field(name="Attribute", value=card.attribute, inline=True)

    if hasattr(card, 'level') and card.level:
        embed.add_field(name="Level", value=str(card.level), inline=True)

    # Monster stats
    if hasattr(card, 'atk') and card.atk is not None:
        atk_value = str(card.atk) if card.atk >= 0 else "?"
        embed.add_field(name="ATK", value=atk_value, inline=True)

    if hasattr(card, 'def_') and card.def_ is not None:
        def_value = str(card.def_) if card.def_ >= 0 else "?"
        embed.add_field(name="DEF", value=def_value, inline=True)

    # Format-specific information
    if hasattr(card, 'status_dl') and card.status_dl:
        embed.add_field(name="Duel Links Status", value=card.status_dl, inline=True)

    if hasattr(card, 'status_md') and card.status_md:
        embed.add_field(name="Master Duel Status", value=card.status_md, inline=True)

    if hasattr(card, 'rarity_dl') and card.rarity_dl:
        embed.add_field(name="Duel Links Rarity", value=card.rarity_dl, inline=True)

    if hasattr(card, 'rarity_md') and card.rarity_md:
        embed.add_field(name="Master Duel Rarity", value=card.rarity_md, inline=True)

    # Monster type information
    if hasattr(card, 'race') and card.race:
        embed.add_field(name="Subtype", value=card.race, inline=True)

    if hasattr(card, 'monster_type') and card.monster_type:
        embed.add_field(name="Monster Type", value=card.monster_type.title(), inline=True)

    # Set information
    if hasattr(card, 'sets_dl') and card.sets_dl:
        dl_sets = ', '.join(card.sets_dl[:3])  # Show first 3 sets
        if len(card.sets_dl) > 3:
            dl_sets += f" (+{len(card.sets_dl) - 3} more)"
        embed.add_field(name="Duel Links Sets", value=dl_sets, inline=False)

    if hasattr(card, 'sets_md') and card.sets_md:
        md_sets = ', '.join(card.sets_md[:3])  # Show first 3 sets
        if len(card.sets_md) > 3:
            md_sets += f" (+{len(card.sets_md) - 3} more)"
        embed.add_field(name="Master Duel Sets", value=md_sets, inline=False)

    return embed
