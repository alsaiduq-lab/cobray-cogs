import discord
from discord.ext import commands
from typing import Dict, Optional, List
import random
import math
from datetime import datetime

from .constants import (
    DEFAULT_TOURNAMENT_CONFIG,
    MIN_PARTICIPANTS,
    VALID_DIMENSIONS,
    MatchStatus,
    VerificationStatus,
    ERROR_MESSAGES,
    ROUND_MESSAGES,
    ParticipantInfo,
    MatchInfo,
    DeckInfo
)

class DuelLinksTournament(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.participants: Dict[int, ParticipantInfo] = {}
        self.matches: Dict[int, MatchInfo] = {}
        self.current_round = 1
        self.max_rounds = None
        self.registration_open = False
        self.tournament_started = False
        self.tournament_config = DEFAULT_TOURNAMENT_CONFIG.copy()
        self.guild_settings = {}

    async def check_tournament_prerequisites(self, ctx: discord.ApplicationContext) -> tuple[bool, str]:
        """Check if all prerequisites are met to start a tournament"""
        tournament_role = await self.get_tournament_role(ctx.guild.id)
        if not tournament_role:
            return False, ERROR_MESSAGES["NO_TOURNAMENT_ROLE"]
        has_mod = False
        for member in ctx.guild.members:
            if member.guild_permissions.manage_guild and tournament_role in member.roles:
                has_mod = True
                break
        if not has_mod:
            return False, ERROR_MESSAGES["NO_MODERATOR"]
        participant_count = len(self.participants)
        if participant_count < MIN_PARTICIPANTS:
            return False, ERROR_MESSAGES["INSUFFICIENT_PARTICIPANTS"](participant_count)
        return True, "Prerequisites met"

    @commands.slash_command(name="register")
    async def register_player(
        self,
        ctx: discord.ApplicationContext,
        attachments: Optional[list[discord.Attachment]] = None
    ):
        """Register for the tournament with deck screenshots"""
        tournament_role = await self.get_tournament_role(ctx.guild.id)
        if tournament_role and tournament_role not in ctx.author.roles:
            await ctx.respond(
                f"You need the {tournament_role.mention} role to participate in tournaments.",
                ephemeral=True
            )
            return

        if not self.registration_open:
            await ctx.respond(ERROR_MESSAGES["REGISTRATION_CLOSED"], ephemeral=True)
            return
        if ctx.author.id in self.participants:
            await ctx.respond(ERROR_MESSAGES["ALREADY_REGISTERED"], ephemeral=True)
            return
        if self.tournament_config["deck_check_required"] and not attachments:
            await ctx.respond(ERROR_MESSAGES["DECK_REQUIRED"], ephemeral=True)
            return
        deck_info = None
        if attachments:
            try:
                deck_info = await self.validate_deck_images(ctx, attachments)
            except ValueError as e:
                await ctx.respond(f"Deck validation failed: {str(e)}")
                return
            except Exception as e:
                await ctx.respond("An error occurred while validating your deck. Please try again.")
                print(f"Deck validation error: {str(e)}")
                return

        participant_info: ParticipantInfo = {
            "deck_info": deck_info,
            "wins": 0,
            "losses": 0,
            "seed": len(self.participants) + 1,
            "registration_time": datetime.now().isoformat(),
            "dq_info": None
        }
        self.participants[ctx.author.id] = participant_info
        self.logger.log_tournament_event(ctx.guild.id, "registration", {
            "user_id": ctx.author.id,
            "deck_info": deck_info
        })
        await self.backup.save_tournament_state(ctx.guild.id, {
            "participants": self.participants,
            "tournament_config": self.tournament_config,
            "registration_open": self.registration_open
        })
        embed = discord.Embed(
            title="Registration Successful!",
            description=f"Player: {ctx.author.mention}",
            color=discord.Color.green()
        )
        await ctx.respond(embed=embed)

   async def validate_deck_images(self, ctx: discord.ApplicationContext, attachments: list[discord.Attachment]) -> DeckInfo:
    """Validate multiple deck image submissions"""
    if not attachments:
        raise ValueError("No deck images provided")

    if len(attachments) > 3:
        raise ValueError("Maximum of 3 deck images allowed (Main Deck, Extra Deck, Side Deck)")

    if len(attachments) < 1:
        raise ValueError("At least one deck image (Main Deck) is required")

    main_deck = attachments[0]
    extra_deck = attachments[1] if len(attachments) > 1 else None
    side_deck = attachments[2] if len(attachments) > 2 else None

    return {
        "main_deck_url": main_deck.url,
        "extra_deck_url": extra_deck.url if extra_deck else None,
        "side_deck_url": side_deck.url if side_deck else None,
        "verification_status": VerificationStatus.PENDING,
        "verification_notes": None,
        "verified_by": None,
        "verified_at": None
    }

    @commands.slash_command(name="report_result")
    async def report_result(
        self,
        ctx: discord.ApplicationContext,
        opponent: discord.Member,
        wins: int,
        losses: int
    ):
        """Report match result"""
        if not self.tournament_started:
            await ctx.respond(ERROR_MESSAGES["TOURNAMENT_IN_PROGRESS"])
            return
        match_id = None
        for mid, match in self.matches.items():
            if match["status"] != MatchStatus.PENDING:
                continue
            if (match["player1"] == ctx.author.id and match["player2"] == opponent.id) or \
               (match["player2"] == ctx.author.id and match["player1"] == opponent.id):
                match_id = mid
                break
        if match_id is None:
            await ctx.respond(ERROR_MESSAGES["NO_MATCH_FOUND"])
            return
        best_of = self.tournament_config["best_of"]
        max_wins = (best_of // 2) + 1
        if wins > max_wins or losses > max_wins:
            await ctx.respond(ERROR_MESSAGES["INVALID_SCORE"](best_of))
            return
        match = self.matches[match_id]
        match["score"] = f"{wins}-{losses}"
        match["status"] = MatchStatus.COMPLETED
        winner_id = ctx.author.id if wins > losses else opponent.id
        loser_id = opponent.id if wins > losses else ctx.author.id
        match["winner"] = winner_id
        match["loser"] = loser_id
        self.participants[winner_id]["wins"] += 1
        self.participants[loser_id]["losses"] += 1
        # Log and backup
        self.logger.log_match_result(ctx.guild.id, match_id, winner_id, loser_id, match["score"])
        await self.backup.save_tournament_state(ctx.guild.id, {
            "participants": self.participants,
            "matches": self.matches,
            "current_round": self.current_round,
            "tournament_started": self.tournament_started
        })
        embed = discord.Embed(
            title="Match Result Reported",
            description=f"Match {match_id}: {ctx.author.mention} vs {opponent.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Score", value=match["score"])
        embed.add_field(name="Winner", value=f"<@{winner_id}>")
        await ctx.respond(embed=embed)
        await self.check_round_completion(ctx)

    async def check_round_completion(self, ctx: discord.ApplicationContext):
        """Check if current round is complete and create next round matches"""
        current_matches = [m for m in self.matches.values() if m["round"] == self.current_round]
        if not all(m["status"] == MatchStatus.COMPLETED for m in current_matches):
            return
        winners = [m["winner"] for m in current_matches]
        if len(winners) >= 2:
            self.current_round += 1
            match_id = max(self.matches.keys()) + 1
            for i in range(0, len(winners), 2):
                if i + 1 < len(winners):
                    new_match: MatchInfo = {
                        "player1": winners[i],
                        "player2": winners[i + 1],
                        "score": None,
                        "round": self.current_round,
                        "winner": None,
                        "loser": None,
                        "status": MatchStatus.PENDING
                    }
                    self.matches[match_id] = new_match
                    match_id += 1
            await ctx.send(ROUND_MESSAGES["COMPLETE"](self.current_round - 1))
            await self.send_bracket_status(ctx)
        else:
            winner = winners[0]
            winner_user = await self.bot.fetch_user(winner)
            embed = discord.Embed(
                title=ROUND_MESSAGES["TOURNAMENT_COMPLETE"],
                description=f"Congratulations to {winner_user.mention}!",
                color=discord.Color.gold()
            )
            stats = self.participants[winner]
            embed.add_field(
                name="Champion Stats",
                value=f"Wins: {stats['wins']}\nLosses: {stats['losses']}"
            )
            await ctx.send(embed=embed)
            self.tournament_started = False
            self.current_round = 1

    @commands.Cog.listener()
    async def on_ready(self):
        print("whenever is loaded and ready.")
        for guild in self.bot.guilds:
            state = await self.backup.load_tournament_state(guild.id)
            if state:
                self.participants = state.get("participants", {})
                self.matches = state.get("matches", {})
                self.tournament_config = state.get("tournament_config", DEFAULT_TOURNAMENT_CONFIG.copy())
                self.current_round = state.get("current_round", 1)
                self.tournament_started = state.get("tournament_started", False)
                self.logger.log_tournament_event(guild.id, "state_restored", {"restored_from": "backup"})

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Handle tournament role changes"""
        tournament_role = await self.get_tournament_role(after.guild.id)
        if not tournament_role:
            return
        if tournament_role in before.roles and tournament_role not in after.roles:
            if after.id in self.participants and self.tournament_started:
                del self.participants[after.id]
                mod_channel = after.guild.get_channel(self.guild_settings[after.guild.id].get("mod_channel_id"))
                self.logger.log_tournament_event(after.guild.id, "role_removed", {
                    "user_id": after.id,
                    "reason": "tournament_role_removed"
                })
                if mod_channel:
                    embed = discord.Embed(
                        title="Tournament Participant Removed",
                        description=f"{after.mention} was removed from the tournament due to role removal.",
                        color=discord.Color.red()
                    )
                    await mod_channel.send(embed=embed)
                await self.backup.save_tournament_state(after.guild.id, {
                    "participants": self.participants,
                    "matches": self.matches,
                    "current_round": self.current_round
                })
