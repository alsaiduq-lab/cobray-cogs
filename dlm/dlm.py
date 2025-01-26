import discord
from redbot.core import commands, Config
import logging
import asyncio
import datetime
from typing import Optional
from .core.registry import CardRegistry
from .core.interactions import InteractionHandler
from .core.user_config import UserConfig
from .utils.parser import CardParser

log = logging.getLogger("red.dlm")

class ArticleCommands:
    """
    Handles subcommands for articles.
    """
    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry
        log.debug("ArticleCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="articles")
        async def dlm_articles(ctx: commands.Context, *, query: str = None):
            """
            Example usage: -dlm articles <query>
            If no query is provided, returns the latest article.
            """
            log.info(f"Article search requested by {ctx.author} with query: {query}")
            if not query:
                articles = await self.registry.get_latest_articles(limit=3)
                if not articles:
                    await ctx.send("No articles found.")
                    return
                latest = articles[0]
                await ctx.send(
                    f"Latest article: {latest.title}\n"
                    f"https://duellinksmeta.com{latest.url}"
                )
                return

            results = await self.registry.search_articles(query)
            if not results:
                await ctx.send(f"No articles found matching: {query}")
                return

            response_lines = ["Found articles:"]
            for article in results:
                response_lines.append(f"• {article.title}")
            await ctx.send("\n".join(response_lines))

class CardCommands:
    """
    Handles subcommands for cards.
    """

    def __init__(self, bot, registry: CardRegistry):
        self.bot = bot
        self.registry = registry
        log.debug("CardCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="cards", aliases=["card"])
        async def dlm_cards(ctx: commands.Context, *, card_name: str = None):
            """
            Usage: -dlm cards <card name>
            Searches cards by name (exact or partial).
            """
            log.info(f"Card search requested by {ctx.author} for: {card_name}")
            if not card_name:
                await ctx.send_help(ctx.command)
                return

            results = self.registry.search_cards(card_name)
            if not results:
                log.debug(f"No cards found for query: {card_name}")
                await ctx.send(f"No cards found for: {card_name}")
            else:
                names = ", ".join(card.name for card in results[:5])
                log.debug(f"Found cards for {card_name}: {names}")
                await ctx.send(f"Found cards: {names}")


class DeckCommands:
    """
    Handles subcommands for decks.
    """
    def __init__(self, bot, registry):
            self.bot = bot
        self.registry = registry
        log.debug("DeckCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="decks")
        async def dlm_decks(ctx: commands.Context, *, deck_name: str = None):
            """
            Usage: -dlm decks <deck name>
            """
            log.info(f"Deck search requested by {ctx.author} for: {deck_name}")
            if not deck_name:
                await ctx.send_help(ctx.command)
                return

            results = await self.registry.search_decks(deck_name)
            if not results:
                await ctx.send(f"No decks found matching: {deck_name}")
                return

            response = "Found decks:\n"
            for deck in results:
                response += f"• {deck.name} by {deck.author}\n"
            await ctx.send(response)


class EventCommands:
    """
    Handles subcommands for events.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry
        log.debug("EventCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="events")
        async def dlm_events(ctx: commands.Context, *, event_name: str = None):
            """
            Usage: -dlm events <event name>
            """
            log.info(f"Event search requested by {ctx.author} for: {event_name}")
            if not event_name:
                await ctx.send_help(ctx.command)
                return

            # TODO: Implement event lookup
            events = await self.registry.search_events(event_name)
            if not events:
                await ctx.send(f"No events found matching: {event_name}")
                return
            response = "Found events:\n"
            for event in events[:5]:
                response += f"• {event.name} ({event.date})\n"
            await ctx.send(response)

class MetaCommands:
    """
    Handles subcommands for meta information.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry
        log.debug("MetaCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="meta")
        async def dlm_meta(ctx: commands.Context, *, format_: str = None):
            """
            Usage: -dlm meta <format>
            """
            log.info(f"Meta information requested by {ctx.author} for format: {format_}")
            if not format_:
                await ctx.send_help(ctx.command)
                return

            # TODO: Implement meta report fetching
            meta_report = await self.registry.get_meta_report(format_)
            if not meta_report:
                await ctx.send(f"No meta report found for format: {format_}")
                return
            response = f"Meta Report for {format_}:\n"
            for deck in meta_report.top_decks[:5]:
                response += f"• {deck.name}: {deck.usage_percent}%\n"
            await ctx.send(response)


class TournamentCommands:
    """
    Handles subcommands for tournaments.
    """

    def __init__(self, bot, registry):
        self.bot = bot
        self.registry = registry
        log.debug("TournamentCommands initialized")

    def register(self, dlm_group: commands.Group):
        @dlm_group.command(name="tournaments", aliases=["tour"])
        async def dlm_tournaments(ctx: commands.Context, *, tournament_name: str = None):
            """
            Usage: -dlm tournaments <tournament name>
            Alias: -dlm tour <tournament name>

            Searches tournaments by name or shortName and displays basic info:
            shortName, full name, and next date (if available).
            """
            log.info(f"Tournament search requested by {ctx.author} for: {tournament_name}")
            if not tournament_name:
                await ctx.send_help(ctx.command)
                return

            # 'search_tournaments' should do the actual lookups (fuzzy match, substring, etc.) in your registry.
            tournaments = await self.registry.search_tournaments(tournament_name)
            if not tournaments:
                await ctx.send(f"No tournaments found matching: {tournament_name}")
                return

            chunk_size = 3
            for start_index in range(0, len(tournaments), chunk_size):
                subset = tournaments[start_index : start_index + chunk_size]

                embed = discord.Embed(
                    title=f"Tournaments matching: {tournament_name}",
                    description=f"Showing {start_index + 1}–{min(len(tournaments), start_index + chunk_size)} "
                                f"of {len(tournaments)} results",
                    color=discord.Color.blurple()
                )

                for t in subset:
                    short_name = t.get("shortName", "N/A")
                    full_name = t.get("name", "Unknown Tournament")
                    next_date_raw = t.get("nextDate")
                    if not next_date_raw:
                        next_date = "No upcoming date"
                    else:
                        try:
                            dt = datetime.fromisoformat(next_date_raw.replace("Z", "+00:00"))
                            next_date = dt.strftime("%d %b %Y, %I:%M %p UTC")
                        except ValueError:
                            next_date = next_date_raw

                    embed.add_field(
                        name=f"{short_name} — {full_name}",
                        value=f"Next Date: {next_date}",
                        inline=False
                    )

                await ctx.send(embed=embed)
