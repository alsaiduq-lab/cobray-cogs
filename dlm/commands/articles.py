from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
from typing import List
from datetime import datetime
from ..core.api import DLMApi, DLMAPIError
from ..utils.embeds import format_article_embed
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.articles")

class ArticleCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.command(name="articles")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def articles(self, ctx, *, query: str = None):
        """List articles, optionally filtered by search query."""
        async with ctx.typing():
            try:
                if query:
                    params = {"q": query, "limit": 10}
                    articles = await self.api.request("articles/search", params)
                    if not articles:
                        return await ctx.send(f"No articles found matching: {query}")
                else:
                    params = {
                        "limit": 10,
                        "fields": "title,description,date,url,image,category,authors",
                        "sort": "-date"
                    }
                    articles = await self.api.request("articles", params)
                    if not articles:
                        return await ctx.send("No articles available.")

                embeds = []
                for article in articles[:5]:
                    try:
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
                        embeds.append(embed)
                    except Exception as e:
                        log.error(f"Error formatting article embed: {str(e)}")

                if embeds:
                    if len(embeds) == 1:
                        await ctx.send(embed=embeds[0])
                    else:
                        await menu(ctx, embeds, DEFAULT_CONTROLS)
                else:
                    await ctx.send("No articles could be formatted for display.")

            except DLMAPIError as e:
                log.error(f"Error fetching articles: {str(e)}")
                await ctx.send("Error fetching articles. Please try again later.")
