from typing import Optional, Dict, Any, List
import discord
import aiohttp
import asyncio
import logging
from datetime import datetime
from redbot.core import commands, Config
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .cache import (
    DLMCache, 
    DLMAPIError, 
    DLMRateLimitError, 
    DLMNotFoundError, 
    DLMServerError, 
    handle_api_response, 
    parse_cache_control
)

log = logging.getLogger("red.dlm")

class DLM(commands.Cog):
    """DuelLinksMeta Information Cog"""

    BASE_URL = "https://www.duellinksmeta.com/api/v1"

    def __init__(self, bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = DLMCache()
        self.headers = {
            'User-Agent': 'IP:Masquerena',
            'Accept': 'application/json'
        }
        self.config = Config.get_conf(self, identifier=8675309991)
        default_guild = {
            "auto_news": False,
            "news_channel": None,
            "last_article_id": None,
            "tournament_notifications": False
        }
        self.config.register_guild(**default_guild)
        log.info("DLM cog initialized")

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()
        log.info("DLM cog loaded, session created")

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()
            log.info("DLM cog unloaded, session closed")

    async def _api_request(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        cache_key = f"{endpoint}:{str(params)}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            log.debug(f"Cache hit for {cache_key}")
            return cached_data
        if not self.session:
            log.error("No session available for API request")
            raise DLMAPIError("No session available")
        try:
            log.debug(f"Making API request to {endpoint} with params {params}")
            async with self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params
            ) as resp:
                data = await handle_api_response(resp)
                ttl = parse_cache_control(resp.headers.get('cache-control'))
                self.cache.set(cache_key, data, ttl)
                log.debug(f"API request successful, cached with TTL {ttl}")
                return data
        except aiohttp.ClientError as e:
            log.error(f"Network error during API request: {str(e)}")
            raise DLMAPIError(f"Network error: {str(e)}")

    async def _fuzzy_search(self, query: str, items: List[Dict], key: str = "title", threshold: float = 0.6) -> List[Dict]:
        from difflib import SequenceMatcher
        def similarity(a: str, b: str) -> float:
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        results = []
        query = query.lower()
        log.debug(f"Performing fuzzy search for '{query}' with threshold {threshold}")
        for item in items:
            if key not in item:
                continue
            score = similarity(query, item[key])
            if score >= threshold:
                item['_score'] = score
                results.append(item)
        log.debug(f"Fuzzy search found {len(results)} results")
        return sorted(results, key=lambda x: x['_score'], reverse=True)

    def format_article_embed(self, article: Dict[str, Any]) -> discord.Embed:
        log.debug(f"Formatting article embed for {article.get('title', 'Unknown Title')}")
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

    def format_card_embed(self, card: Dict[str, Any]) -> discord.Embed:
        log.debug(f"Formatting card embed for {card.get('name', 'Unknown Card')}")
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

        if "level" in card or "atk" in card or "def" in card:
            stats = []
            if "level" in card:
                stats.append(f"Level/Rank: {card['level']}")
            if "atk" in card:
                stats.append(f"ATK: {card['atk']}")
            if "def" in card:
                stats.append(f"DEF: {card['def']}")
            if stats:
                embed.add_field(name="Stats", value="\n".join(stats), inline=True)

        if "obtain" in card:
            obtain_methods = ", ".join(card["obtain"])
            embed.add_field(name="How to Obtain", value=obtain_methods, inline=False)

        if "image" in card:
            embed.set_thumbnail(url=f"https://www.duellinksmeta.com{card['image']}")
        if "rarity" in card:
            embed.set_footer(text=f"Rarity: {card['rarity']}")

        return embed
    
    def format_error_message(self, error_type: str, context: str = None) -> str:
        """Format user-friendly error messages."""
        messages = {
            "not_found": "I couldn't find that {}. Please check your spelling and try again.",
            "rate_limit": "This request is rate-limited. Please try again in {} seconds.",
            "network": "There was a problem connecting to DuelLinksMeta. Please try again in a few minutes.",
            "api": "There was an issue with the API. Please try again later."
        }
        error_message = messages.get(error_type, "An unexpected error occurred.").format(context if context else "")
        log.error(f"Error occurred: {error_type} - {error_message}")
        return error_message

    @staticmethod
    def format_cooldown(seconds: float) -> str:
        """Format cooldown time in a user-friendly way."""
        return f"{round(seconds)} seconds"

    @commands.group(name="dlm")
    async def dlm(self, ctx):
        """DuelLinksMeta commands."""
        pass

    @dlm.group(name="search")
    async def search_group(self, ctx):
        """Search commands."""
        pass

    @dlm.group(name="card")
    async def card_group(self, ctx):
        """Card database commands."""
        pass

    @dlm.group(name="decks")
    async def decks_group(self, ctx):
        """Deck-related commands."""
        pass

    @dlm.group(name="tournament")
    async def tournament_group(self, ctx):
        """Tournament related commands."""
        pass

    @dlm.group(name="meta")
    async def meta_group(self, ctx):
        """Meta analysis commands."""
        pass

    @search_group.command(name="articles")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def search_articles(self, ctx, *, query: str):
        log.debug(f"Searching articles with query: {query}")
        try:
            async with ctx.typing():
                params = {"q": query, "limit": 10}
                log.debug(f"Making initial search request with params: {params}")
                results = await self._api_request("articles/search", params)
                if not results:
                    log.debug("No direct search results, attempting fuzzy search")
                    params = {"limit": 50, "fields": "title,description,url,date"}
                    articles = await self._api_request("articles", params)
                    results = self._fuzzy_search(query, articles)
                if not results:
                    log.debug("No articles found for query")
                    return await ctx.send("No articles found matching your search.")
                log.debug(f"Found {len(results)} articles, formatting first 5")
                embeds = [self.format_article_embed(article) for article in results[:5]]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error searching articles: {str(e)}")
            await ctx.send(f"Error searching articles: {str(e)}")

    @dlm.command(name="latest")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def latest_articles(self, ctx, limit: int = 5):
        log.debug(f"Fetching latest {limit} articles")
        try:
            if limit > 10:
                limit = 10
                log.debug("Adjusted limit to maximum of 10 articles")
                await ctx.send("Limiting results to 10 articles maximum.")
            async with ctx.typing():
                params = {
                    "limit": limit,
                    "fields": "-markdown",
                    "sort": "-featured,-date"
                }
                log.debug(f"Requesting articles with params: {params}")
                articles = await self._api_request("articles", params)
                if not articles:
                    log.debug("No articles found")
                    return await ctx.send("No articles found.")
                log.debug(f"Formatting {len(articles)} articles")
                embeds = [self.format_article_embed(article) for article in articles]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching latest articles: {str(e)}")
            await ctx.send(f"Error fetching articles: {str(e)}")

    
    @decks_group.command(name="skill")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_skill(self, ctx, *, skill_name: str):
        log.debug(f"Searching decks with skill: {skill_name}")
        try:
            async with ctx.typing():
                params = {"limit": 50}
                log.debug(f"Requesting top-decks with params: {params}")
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("skillName", "").lower() == skill_name.lower()]
                if not results:
                    log.debug("No exact skill match found, attempting fuzzy search")
                    results = self._fuzzy_search(skill_name, decks, key="skillName")
                if not results:
                    log.debug("No decks found with specified skill")
                    return await ctx.send("No decks found with that skill.")
                log.debug(f"Found {len(results)} decks, formatting first 5")
                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=f"{deck.get('name', 'Unnamed Deck')} ({deck.get('skillName')})",
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        color=discord.Color.blue()
                    )
                    if "author" in deck:
                        embed.add_field(name="Author", value=deck["author"], inline=True)
                    if "price" in deck:
                        embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
                    embeds.append(embed)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching decks by skill: {str(e)}")
            await ctx.send(f"Error fetching decks: {str(e)}") 

    @decks_group.command(name="budget")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def budget_decks(self, ctx, max_gems: int = 30000):
        log.debug(f"Searching for budget decks under {max_gems:,} gems")
        try:
            async with ctx.typing():
                params = {"limit": 50}
                log.debug(f"Requesting top-decks with params: {params}")
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("price", float('inf')) <= max_gems]
                if not results:
                    log.debug(f"No decks found under {max_gems:,} gems")
                    return await ctx.send(f"No decks found under {max_gems:,} gems.")
                results.sort(key=lambda x: x.get("price", 0))
                log.debug(f"Found {len(results)} decks, formatting first 5")
                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=deck.get("name", "Unnamed Deck"),
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        description=f"💎 {deck.get('price', 'N/A'):,} gems",
                        color=discord.Color.blue()
                    )
                    if "author" in deck:
                        embed.add_field(name="Author", value=deck["author"], inline=True)
                    if "skillName" in deck:
                        embed.add_field(name="Skill", value=deck["skillName"], inline=True)
                    embeds.append(embed)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching budget decks: {str(e)}")
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="author")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_author(self, ctx, *, author_name: str):
        log.debug(f"Searching decks by author: {author_name}")
        try:
            async with ctx.typing():
                params = {"limit": 50}
                log.debug(f"Requesting top-decks with params: {params}")
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("author", "").lower() == author_name.lower()]
                if not results:
                    log.debug("No exact author match found, attempting fuzzy search")
                    results = self._fuzzy_search(author_name, decks, key="author")
                if not results:
                    log.debug("No decks found by specified author")
                    return await ctx.send("No decks found by that author.")
                log.debug(f"Found {len(results)} decks, formatting first 5")
                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=deck.get("name", "Unnamed Deck"),
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        color=discord.Color.blue()
                    )
                    if "skillName" in deck:
                        embed.add_field(name="Skill", value=deck["skillName"], inline=True)
                    if "price" in deck:
                        embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
                    embed.set_footer(text=f"By {deck.get('author')}")
                    embeds.append(embed)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching decks by author: {str(e)}")
            await ctx.send(f"Error fetching decks: {str(e)}")

    @tournament_group.command(name="recent")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def recent_tournaments(self, ctx, limit: int = 5):
        """Show recent tournament results."""
        log.debug(f"Fetching recent {limit} tournaments")
        try:
            if limit > 10:
                limit = 10
                log.debug("Adjusted limit to maximum of 10 tournaments")
            async with ctx.typing():
                params = {
                    "limit": limit,
                    "sort": "-date"
                }
                log.debug(f"Requesting tournaments with params: {params}")
                tournaments = await self._api_request("tournaments", params)
                if not tournaments:
                    log.debug("No tournament data found")
                    return await ctx.send("No tournament data found.")
                log.debug(f"Found {len(tournaments)} tournaments, formatting embeds")
                embeds = []
                for tourney in tournaments:
                    embed = discord.Embed(
                        title=tourney.get("name", "Unnamed Tournament"),
                        url=f"https://www.duellinksmeta.com/tournaments/{tourney.get('id')}",
                        color=discord.Color.blue(),
                        timestamp=datetime.fromisoformat(tourney["date"].replace("Z", "+00:00"))
                    )
                    if "participants" in tourney:
                        embed.add_field(
                            name="Participants",
                            value=str(tourney["participants"]),
                            inline=True
                        )
                    if "winner" in tourney:
                        embed.add_field(
                            name="Winner",
                            value=tourney["winner"],
                            inline=True
                        )
                    if "format" in tourney:
                        embed.add_field(
                            name="Format",
                            value=tourney["format"],
                            inline=True
                        )
                    embeds.append(embed)
                log.debug(f"Sending {len(embeds)} tournament embeds")
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching tournament data: {str(e)}")
            await ctx.send(f"Error fetching tournament data: {str(e)}")

    @meta_group.command(name="skills")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def top_skills(self, ctx):
        """Show most used skills in the current meta."""
        log.debug("Fetching top skills data")
        try:
            async with ctx.typing():
                params = {"limit": 100}
                log.debug(f"Requesting top-decks with params: {params}")
                decks = await self._api_request("top-decks", params)
                skill_counts = {}
                log.debug("Processing skill usage counts")
                for deck in decks:
                    skill = deck.get("skillName")
                    if skill:
                        skill_counts[skill] = skill_counts.get(skill, 0) + 1
                sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
                log.debug(f"Found {len(sorted_skills)} unique skills")
                embed = discord.Embed(
                    title="Most Used Skills in Current Meta",
                    color=discord.Color.blue()
                )
                log.debug("Formatting top 10 skills for embed")
                for skill, count in sorted_skills[:10]:
                    percentage = (count / len(decks)) * 100
                    embed.add_field(
                        name=skill,
                        value=f"Used in {count} decks ({percentage:.1f}%)",
                        inline=False
                    )
                log.debug("Sending skills embed")
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            log.error(f"Error analyzing meta data: {str(e)}")
            await ctx.send(f"Error analyzing meta data: {str(e)}")

    @card_group.command(name="search")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def card_search(self, ctx, *, query: str = None):
        """Search for cards by name with detailed information."""
        log.debug(f"Starting card search with query: {query}")
        if not query:
            log.debug("No initial query provided, prompting user")
            prompt_msg = await ctx.send("Please enter the name of the card you want to look up:")
            try:
                response = await self.bot.wait_for(
                    'message',
                    timeout=30.0,
                    check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                )
                query = response.content
                log.debug(f"User provided query: {query}")
            except asyncio.TimeoutError:
                log.debug("Search prompt timed out")
                return await prompt_msg.edit(content="Search timed out. Please try again.")

        try:
            async with ctx.typing():
                params = {"name": query}
                log.debug(f"Attempting exact match with params: {params}")
                try:
                    card = await self._api_request(f"cards/detail", params)
                    log.debug("Found exact card match")
                except DLMNotFoundError:
                    log.debug("No exact match found")
                    card = None
            
                if not card:
                    params = {"q": query.lower(), "limit": 5}
                    log.debug(f"Attempting search with params: {params}")
                    try:
                        results = await self._api_request("cards/search", params)
                        log.debug(f"Search found {len(results)} results")
                    except DLMNotFoundError:
                        log.debug("Search found no results")
                        results = []
                
                    if not results:
                        params = {"limit": 200}
                        log.debug("Attempting fuzzy search")
                        cards = await self._api_request("cards", params)
                        results = self._fuzzy_search(query, cards, key="name", threshold=0.6)
                        log.debug(f"Fuzzy search found {len(results)} results")
                
                    if not results:
                        suggestion_msg = ""
                        if len(query) > 3:
                            log.debug("Attempting to find similar cards for suggestions")
                            try:
                                similar_cards = await self._api_request("cards/search", {"q": query[:3], "limit": 3})
                                if similar_cards:
                                    suggestions = [card["name"] for card in similar_cards]
                                    suggestion_msg = f"\n\nDid you mean one of these?\n" + "\n".join(f"• {name}" for name in suggestions)
                                    log.debug(f"Found {len(suggestions)} card suggestions")
                            except DLMAPIError:
                                log.debug("Failed to get card suggestions")
                                pass
                
                        return await ctx.send(f"No cards found matching '{query}'.{suggestion_msg}")

                    if len(results) > 1:
                        log.debug("Multiple results found, presenting choice to user")
                        options = "\n".join(f"{idx+1}. {card['name']}" for idx, card in enumerate(results[:5]))
                        choice_msg = await ctx.send(f"Multiple cards found. Please choose one by number:\n{options}")
                    
                        try:
                            response = await self.bot.wait_for(
                                'message',
                                timeout=30.0,
                                check=lambda m: (
                                    m.author == ctx.author and 
                                    m.channel == ctx.channel and 
                                    m.content.isdigit() and 
                                    1 <= int(m.content) <= len(results)
                                )
                            )
                            card = results[int(response.content) - 1]
                            log.debug(f"User selected card: {card.get('name')}")
                        except asyncio.TimeoutError:
                            log.debug("Card selection timed out")
                            return await choice_msg.edit(content="Selection timed out. Please try again.")
                    else:
                        card = results[0]
                        log.debug(f"Using single result: {card.get('name')}")

                embed = self.format_card_embed(card)
                log.debug("Sending card embed")
                await ctx.send(embed=embed)

        except DLMAPIError as e:
            log.error(f"API error during card search: {str(e)}")
            error_msg = self.format_error_message("api")
            if isinstance(e, DLMNotFoundError):
                error_msg = self.format_error_message("not_found", "card")
            elif isinstance(e, DLMRateLimitError):
                error_msg = self.format_error_message("rate_limit", str(e))
            await ctx.send(error_msg)

    @card_group.command(name="random")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def random_card(self, ctx):
        """Get information about a random card."""
        log.debug("Fetching random card")
        try:
            async with ctx.typing():
                card = await self._api_request("cards/random")
                if not card:
                    log.debug("No random card data received")
                    return await ctx.send("Error fetching random card.")
                log.debug(f"Formatting random card: {card.get('name', 'Unknown')}")
                embed = self.format_card_embed(card)
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            log.error(f"Error fetching random card: {str(e)}")
            await ctx.send(f"Error fetching random card: {str(e)}")

    @card_group.command(name="box")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def cards_from_box(self, ctx, *, box_name: str):
        """List cards available in a specific box."""
        log.debug(f"Searching for cards in box: {box_name}")
        try:
            async with ctx.typing():
                box_name = box_name.strip().lower()
                log.debug(f"Normalized box name: {box_name}")
                
                params = {"box": box_name}
                log.debug(f"Requesting box cards with params: {params}")
                cards = await self._api_request("cards/box", params)
                
                if not cards:
                    log.debug("No cards found, attempting to find similar boxes")
                    boxes = await self._api_request("boxes", {"limit": 50})
                    similar_boxes = self._fuzzy_search(box_name, boxes, key="name", threshold=0.6)
                    
                    if similar_boxes:
                        log.debug(f"Found {len(similar_boxes)} similar boxes")
                        suggestions = [box["name"] for box in similar_boxes[:3]]
                        suggestion_msg = "\n\nDid you mean one of these boxes?\n" + "\n".join(f"• {name}" for name in suggestions)
                        await ctx.send(f"Box '{box_name}' not found.{suggestion_msg}")
                        return
                    else:
                        log.debug("No similar boxes found")
                        await ctx.send(f"No box found matching '{box_name}'.")
                        return

                log.debug(f"Found {len(cards)} cards in box {box_name}")
                embed = discord.Embed(
                    title=f"Cards in {box_name}",
                    color=discord.Color.blue()
                )
                cards_by_rarity = {}
                for card in cards:
                    rarity = card.get("rarity", "Unknown")
                    if rarity not in cards_by_rarity:
                        cards_by_rarity[rarity] = []
                    cards_by_rarity[rarity].append(card["name"])

                log.debug(f"Organizing cards by {len(cards_by_rarity)} rarities")
                for rarity, card_list in sorted(cards_by_rarity.items()):
                    card_names = ", ".join(sorted(card_list))
                    if len(card_names) > 1024:
                        log.debug(f"Truncating {rarity} card list due to length")
                        card_names = card_names[:1021] + "..."
                    embed.add_field(
                        name=f"{rarity} Cards",
                        value=card_names,
                        inline=False
                    )
                log.debug("Sending box cards embed")
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            log.error(f"Error fetching box cards: {str(e)}")
            error_msg = self.format_error_message("api")
            if "not found" in str(e).lower():
                error_msg = self.format_error_message("not_found", "box")
            await ctx.send(error_msg)

    @dlm.command(name="tier")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tier_list(self, ctx):
        log.debug("Fetching tier list data")
        try:
            async with ctx.typing():
                data = await self._api_request("tier-list")
                log.debug("Creating tier list embed")
                embed = discord.Embed(
                    title="Current DLM Tier List",
                    url="https://www.duellinksmeta.com/tier-list/",
                    color=discord.Color.blue()
                )
                log.debug("Processing tier data")
                for tier in data.get("tiers", []):
                    decks = ", ".join(deck["name"] for deck in tier.get("decks", []))
                    if decks:
                        log.debug(f"Adding Tier {tier['name']} with {len(tier.get('decks', []))} decks")
                        embed.add_field(
                            name=f"Tier {tier['name']}",
                            value=decks,
                            inline=False
                        )
                log.debug("Sending tier list embed")
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            log.error(f"Error fetching tier list: {str(e)}")
            await ctx.send(f"Error fetching tier list: {str(e)}")

    @dlm.command(name="events")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def current_events(self, ctx):
        log.debug("Fetching current events")
        try:
            async with ctx.typing():
                data = await self._api_request("events/active")
                if not data:
                    log.debug("No active events found")
                    return await ctx.send("No active events found.")
                log.debug(f"Processing {len(data)} active events")
                embeds = []
                for event in data:
                    log.debug(f"Creating embed for event: {event.get('title', 'Unknown Event')}")
                    embed = discord.Embed(
                        title=event.get("title", "Unknown Event"),
                        description=event.get("description", "No description available."),
                        color=discord.Color.blue()
                    )
                    if "startDate" in event and "endDate" in event:
                        start = datetime.fromisoformat(event["startDate"].replace("Z", "+00:00"))
                        end = datetime.fromisoformat(event["endDate"].replace("Z", "+00:00"))
                        log.debug(f"Adding duration field: {start} to {end}")
                        embed.add_field(
                            name="Duration",
                            value=f"From {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
                            inline=False
                        )
                    if "image" in event:
                        log.debug("Setting event thumbnail")
                        embed.set_thumbnail(url=f"https://www.duellinksmeta.com{event['image']}")
                    embeds.append(embed)
                log.debug(f"Sending {len(embeds)} event embeds")
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            log.error(f"Error fetching events: {str(e)}")
            await ctx.send(f"Error fetching events: {str(e)}")

    @dlm.command(name="cache")
    @commands.is_owner()
    async def clear_cache(self, ctx):
        """Clear the API cache (Bot owner only)."""
        log.info("Clearing API cache")
        self.cache.clear()
        log.info("Cache cleared successfully")
        await ctx.send("Cache cleared successfully!")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {self.format_cooldown(error.retry_after)}.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument provided. Please check the command help for correct usage.")
        else:
            await ctx.send("An error occurred while processing your command. Please try again later.")


