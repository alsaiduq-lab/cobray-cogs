from redbot.core import commands
import discord
from typing import Optional

from .log import TournamentLogger
from .backup import TournamentBackup
from .tournament import TournamentManager

class DuelLinksTournament(commands.Cog):
    """A cog for managing Yu-Gi-Oh! Duel Links tournaments."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = TournamentLogger()
        self.backup = TournamentBackup()
        self.tournament = TournamentManager(bot, self.logger, self.backup)

    @discord.app_commands.command(name="register")
    async def register_player(
        self,
        interaction: discord.Interaction,
        main_deck: Optional[discord.Attachment] = None,
        extra_deck: Optional[discord.Attachment] = None,
        side_deck: Optional[discord.Attachment] = None
    ):
        """Register for the tournament"""
        await self.tournament.register_player(interaction, main_deck, extra_deck, side_deck)

    @discord.app_commands.command(name="report_result")
    async def report_result(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        wins: int,
        losses: int
    ):
        """Report a match result"""
        await self.tournament.report_result(interaction, opponent, wins, losses)

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready"""
        print("whenever is loaded and ready.")
        await self.tournament.load_states(self.bot.guilds)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called when a member's roles are updated"""
        await self.tournament.handle_member_update(before, after)
