import discord
from datetime import datetime
from typing import Dict, Any

def format_article_embed(article: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=article.get("title", "No Title"),
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

def format_card_embed(card: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(
        title=card.get("name", "Unknown Card"),
        url=f"https://www.duellinksmeta.com/cards/{card.get('id')}",
        color=discord.Color.blue()
    )
    if "description" in card:
        embed.description = card["description"]

    card_info = []
    if "type" in card:
        card_info.append(f"Type: {card['type']}")
    if "attribute" in card:
        card_info.append(f"Attribute: {card['attribute']}")
    if card_info:
        embed.add_field(name="Card Info", value="\n".join(card_info), inline=False)

    return embed
