from redbot.core import commands
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS
import discord
import logging
from ..core.api import DLMApi, DLMAPIError
from ..utils.embeds import format_article_embed
from ..utils.fsearch import fuzzy_search

log = logging.getLogger("red.dlm.articles")

class ArticleCommands(commands.Cog):
    def __init__(self, bot, api: DLMApi):
        self.bot = bot
        self.api = api

    @commands.group(name="search")
    async def search_group(self, ctx):
        """Search commands."""
        pass

    @search_group.command(name="articles")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def search_articles(self, ctx, *, query: str):
        try:
            async with ctx.typing():
                params = {"q": query, "limit": 10}
                results = await self.api.request("articles/search", params)
                if not results:
                    params = {"limit": 50, "fields": "title,description,url,date"}
                    articles = await self.api.request("articles", params)
                    results = fuzzy_search(query, articles)
                if not results:
                    return await ctx.send("No articles found matching your search.")

                embeds = [format_article_embed(article) for article in results[:5]]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error searching articles: {str(e)}")

    @commands.command(name="latest")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def latest_articles(self, ctx, limit: int = 5):
        try:
            if limit > 10:
                limit = 10
                await ctx.send("Limiting results to 10 articles maximum.")
            async with ctx.typing():
                params = {
                    "limit": limit,
                    "fields": "-markdown",
                    "sort": "-featured,-date"
                }
                articles = await self.api.request("articles", params)
                if not articles:
                    return await ctx.send("No articles found.")

                embeds = [format_article_embed(article) for article in articles]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching articles: {str(e)}")
