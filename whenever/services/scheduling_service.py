import discord
from discord.ext import commands
from typing import Dict, Optional, List, Any, Union
from datetime import datetime, timedelta
import asyncio
import dateparser

from ..core.models import Tournament, Match
from ..utils.constants import MatchStatus, ERROR_MESSAGES, ROUND_MESSAGES


class SchedulingService:
    """
    Service for handling match scheduling and reminders
    """
    def __init__(self, bot, logger, backup):
        self.bot = bot
        self.logger = logger
        self.backup = backup
        self.reminder_tasks = {}  # Dict of match_id: asyncio Task
    
    async def schedule_match(self, ctx, tournament: Tournament, 
                           opponent: discord.Member, time_str: str) -> bool:
        """Schedule a match with an opponent at a specific time"""
        is_interaction = hasattr(ctx, 'response')
        user = ctx.user if is_interaction else ctx.author
        
        if not tournament.is_started:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            else:
                await ctx.send(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            return False
        
        # Find match between players
        match_id = None
        for mid, match in tournament.matches.items():
            if match.status != MatchStatus.PENDING:
                continue
            if (match.player1 == user.id and match.player2 == opponent.id) or \
               (match.player2 == user.id and match.player1 == opponent.id):
                match_id = mid
                break
        
        if match_id is None:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["NO_MATCH_FOUND"])
            else:
                await ctx.send(ERROR_MESSAGES["NO_MATCH_FOUND"])
            return False
        
        # Parse the time string
        parsed_time = dateparser.parse(time_str, settings={'PREFER_DATES_FROM': 'future'})
        if not parsed_time:
            if is_interaction:
                await ctx.response.send_message("I couldn't understand that time format. Please use a standard format like 'tomorrow at 3pm' or 'in 2 hours'.")
            else:
                await ctx.send("I couldn't understand that time format. Please use a standard format like 'tomorrow at 3pm' or 'in 2 hours'.")
            return False
        
        # Check if the time is in the future
        now = datetime.now()
        if parsed_time < now:
            if is_interaction:
                await ctx.response.send_message("The scheduled time must be in the future.")
            else:
                await ctx.send("The scheduled time must be in the future.")
            return False
        
        # Update match with scheduled time
        match = tournament.matches[match_id]
        match.scheduled_time = parsed_time.isoformat()
        
        # Store in scheduled matches dict for easy lookup
        tournament.meta["scheduled_matches"][str(match_id)] = parsed_time.isoformat()
        
        # Save state
        self.backup.save_tournament_state(tournament.meta["guild_id"], tournament.to_dict())
        
        # Calculate reminder time (default 15 minutes before match)
        reminder_minutes = tournament.config.get("reminder_minutes", 15)
        reminder_time = parsed_time - timedelta(minutes=reminder_minutes)
        
        # Schedule reminder task if needed
        if reminder_time > now and tournament.config.get("send_reminders", True):
            # Calculate seconds until reminder
            seconds_until_reminder = (reminder_time - now).total_seconds()
            
            # Cancel any existing reminder task for this match
            if match_id in self.reminder_tasks and not self.reminder_tasks[match_id].done():
                self.reminder_tasks[match_id].cancel()
            
            # Schedule new reminder task
            task = asyncio.create_task(
                self._send_match_reminder(tournament, match_id, seconds_until_reminder)
            )
            self.reminder_tasks[match_id] = task
        
        # Create confirmation embed
        embed = discord.Embed(
            title="Match Scheduled",
            description=f"Match between <@{match.player1}> and <@{match.player2}> has been scheduled.",
            color=discord.Color.green()
        )
        
        # Format time for display
        timestamp = int(parsed_time.timestamp())
        embed.add_field(
            name="Time",
            value=f"<t:{timestamp}:F> (<t:{timestamp}:R>)",
            inline=False
        )
        
        embed.add_field(
            name="Match Details",
            value=f"Round {match.round_num} | Match {match_id} | Best of {tournament.config['best_of']}",
            inline=False
        )
        
        # Reminder info
        reminder_minutes = tournament.config.get("reminder_minutes", 15)
        embed.add_field(
            name="Reminder",
            value=f"A reminder will be sent {reminder_minutes} minutes before the match.",
            inline=False
        )
        
        # Send confirmation
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
        
        # Log the scheduled match
        self.logger.log_tournament_event(tournament.meta["guild_id"], "match_scheduled", {
            "match_id": match_id,
            "scheduled_by": user.id,
            "player1": match.player1,
            "player2": match.player2,
            "scheduled_time": parsed_time.isoformat()
        })
        
        # Try to DM the opponent
        try:
            await opponent.send(embed=embed)
        except:
            pass
            
        return True
    
    async def _send_match_reminder(self, tournament: Tournament, match_id: int, delay_seconds: float):
        """Send a reminder for an upcoming match"""
        # Wait until it's time to send the reminder
        await asyncio.sleep(delay_seconds)
        
        # Check if match still exists and is pending
        if match_id not in tournament.matches:
            return
            
        match = tournament.matches[match_id]
        if match.status != MatchStatus.PENDING:
            return
            
        # Get player info
        try:
            player1 = await self.bot.fetch_user(match.player1)
            player2 = await self.bot.fetch_user(match.player2)
            
            if not player1 or not player2:
                return
        except:
            return
            
        # Create reminder embed
        embed = discord.Embed(
            title="⏰ Match Reminder",
            description=f"Reminder for match between {player1.mention} and {player2.mention}",
            color=discord.Color.gold()
        )
        
        # Get scheduled time
        try:
            scheduled_time = datetime.fromisoformat(match.scheduled_time)
            embed.add_field(
                name="Scheduled Time",
                value=f"<t:{int(scheduled_time.timestamp())}:F>",
                inline=False
            )
        except:
            pass
            
        # Add match details
        embed.add_field(
            name="Match Details",
            value=f"Round {match.round_num} | Match {match_id}",
            inline=True
        )
        
        embed.add_field(
            name="Format",
            value=f"Best of {tournament.config['best_of']}",
            inline=True
        )
        
        # Try to get announcement channel
        try:
            guild = self.bot.get_guild(tournament.meta["guild_id"])
            if guild:
                announcement_channel_id = guild.settings.get("announcement_channel_id")
                if announcement_channel_id:
                    channel = self.bot.get_channel(announcement_channel_id)
                    if channel:
                        await channel.send(embed=embed)
        except:
            pass
            
        # Also send DMs to players if possible
        try:
            await player1.send(embed=embed)
        except:
            pass
            
        try:
            await player2.send(embed=embed)
        except:
            pass
    
    async def show_upcoming_matches(self, ctx, tournament: Tournament):
        """Show all upcoming scheduled matches"""
        is_interaction = hasattr(ctx, 'response')
        
        if not tournament.is_started:
            if is_interaction:
                await ctx.response.send_message(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            else:
                await ctx.send(ERROR_MESSAGES["TOURNAMENT_NOT_STARTED"])
            return False
            
        # Get all pending matches with scheduled times
        scheduled_matches = []
        now = datetime.now()
        
        for match_id, match in tournament.matches.items():
            if match.status != MatchStatus.PENDING or not match.scheduled_time:
                continue
                
            try:
                scheduled_time = datetime.fromisoformat(match.scheduled_time)
                if scheduled_time > now:
                    scheduled_matches.append((match_id, match, scheduled_time))
            except:
                continue
                
        # Sort matches by scheduled time
        scheduled_matches.sort(key=lambda x: x[2])
        
        if not scheduled_matches:
            if is_interaction:
                await ctx.response.send_message("No upcoming matches are scheduled.")
            else:
                await ctx.send("No upcoming matches are scheduled.")
            return False
            
        # Create embed
        embed = discord.Embed(
            title="Upcoming Scheduled Matches",
            description=f"Tournament: {tournament.name}",
            color=discord.Color.blue()
        )
        
        # Add each match to the embed
        for match_id, match, scheduled_time in scheduled_matches:
            player1 = await self.bot.fetch_user(match.player1)
            player2 = await self.bot.fetch_user(match.player2)
            
            timestamp = int(scheduled_time.timestamp())
            field_name = f"Match {match_id} - <t:{timestamp}:R>"
            field_value = f"{player1.mention} vs {player2.mention}\n" \
                         f"Time: <t:{timestamp}:F>\n" \
                         f"Round {match.round_num} | Best of {tournament.config['best_of']}"
                         
            embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
            
        # Add footer
        reminder_minutes = tournament.config.get("reminder_minutes", 15)
        embed.set_footer(text=f"Reminders are sent {reminder_minutes} minutes before each match.")
        
        # Send the embed
        if is_interaction:
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.send(embed=embed)
            
        return True
            
    def cancel_all_reminders(self):
        """Cancel all scheduled reminder tasks"""
        for match_id, task in self.reminder_tasks.items():
            if not task.done() and not task.cancelled():
                task.cancel()
                
        self.reminder_tasks = {}
