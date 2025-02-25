import discord
from discord.ext import commands
from typing import Dict, Optional, List, Any, Union
from datetime import datetime

from ..core.models import Tournament, Participant, DeckInfo
from ..utils.constants import VerificationStatus, ERROR_MESSAGES


class RegistrationService:
    """
    Service for handling player registration and deck submissions
    """
    def __init__(self, bot, logger, backup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
    async def register_player(self, ctx, tournament: Tournament,
                             main_deck: discord.Attachment = None,
                             extra_deck: discord.Attachment = None,
                             side_deck: discord.Attachment = None) -> bool:
        """Register a player for the tournament"""
        is_interaction = hasattr(ctx, 'response')
        user = ctx.user if is_interaction else ctx.author
        guild = ctx.guild
        if not tournament.registration_open:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["REGISTRATION_CLOSED"], ephemeral=True)
            else:
                await ctx.send(ERROR_MESSAGES["REGISTRATION_CLOSED"])
            return False
        if user.id in tournament.participants:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["ALREADY_REGISTERED"], ephemeral=True)
            else:
                await ctx.send(ERROR_MESSAGES["ALREADY_REGISTERED"])
            return False
        attachments = [a for a in [main_deck, extra_deck, side_deck] if a is not None]
        if tournament.config["deck_check_required"] and not attachments:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["DECK_REQUIRED"], ephemeral=True)
            else:
                await ctx.send(ERROR_MESSAGES["DECK_REQUIRED"])
            return False
        deck_info = None
        if attachments:
            try:
                deck_info = await self._validate_deck_images(attachments)
            except ValueError as e:
                if is_interaction:
                    await ctx.response.send_message(f"Deck validation failed: {str(e)}")
                else:
                    await ctx.send(f"Deck validation failed: {str(e)}")
                return False
            except Exception as e:
                if is_interaction:
                    await ctx.response.send_message("An error occurred while validating your deck. Please try again.")
                else:
                    await ctx.send("An error occurred while validating your deck. Please try again.")
                return False
        participant = Participant(
            user_id=user.id,
            deck_info=deck_info,
            seed=len(tournament.participants) + 1,
            registration_time=datetime.now().isoformat(),
            active=True
        )
        tournament.participants[user.id] = participant
        self.logger.log_tournament_event(guild.id, "registration", {
            "user_id": user.id,
            "deck_info": deck_info.to_dict() if deck_info else None
        })
        self.backup.save_tournament_state(
            guild.id,
            tournament.to_dict()
        )
        embed = discord.Embed(
            title="Registration Successful!",
            description=f"Player: {user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Tournament",
            value=tournament.name,
            inline=True
        )
        embed.add_field(
            name="Format",
            value=tournament.config["tournament_mode"].replace("_", " ").title(),
            inline=True
        )
        if deck_info:
            embed.add_field(
                name="Deck Status",
                value="Submitted - Awaiting Verification",
                inline=False
            )
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        return True
    async def _validate_deck_images(self, attachments: List[discord.Attachment]) -> DeckInfo:
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
        for deck in [d for d in [main_deck, extra_deck, side_deck] if d is not None]:
            if not deck.content_type.startswith('image/'):
                raise ValueError(f"File {deck.filename} is not an image")
        return DeckInfo(
            main_deck_url=main_deck.url,
            extra_deck_url=extra_deck.url if extra_deck else None,
            side_deck_url=side_deck.url if side_deck else None,
            verification_status=VerificationStatus.PENDING
        )
    async def verify_deck(self, ctx, tournament: Tournament,
                        player_id: int, status: str,
                        notes: str = None) -> bool:
        """Verify a player's deck"""
        is_interaction = hasattr(ctx, 'response')
        mod_user = ctx.user if is_interaction else ctx.author
        if player_id not in tournament.participants:
            if is_interaction:
                await ctx.response.send_message("Player not found in tournament.")
            else:
                await ctx.send("Player not found in tournament.")
            return False
        participant = tournament.participants[player_id]
        if not participant.deck_info:
            if is_interaction:
                await ctx.response.send_message("This player has not submitted deck information.")
            else:
                await ctx.send("This player has not submitted deck information.")
            return False
        participant.deck_info.verification_status = status
        participant.deck_info.verification_notes = notes
        participant.deck_info.verified_by = mod_user.id
        participant.deck_info.verified_at = datetime.now().isoformat()
        self.logger.log_tournament_event(ctx.guild.id, "deck_verification", {
            "player_id": player_id,
            "verified_by": mod_user.id,
            "status": status,
            "notes": notes
        })
        self.backup.save_tournament_state(
            ctx.guild.id,
            tournament.to_dict()
        )
        player = await self.bot.fetch_user(player_id)
        embed = discord.Embed(
            title="Deck Verification",
            description=f"Deck for {player.mention} has been verified.",
            color=discord.Color.green() if status == VerificationStatus.APPROVED else discord.Color.red()
        )
        embed.add_field(
            name="Status",
            value=status.title(),
            inline=True
        )
        embed.add_field(
            name="Verified By",
            value=mod_user.mention,
            inline=True
        )
        if notes:
            embed.add_field(
                name="Notes",
                value=notes,
                inline=False
            )
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        try:
            await player.send(embed=embed)
        except:
            pass
        return True
