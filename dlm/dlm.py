from typing import Optional, Dict, Any, List
import discord
import aiohttp
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

    async def cog_load(self) -> None:
        self.session = aiohttp.ClientSession()

    async def cog_unload(self) -> None:
        if self.session:
            await self.session.close()

    async def _api_request(self, endpoint: str, params: Dict = None) -> Dict[str, Any]:
        cache_key = f"{endpoint}:{str(params)}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data
        if not self.session:
            raise DLMAPIError("No session available")
        try:
            async with self.session.get(
                f"{self.BASE_URL}/{endpoint}",
                params=params
            ) as resp:
                data = await handle_api_response(resp)
                ttl = parse_cache_control(resp.headers.get('cache-control'))
                self.cache.set(cache_key, data, ttl)
                return data
        except aiohttp.ClientError as e:
            raise DLMAPIError(f"Network error: {str(e)}")

    async def _fuzzy_search(self, query: str, items: List[Dict], key: str = "title", threshold: float = 0.6) -> List[Dict]:
        from difflib import SequenceMatcher
        def similarity(a: str, b: str) -> float:
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        results = []
        query = query.lower()
        for item in items:
            if key not in item:
                continue
            score = similarity(query, item[key])
            if score >= threshold:
                item['_score'] = score
                results.append(item)
        return sorted(results, key=lambda x: x['_score'], reverse=True)

    def format_article_embed(self, article: Dict[str, Any]) -> discord.Embed:
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
        return messages.get(error_type, "An unexpected error occurred.").format(context if context else "")

    @staticmethod
    def format_cooldown(seconds: float) -> str:
        """Format cooldown time in a user-friendly way."""
        return f"{round(seconds)} seconds"

    @commands.group(name="dlm")
    async def dlm(self, ctx):
        """DuelLinksMeta commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm.group(name="search")
    async def search_group(self, ctx):
        """Search commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm.group(name="card")
    async def card_group(self, ctx):
        """Card database commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm.group(name="decks")
    async def decks_group(self, ctx):
        """Deck-related commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm.group(name="tournament")
    async def tournament_group(self, ctx):
        """Tournament related commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @dlm.group(name="meta")
    async def meta_group(self, ctx):
        """Meta analysis commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @search_group.command(name="articles")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def search_articles(self, ctx, *, query: str):
        try:
            async with ctx.typing():
                params = {"q": query, "limit": 10}
                results = await self._api_request("articles/search", params)
                if not results:
                    params = {"limit": 50, "fields": "title,description,url,date"}
                    articles = await self._api_request("articles", params)
                    results = self._fuzzy_search(query, articles)
                if not results:
                    return await ctx.send("No articles found matching your search.")
                embeds = [self.format_article_embed(article) for article in results[:5]]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error searching articles: {str(e)}")

    @dlm.command(name="latest")
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
                articles = await self._api_request("articles", params)
                if not articles:
                    return await ctx.send("No articles found.")
                embeds = [self.format_article_embed(article) for article in articles]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching articles: {str(e)}")

    @search_group.command(name="decks")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def search_decks(self, ctx, *, query: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self._api_request("top-decks", params)
                results = self._fuzzy_search(query, decks, key="name")
                if not results:
                    return await ctx.send("No decks found matching your search.")
                embeds = []
                for deck in results[:5]:
                    embed = discord.Embed(
                        title=deck.get("name", "Unnamed Deck"),
                        url=f"https://www.duellinksmeta.com/top-decks/{deck.get('id')}",
                        color=discord.Color.blue()
                    )
                    if "author" in deck:
                        embed.add_field(name="Author", value=deck["author"], inline=True)
                    if "price" in deck:
                        embed.add_field(name="Price", value=f"{deck['price']:,} gems", inline=True)
                    if "skillName" in deck:
                        embed.add_field(name="Skill", value=deck["skillName"], inline=True)
                    match_score = round(deck.get('_score', 0) * 100)
                    embed.set_footer(text=f"Match Score: {match_score}%")
                    embeds.append(embed)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error searching decks: {str(e)}")

    @decks_group.command(name="skill")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_skill(self, ctx, *, skill_name: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("skillName", "").lower() == skill_name.lower()]
                if not results:
                    results = self._fuzzy_search(skill_name, decks, key="skillName")
                if not results:
                    return await ctx.send("No decks found with that skill.")
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
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="budget")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def budget_decks(self, ctx, max_gems: int = 30000):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("price", float('inf')) <= max_gems]
                if not results:
                    return await ctx.send(f"No decks found under {max_gems:,} gems.")
                results.sort(key=lambda x: x.get("price", 0))
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
            await ctx.send(f"Error fetching decks: {str(e)}")

    @decks_group.command(name="author")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def decks_by_author(self, ctx, *, author_name: str):
        try:
            async with ctx.typing():
                params = {"limit": 50}
                decks = await self._api_request("top-decks", params)
                results = [deck for deck in decks if deck.get("author", "").lower() == author_name.lower()]
                if not results:
                    results = self._fuzzy_search(author_name, decks, key="author")
                if not results:
                    return await ctx.send("No decks found by that author.")
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
            await ctx.send(f"Error fetching decks: {str(e)}")

    @tournament_group.command(name="recent")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def recent_tournaments(self, ctx, limit: int = 5):
        """Show recent tournament results."""
        try:
            if limit > 10:
                limit = 10
            async with ctx.typing():
                params = {
                    "limit": limit,
                    "sort": "-date"
                }
                tournaments = await self._api_request("tournaments", params)
                if not tournaments:
                    return await ctx.send("No tournament data found.")
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
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching tournament data: {str(e)}")

    @meta_group.command(name="skills")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def top_skills(self, ctx):
        """Show most used skills in the current meta."""
        try:
            async with ctx.typing():
                params = {"limit": 100}
                decks = await self._api_request("top-decks", params)
                skill_counts = {}
                for deck in decks:
                    skill = deck.get("skillName")
                    if skill:
                        skill_counts[skill] = skill_counts.get(skill, 0) + 1
                sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
                embed = discord.Embed(
                    title="Most Used Skills in Current Meta",
                    color=discord.Color.blue()
                )
                for skill, count in sorted_skills[:10]:
                    percentage = (count / len(decks)) * 100
                    embed.add_field(
                        name=skill,
                        value=f"Used in {count} decks ({percentage:.1f}%)",
                        inline=False
                    )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error analyzing meta data: {str(e)}")

    @card_group.command(name="search")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def search_cards(self, ctx, *, query: str):
        """Search for cards by name."""
        if not query:
            await ctx.send("Please provide a card name to search for.")
            return

        try:
            async with ctx.typing():
                params = {
                    "q": query.lower(),
                    "limit": 10
                }
                results = await self._api_request("cards/search", params)
                
                if not results:
                    params = {"limit": 200}
                    cards = await self._api_request("cards", params)
                    results = await self._fuzzy_search(query, cards, key="name", threshold=0.5)
                
                if not results:
                    suggestion_msg = ""
                    if len(query) > 3:
                        similar_cards = await self._api_request("cards/search", {"q": query[:3], "limit": 3})
                        if similar_cards:
                            suggestions = [card["name"] for card in similar_cards]
                            suggestion_msg = f"\n\nDid you mean one of these?\n" + "\n".join(f"• {name}" for name in suggestions)
                    
                    await ctx.send(f"No cards found matching '{query}'.{suggestion_msg}")
                    return

                embeds = [self.format_card_embed(card) for card in results[:5]]
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)

        except DLMAPIError as e:
            error_msg = self.format_error_message("api")
            if "not found" in str(e).lower():
                error_msg = self.format_error_message("not_found", "card")
            await ctx.send(error_msg)

    @card_group.command(name="detail")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def card_detail(self, ctx, *, card_name: str):
        """Get detailed information about a specific card."""
        try:
            async with ctx.typing():
                params = {"name": card_name}
                card = await self._api_request(f"cards/detail", params)
                if not card:
                    results = await self.search_cards(ctx, query=card_name)
                    if not results or not results[0].get('_score', 0) > 0.8:
                        return await ctx.send("Could not find a matching card. Please try a more specific name.")
                    card = results[0]
                embed = self.format_card_embed(card)
                if "releaseDate" in card:
                    embed.add_field(
                        name="Release Date",
                        value=datetime.fromisoformat(card["releaseDate"].replace("Z", "+00:00")).strftime("%Y-%m-%d"),
                        inline=True
                    )
                if "banStatus" in card:
                    embed.add_field(
                        name="Ban Status",
                        value=card["banStatus"].title(),
                        inline=True
                    )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching card details: {str(e)}")

    @card_group.command(name="random")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def random_card(self, ctx):
        """Get information about a random card."""
        try:
            async with ctx.typing():
                card = await self._api_request("cards/random")
                if not card:
                    return await ctx.send("Error fetching random card.")
                embed = self.format_card_embed(card)
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching random card: {str(e)}")

    @card_group.command(name="box")
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def cards_from_box(self, ctx, *, box_name: str):
        """List cards available in a specific box."""
        try:
            async with ctx.typing():
                box_name = box_name.strip().lower()
                
                params = {"box": box_name}
                cards = await self._api_request("cards/box", params)
                
                if not cards:
                    boxes = await self._api_request("boxes", {"limit": 50})
                    similar_boxes = self._fuzzy_search(box_name, boxes, key="name", threshold=0.6)
                    
                    if similar_boxes:
                        suggestions = [box["name"] for box in similar_boxes[:3]]
                        suggestion_msg = "\n\nDid you mean one of these boxes?\n" + "\n".join(f"• {name}" for name in suggestions)
                        await ctx.send(f"Box '{box_name}' not found.{suggestion_msg}")
                        return
                    else:
                        await ctx.send(f"No box found matching '{box_name}'.")
                        return

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

                for rarity, card_list in sorted(cards_by_rarity.items()):
                    card_names = ", ".join(sorted(card_list))
                    if len(card_names) > 1024:
                        card_names = card_names[:1021] + "..."
                    embed.add_field(
                        name=f"{rarity} Cards",
                        value=card_names,
                        inline=False
                    )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            error_msg = self.format_error_message("api")
            if "not found" in str(e).lower():
                error_msg = self.format_error_message("not_found", "box")
            await ctx.send(error_msg)

    @dlm.command(name="tier")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def tier_list(self, ctx):
        try:
            async with ctx.typing():
                data = await self._api_request("tier-list")
                embed = discord.Embed(
                    title="Current DLM Tier List",
                    url="https://www.duellinksmeta.com/tier-list/",
                    color=discord.Color.blue()
                )
                for tier in data.get("tiers", []):
                    decks = ", ".join(deck["name"] for deck in tier.get("decks", []))
                    if decks:
                        embed.add_field(
                            name=f"Tier {tier['name']}",
                            value=decks,
                            inline=False
                        )
                await ctx.send(embed=embed)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching tier list: {str(e)}")

    @dlm.command(name="events")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def current_events(self, ctx):
        try:
            async with ctx.typing():
                data = await self._api_request("events/active")
                if not data:
                    return await ctx.send("No active events found.")
                embeds = []
                for event in data:
                    embed = discord.Embed(
                        title=event.get("title", "Unknown Event"),
                        description=event.get("description", "No description available."),
                        color=discord.Color.blue()
                    )
                    if "startDate" in event and "endDate" in event:
                        start = datetime.fromisoformat(event["startDate"].replace("Z", "+00:00"))
                        end = datetime.fromisoformat(event["endDate"].replace("Z", "+00:00"))
                        embed.add_field(
                            name="Duration",
                            value=f"From {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
                            inline=False
                        )
                    if "image" in event:
                        embed.set_thumbnail(url=f"https://www.duellinksmeta.com{event['image']}")
                    embeds.append(embed)
                if len(embeds) == 1:
                    await ctx.send(embed=embeds[0])
                else:
                    await menu(ctx, embeds, DEFAULT_CONTROLS)
        except DLMAPIError as e:
            await ctx.send(f"Error fetching events: {str(e)}")

    @dlm.command(name="cache")
    @commands.is_owner()
    async def clear_cache(self, ctx):
        """Clear the API cache (Bot owner only)."""
        self.cache.clear()
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

