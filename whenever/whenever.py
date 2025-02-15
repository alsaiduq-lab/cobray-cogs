from redbot.core import commands
import discord
from typing import Dict, Optional, List
from datetime import datetime
from .constants import (
    DEFAULT_TOURNAMENT_CONFIG,
    MIN_PARTICIPANTS,
    MatchStatus,
    VerificationStatus,
    ERROR_MESSAGES,
    ROUND_MESSAGES,
    ParticipantInfo,
    MatchInfo,
    DeckInfo
)
from .log import TournamentLogger
from .backup import TournamentBackup

class TournamentManager:
    def __init__(self, bot: commands.Bot, logger: TournamentLogger, backup: TournamentBackup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
        self.participants: Dict[int, ParticipantInfo] = {}
        self.matches: Dict[int, MatchInfo] = {}
        self.current_round = 1
        self.max_rounds = None
        self.registration_open = False
        self.tournament_started = False
        self.tournament_config = DEFAULT_TOURNAMENT_CONFIG.copy()
        self.guild_settings = {}

    async def load_states(self, guilds: List[discord.Guild]):
        """Load tournament states for all guilds"""
        for guild in guilds:
            state = self.backup.load_tournament_state(guild.id)
            if state:
                self.participants = state.get("participants", {})
                self.matches = state.get("matches", {})
                self.tournament_config = state.get("tournament_config", DEFAULT_TOURNAMENT_CONFIG.copy())
                self.current_round = state.get("current_round", 1)
                self.tournament_started = state.get("tournament_started", False)
                self.logger.log_tournament_event(guild.id, "state_restored", {"restored_from": "backup"})

    async def get_tournament_role(self, guild_id: int) -> Optional[discord.Role]:
        """Get the tournament role for a guild"""
        if guild_id not in self.guild_settings:
            return None
        role_id = self.guild_settings[guild_id].get("tournament_role_id")
        if not role_id:
            return None
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        return guild.get_role(role_id)

    async def register_player(
        self,
        ctx: commands.Context,
        main_deck: discord.Attachment,
        extra_deck: Optional[discord.Attachment] = None,
        side_deck: Optional[discord.Attachment] = None
    ):
        """Register a player for the tournament"""
        tournament_role = await self.get_tournament_role(ctx.guild.id)
        if tournament_role and tournament_role not in ctx.author.roles:
            await ctx.send(
                f"You need the {tournament_role.mention} role to participate in tournaments.",
                ephemeral=True
            )
            return

        if not self.registration_open:
            await ctx.send(ERROR_MESSAGES["REGISTRATION_CLOSED"], ephemeral=True)
            return

        if ctx.author.id in self.participants:
            await ctx.send(ERROR_MESSAGES["ALREADY_REGISTERED"], ephemeral=True)
            return

        attachments = [a for a in [main_deck, extra_deck, side_deck] if a is not None]
        if self.tournament_config["deck_check_required"] and not attachments:
            await ctx.send(ERROR_MESSAGES["DECK_REQUIRED"], ephemeral=True)
            return

        deck_info = None
        if attachments:
            try:
                deck_info = await self.validate_deck_images(ctx, attachments)
            except ValueError as e:
                await ctx.send(f"Deck validation failed: {str(e)}")
                return
            except Exception as e:
                await ctx.send("An error occurred while validating your deck. Please try again.")
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

        self.backup.save_tournament_state(ctx.guild.id, {
            "participants": self.participants,
            "tournament_config": self.tournament_config,
            "registration_open": self.registration_open
        })

        embed = discord.Embed(
            title="Registration Successful!",
            description=f"Player: {ctx.author.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    async def validate_deck_images(self, ctx: commands.Context, attachments: list[discord.Attachment]) -> DeckInfo:
        """Validate submitted deck images"""
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
