from redbot.core import commands
import discord
import logging
from typing import Optional

from .log import TournamentLogger
from .backup import TournamentBackup
from .tournament import TournamentManager

class DuelLinksTournament(commands.Cog):
    """A cog for managing Yu-Gi-Oh! Duel Links tournaments."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = TournamentLogger()
        self.log = logging.getLogger("red.tournament.DuelLinksTournament")
        self.backup = TournamentBackup()
        self.tournament = TournamentManager(bot, self.logger, self.backup)
        self.log.info("DuelLinksTournament cog initialized")

    @commands.hybrid_command(name="register")
    async def register_player(
        self,
        ctx: commands.Context,
        main_deck: discord.Attachment,
        extra_deck: Optional[discord.Attachment] = None,
        side_deck: Optional[discord.Attachment] = None
    ):
        """Register for the tournament
        Parameters
        ----------
        main_deck: Attachment
            Your main deck image
        extra_deck: Optional[Attachment]
            Your extra deck image
        side_deck: Optional[Attachment]
            Your side deck image
        """
        self.log.info(f"Registration attempt by {ctx.author} (ID: {ctx.author.id})")
        self.log.debug(f"Main deck: {main_deck}, Extra deck: {extra_deck}, Side deck: {side_deck}")
        await self.tournament.register_player(ctx, main_deck, extra_deck, side_deck)

    @commands.hybrid_command(name="report_result")
    async def report_result(
        self,
        ctx: commands.Context,
        opponent: discord.Member,
        wins: int,
        losses: int
    ):
        """Report a match result
        Parameters
        ----------
        opponent: Member
            Your opponent in the match
        wins: int
            Number of games you won
        losses: int
            Number of games you lost
        """
        self.log.info(f"Result report attempt by {ctx.author} vs {opponent} ({wins}-{losses})")
        await self.tournament.report_result(ctx, opponent, wins, losses)

    @commands.Cog.listener()
    async def on_ready(self):
        self.log.info("DuelLinksTournament cog is loaded and ready")
        await self.tournament.load_states(self.bot.guilds)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        self.log.debug(f"Member update: {before} -> {after}")
        await self.tournament.handle_member_update(before, after)
