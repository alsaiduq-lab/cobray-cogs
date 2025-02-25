from redbot.core import commands, Config
import discord
from typing import Dict, Optional, List, Union
from datetime import datetime
import asyncio
import os
from .constants import (
    DEFAULT_TOURNAMENT_CONFIG,
    MIN_PARTICIPANTS,
    MatchStatus,
    VerificationStatus,
    TournamentMode,
    ERROR_MESSAGES,
    ROUND_MESSAGES,
    ParticipantInfo,
    MatchInfo,
    DeckInfo
)
from .log import TournamentLogger
from .backup import TournamentBackup
from .tournament import TournamentManager

class DuelLinksTournament(commands.Cog):
    """
    Duel Links Tournament Manager - For organizing Yu-Gi-Oh! Duel Links tournaments
    """
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=105680985214757, force_registration=True)
        
        default_guild = {
            "tournament_role_id": None,
            "mod_role_id": None,
            "tournament_channel_id": None,
            "tournament_category_id": None,
            "announcement_channel_id": None,
            "use_threads": True,
            "tournament_threads": {},  # {user_id: thread_id}
            "tournament_channels": {},  # {user_id: channel_id}
            "active_tournaments": {}   # {tournament_id: tournament_data}
        }
        
        self.config.register_guild(**default_guild)
        
        # Initialize tournament manager
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tournament_logs")
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tournament_backups")
        self.logger = TournamentLogger(log_dir)
        self.backup = TournamentBackup(backup_dir)
        self.tournament_manager = TournamentManager(bot, self.logger, self.backup)
        
        # Load guild settings
        self.bot.loop.create_task(self._load_guild_settings())
    
    async def _load_guild_settings(self):
        await self.bot.wait_until_ready()
        # Load guild settings
        all_guilds = await self.config.all_guilds()
        for guild_id, settings in all_guilds.items():
            self.tournament_manager.guild_settings[guild_id] = settings
        
        # Load tournament states
        await self.tournament_manager.load_states(self.bot.guilds)
    
    @commands.guild_only()
    @commands.group(name="whenever", aliases=["dlt", "tournament"])
    async def whenever(self, ctx):
        """
        Duel Links Tournament commands
        
        Use this command to manage Yu-Gi-Oh! Duel Links tournaments.
        """
        if ctx.invoked_subcommand is None:
            await self._create_or_get_private_channel(ctx)
    
    @whenever.command(name="create")
    @commands.admin_or_permissions(manage_guild=True)
    async def create_tournament(self, ctx, name: str, tournament_mode: str = "single_elimination", best_of: int = 3):
        """
        Create a new tournament
        
        Arguments:
        - name: The name of the tournament
        - tournament_mode: single_elimination, double_elimination, swiss, round_robin
        - best_of: Number of games in a match (3, 5, 7, etc.)
        """
        # Validate tournament mode
        valid_modes = [TournamentMode.SINGLE_ELIMINATION, TournamentMode.DOUBLE_ELIMINATION, 
                     TournamentMode.SWISS, TournamentMode.ROUND_ROBIN]
        
        if tournament_mode not in valid_modes:
            await ctx.send(f"Invalid tournament mode. Valid options are: {', '.join(valid_modes)}")
            return
        
        # Create the tournament
        await self.tournament_manager.create_tournament(
            ctx,
            name=name,
            tournament_mode=tournament_mode,
            best_of=best_of
        )
    
    @whenever.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def start_tournament(self, ctx):
        """Start the tournament with registered players"""
        await self.tournament_manager.start_tournament(ctx)
    
    @whenever.command(name="open")
    @commands.admin_or_permissions(manage_guild=True)
    async def open_registration(self, ctx):
        """Open registration for the tournament"""
        await self.tournament_manager.open_registration(ctx)
    
    @whenever.command(name="close")
    @commands.admin_or_permissions(manage_guild=True)
    async def close_registration(self, ctx):
        """Close registration for the tournament"""
        await self.tournament_manager.close_registration(ctx)
    
    @whenever.command(name="register")
    async def register_player(self, ctx, main_deck: discord.Attachment = None, 
                             extra_deck: discord.Attachment = None,
                             side_deck: discord.Attachment = None):
        """
        Register for the tournament
        
        Arguments:
        - main_deck: Screenshot of your main deck (required if deck check is enabled)
        - extra_deck: Screenshot of your extra deck (optional)
        - side_deck: Screenshot of your side deck (optional)
        """
        # Create private channel or thread first
        channel = await self._create_or_get_private_channel(ctx)
        
        # If we couldn't create a private channel
        if channel is None:
            return
        
        # If we're in a different channel than the command was issued, send acknowledgement
        if channel.id != ctx.channel.id:
            try:
                await ctx.send(f"Registration moved to {channel.mention}", ephemeral=True)
            except Exception:
                await ctx.send(f"Registration moved to {channel.mention}")
            
            # Clone the context for the private channel
            new_ctx = await self.bot.get_context(ctx.message)
            new_ctx.channel = channel
            
            # Now perform the registration in the private channel
            await self.tournament_manager.register_player(new_ctx, main_deck, extra_deck, side_deck)
        else:
            # We're already in the right channel
            await self.tournament_manager.register_player(ctx, main_deck, extra_deck, side_deck)
    
    @whenever.command(name="report")
    async def report_result(self, ctx, opponent: discord.Member, wins: int, losses: int, draws: int = 0):
        """
        Report match results
        
        Arguments:
        - opponent: Your opponent in the match
        - wins: Number of games you won
        - losses: Number of games you lost
        - draws: Number of games that ended in a draw (optional)
        """
        # Create private channel or thread first
        channel = await self._create_or_get_private_channel(ctx)
        
        # If we couldn't create a private channel
        if channel is None:
            return
        
        # If we're in a different channel than the command was issued, send acknowledgement
        if channel.id != ctx.channel.id:
            try:
                await ctx.send(f"Match reporting moved to {channel.mention}", ephemeral=True)
            except Exception:
                await ctx.send(f"Match reporting moved to {channel.mention}")
            
            # Clone the context for the private channel
            new_ctx = await self.bot.get_context(ctx.message)
            new_ctx.channel = channel
            
            # Now perform the reporting in the private channel
            await self.tournament_manager.report_result(new_ctx, opponent, wins, losses, draws)
        else:
            # We're already in the right channel
            await self.tournament_manager.report_result(ctx, opponent, wins, losses, draws)
    
    @whenever.command(name="bracket")
    async def show_bracket(self, ctx):
        """Show the current tournament bracket"""
        # This command doesn't need to be in a private channel, but can be redirected there if user already has one
        
        # Check if the user has a private channel
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        thread_mapping = await self.config.guild(ctx.guild).tournament_threads()
        channel_mapping = await self.config.guild(ctx.guild).tournament_channels()
        
        private_channel = None
        
        # Check for existing thread
        if str(ctx.author.id) in thread_mapping:
            thread_id = thread_mapping[str(ctx.author.id)]
            private_channel = self.bot.get_channel(thread_id)
        
        # Check for existing channel
        if not private_channel and str(ctx.author.id) in channel_mapping:
            channel_id = channel_mapping[str(ctx.author.id)]
            private_channel = self.bot.get_channel(channel_id)
        
        # If the user has a private channel and we're not in it, redirect
        if private_channel and private_channel.id != ctx.channel.id:
            # Let the user know we're redirecting
            try:
                await ctx.send(f"Sending tournament bracket to {private_channel.mention}", ephemeral=True)
            except Exception:
                await ctx.send(f"Sending tournament bracket to {private_channel.mention}")
            
            # Send bracket to the private channel
            new_ctx = await self.bot.get_context(ctx.message)
            new_ctx.channel = private_channel
            await self.tournament_manager.send_bracket_status(new_ctx)
            
            # Also send a public version if this was in a public channel
            if ctx.channel.type == discord.ChannelType.text:
                await self.tournament_manager.send_bracket_status(ctx)
        else:
            # Just show the bracket in the current channel
            await self.tournament_manager.send_bracket_status(ctx)
    
    @whenever.command(name="stats")
    async def show_stats(self, ctx):
        """Show tournament statistics"""
        await self.tournament_manager.get_tournament_stats(ctx)
        
    @whenever.command(name="schedule")
    async def schedule_match(self, ctx, opponent: discord.Member, *, time: str):
        """
        Schedule a match with your opponent
        
        Arguments:
        - opponent: Your opponent in the match
        - time: When the match will take place (e.g. "tomorrow at 3pm", "in 2 hours")
        
        Example: /whenever schedule @opponent tomorrow at 3pm
        """
        # Create private channel or thread first
        channel = await self._create_or_get_private_channel(ctx)
        
        # If we couldn't create a private channel
        if channel is None:
            return
            
        # If we're in a different channel than the command was issued, send acknowledgement
        if channel.id != ctx.channel.id:
            try:
                await ctx.send(f"Match scheduling moved to {channel.mention}", ephemeral=True)
            except Exception:
                await ctx.send(f"Match scheduling moved to {channel.mention}")
                
            # Clone the context for the private channel
            new_ctx = await self.bot.get_context(ctx.message)
            new_ctx.channel = channel
                
            # Now perform the scheduling in the private channel
            await self.tournament_manager.schedule_player_match(new_ctx, opponent, time)
        else:
            # We're already in the right channel
            await self.tournament_manager.schedule_player_match(ctx, opponent, time)
            
    @whenever.command(name="upcoming")
    async def show_upcoming_matches(self, ctx):
        """
        Show upcoming scheduled matches
        
        View all matches scheduled for the current tournament
        """
        await self.tournament_manager.show_upcoming_matches(ctx)
    
    @whenever.command(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    async def configure_tournament(self, ctx, setting: str, value: str):
        """
        Configure tournament settings
        
        Examples:
        - [p]whenever config deck_check_required true
        - [p]whenever config best_of 5
        - [p]whenever config rounds_swiss 4
        """
        if setting not in self.tournament_manager.tournament_config:
            valid_settings = ", ".join(self.tournament_manager.tournament_config.keys())
            await ctx.send(f"Invalid setting. Valid options are: {valid_settings}")
            return
        
        # Handle different setting types
        if value.lower() in ["true", "yes", "on", "enable", "enabled"]:
            self.tournament_manager.tournament_config[setting] = True
        elif value.lower() in ["false", "no", "off", "disable", "disabled"]:
            self.tournament_manager.tournament_config[setting] = False
        else:
            try:
                if "." in value:
                    self.tournament_manager.tournament_config[setting] = float(value)
                else:
                    self.tournament_manager.tournament_config[setting] = int(value)
            except ValueError:
                self.tournament_manager.tournament_config[setting] = value
        
        # Save configuration
        self.tournament_manager.backup.save_tournament_state(ctx.guild.id, {
            "tournament_config": self.tournament_manager.tournament_config
        })
        
        await ctx.send(f"Tournament setting `{setting}` set to `{value}`")
    
    @whenever.command(name="dq")
    @commands.admin_or_permissions(manage_guild=True)
    async def disqualify_player(self, ctx, player: discord.Member, *, reason: str = "Disqualified by moderator"):
        """
        Disqualify a player from the tournament
        
        Arguments:
        - player: The player to disqualify
        - reason: Reason for disqualification
        """
        await self.tournament_manager.disqualify_player(ctx, player, reason)
    
    @whenever.command(name="setrole")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_tournament_role(self, ctx, role: discord.Role):
        """
        Set the tournament participation role
        
        Players need this role to register for tournaments
        """
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["tournament_role_id"] = role.id
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).tournament_role_id.set(role.id)
        
        await ctx.send(f"Tournament role set to {role.mention}")
    
    @whenever.command(name="setmodrole")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_mod_role(self, ctx, role: discord.Role):
        """
        Set the tournament moderator role
        
        Users with this role can manage tournaments even without admin permissions
        """
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["mod_role_id"] = role.id
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).mod_role_id.set(role.id)
        
        await ctx.send(f"Tournament moderator role set to {role.mention}")
    
    @whenever.command(name="setchannel")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_tournament_channel(self, ctx, channel: discord.TextChannel = None):
        """
        Set the tournament channel
        
        This channel will be used for tournament management and threads
        If no channel is provided, the current channel will be used
        """
        if channel is None:
            channel = ctx.channel
        
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["tournament_channel_id"] = channel.id
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).tournament_channel_id.set(channel.id)
        
        await ctx.send(f"Tournament channel set to {channel.mention}")
        
    @whenever.command(name="setannouncements")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_announcement_channel(self, ctx, channel: discord.TextChannel = None):
        """
        Set the tournament announcement channel
        
        This channel will be used for tournament announcements, match pairings, and results
        If no channel is provided, the current channel will be used
        """
        if channel is None:
            channel = ctx.channel
        
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["announcement_channel_id"] = channel.id
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).announcement_channel_id.set(channel.id)
        
        await ctx.send(f"Tournament announcement channel set to {channel.mention}")
    
    @whenever.command(name="setcategory")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_tournament_category(self, ctx, category: discord.CategoryChannel):
        """
        Set the tournament category
        
        Private channels for tournament participants will be created in this category
        """
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["tournament_category_id"] = category.id
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).tournament_category_id.set(category.id)
        
        await ctx.send(f"Tournament category set to {category.mention}")
    
    @whenever.command(name="threadmode")
    @commands.admin_or_permissions(manage_guild=True)
    async def set_thread_mode(self, ctx, use_threads: bool = True):
        """
        Set whether to use threads or channels for private communication
        
        Arguments:
        - use_threads: True to use threads, False to use channels
        """
        # Update guild settings
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        guild_settings["use_threads"] = use_threads
        self.tournament_manager.guild_settings[ctx.guild.id] = guild_settings
        
        # Save to config
        await self.config.guild(ctx.guild).use_threads.set(use_threads)
        
        mode_str = "threads" if use_threads else "channels"
        await ctx.send(f"Tournament communication mode set to use {mode_str}")
    
    @whenever.command(name="cleanup")
    @commands.admin_or_permissions(manage_guild=True)
    async def cleanup_channels(self, ctx, player: discord.Member = None):
        """
        Clean up tournament private channels/threads
        
        If a player is specified, only their channel/thread will be removed.
        If no player is specified, all inactive channels/threads will be removed.
        """
        thread_mapping = await self.config.guild(ctx.guild).tournament_threads()
        channel_mapping = await self.config.guild(ctx.guild).tournament_channels()
        
        if player:
            # Remove specific player's channel/thread
            player_id = str(player.id)
            if player_id in thread_mapping:
                thread_id = thread_mapping[player_id]
                thread = self.bot.get_channel(thread_id)
                if thread:
                    try:
                        await thread.delete()
                        del thread_mapping[player_id]
                        await ctx.send(f"Tournament thread for {player.display_name} has been removed.")
                    except discord.Forbidden:
                        await ctx.send("I don't have permission to delete that thread.")
                    except Exception as e:
                        await ctx.send(f"Error deleting thread: {str(e)}")
            
            if player_id in channel_mapping:
                channel_id = channel_mapping[player_id]
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.delete()
                        del channel_mapping[player_id]
                        await ctx.send(f"Tournament channel for {player.display_name} has been removed.")
                    except discord.Forbidden:
                        await ctx.send("I don't have permission to delete that channel.")
                    except Exception as e:
                        await ctx.send(f"Error deleting channel: {str(e)}")
        
        else:
            # Remove all channels/threads for players not in a tournament
            active_participants = list(self.tournament_manager.participants.keys())
            
            # Clean up threads
            deleted_threads = 0
            for player_id, thread_id in list(thread_mapping.items()):
                if int(player_id) not in active_participants:
                    thread = self.bot.get_channel(thread_id)
                    if thread:
                        try:
                            await thread.delete()
                            del thread_mapping[player_id]
                            deleted_threads += 1
                        except Exception:
                            pass
            
            # Clean up channels
            deleted_channels = 0
            for player_id, channel_id in list(channel_mapping.items()):
                if int(player_id) not in active_participants:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.delete()
                            del channel_mapping[player_id]
                            deleted_channels += 1
                        except Exception:
                            pass
            
            await ctx.send(f"Cleanup complete. Removed {deleted_threads} threads and {deleted_channels} channels.")
        
        # Save updated mappings
        await self.config.guild(ctx.guild).tournament_threads.set(thread_mapping)
        await self.config.guild(ctx.guild).tournament_channels.set(channel_mapping)
    
    async def _create_or_get_private_channel(self, ctx) -> Union[discord.TextChannel, discord.Thread, None]:
        """Create or get a private channel/thread for tournament interaction"""
        guild_settings = self.tournament_manager.guild_settings.get(ctx.guild.id, {})
        tournament_role_id = guild_settings.get("tournament_role_id")
        tournament_role = None
        mod_role_id = guild_settings.get("mod_role_id")
        mod_role = None
        
        if tournament_role_id:
            tournament_role = ctx.guild.get_role(tournament_role_id)
        
        if mod_role_id:
            mod_role = ctx.guild.get_role(mod_role_id)
        
        # Get user's existing channel/thread if it exists
        thread_mapping = await self.config.guild(ctx.guild).tournament_threads()
        channel_mapping = await self.config.guild(ctx.guild).tournament_channels()
        
        # Check if user already has a thread
        if str(ctx.author.id) in thread_mapping:
            thread_id = thread_mapping[str(ctx.author.id)]
            thread = self.bot.get_channel(thread_id)
            if thread:
                return thread
            else:
                # Thread was deleted or inaccessible, remove from mapping
                del thread_mapping[str(ctx.author.id)]
                await self.config.guild(ctx.guild).tournament_threads.set(thread_mapping)
        
        # Check if user already has a channel
        if str(ctx.author.id) in channel_mapping:
            channel_id = channel_mapping[str(ctx.author.id)]
            channel = self.bot.get_channel(channel_id)
            if channel:
                return channel
            else:
                # Channel was deleted or inaccessible, remove from mapping
                del channel_mapping[str(ctx.author.id)]
                await self.config.guild(ctx.guild).tournament_channels.set(channel_mapping)
        
        # Determine if we should use threads or channels
        use_threads = guild_settings.get("use_threads", True)
        
        try:
            if use_threads:
                # Get or create tournament channel for threads
                tournament_channel_id = guild_settings.get("tournament_channel_id")
                tournament_channel = None
                
                if tournament_channel_id:
                    tournament_channel = self.bot.get_channel(tournament_channel_id)
                
                # If no tournament channel is set, use the current channel
                if not tournament_channel:
                    tournament_channel = ctx.channel
                
                # Check if we have permission to create threads
                if not tournament_channel.permissions_for(ctx.guild.me).create_public_threads or \
                   not tournament_channel.permissions_for(ctx.guild.me).create_private_threads:
                    try:
                        await ctx.send("I don't have permission to create threads in this channel. "
                                     "Please ask an admin to grant me the 'Create Public Threads' and "
                                     "'Create Private Threads' permissions.", ephemeral=True)
                    except:
                        await ctx.send("I don't have permission to create threads in this channel.")
                    return None
                
                # Create a thread for the user
                try:
                    thread_name = f"{ctx.author.display_name}'s Tournament"
                    thread = await tournament_channel.create_thread(
                        name=thread_name,
                        type=discord.ChannelType.private_thread,
                        auto_archive_duration=1440  # 1 day
                    )
                    
                    # Make the thread accessible to the user and staff
                    await thread.add_user(ctx.author)
                    
                    # Add tournament staff if applicable
                    if tournament_role:
                        for member in ctx.guild.members:
                            if tournament_role in member.roles and member.id != ctx.author.id:
                                try:
                                    await thread.add_user(member)
                                except:
                                    pass
                    
                    if mod_role:
                        for member in ctx.guild.members:
                            if mod_role in member.roles and member.id != ctx.author.id:
                                try:
                                    await thread.add_user(member)
                                except:
                                    pass
                    
                    # Store the thread ID
                    thread_mapping[str(ctx.author.id)] = thread.id
                    await self.config.guild(ctx.guild).tournament_threads.set(thread_mapping)
                    
                    # Send welcome message
                    await thread.send(f"Welcome to your private tournament thread, {ctx.author.mention}! "
                                    f"You can use this thread to interact with the tournament.")
                    
                    return thread
                except discord.Forbidden:
                    try:
                        await ctx.send("I don't have permission to create or manage threads.", ephemeral=True)
                    except:
                        await ctx.send("I don't have permission to create or manage threads.")
                    return None
                except Exception as e:
                    await ctx.send(f"Error creating thread: {str(e)}")
                    return None
            else:
                # Use dedicated channels instead of threads
                # Check if we have permission to create channels
                if not ctx.guild.me.guild_permissions.manage_channels:
                    try:
                        await ctx.send("I don't have permission to create channels. "
                                     "Please ask an admin to grant me the 'Manage Channels' permission.", ephemeral=True)
                    except:
                        await ctx.send("I don't have permission to create channels.")
                    return None
                
                category_id = guild_settings.get("tournament_category_id")
                category = None
                
                if category_id:
                    category = ctx.guild.get_channel(category_id)
                
                # Create private channel for the user
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    ctx.author: discord.PermissionOverwrite(read_messages=True),
                    ctx.guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True)
                }
                
                # Give access to tournament role if set
                if tournament_role:
                    overwrites[tournament_role] = discord.PermissionOverwrite(read_messages=True)
                
                # Give access to moderator role if set
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True)
                
                try:
                    channel_name = f"{ctx.author.name.lower()}-tournament"
                    channel = await ctx.guild.create_text_channel(
                        name=channel_name, 
                        category=category,
                        overwrites=overwrites
                    )
                    
                    # Store the channel ID
                    channel_mapping[str(ctx.author.id)] = channel.id
                    await self.config.guild(ctx.guild).tournament_channels.set(channel_mapping)
                    
                    # Send welcome message
                    await channel.send(f"Welcome to your private tournament channel, {ctx.author.mention}! "
                                    f"You can use this channel to interact with the tournament.")
                    
                    return channel
                except discord.Forbidden:
                    try:
                        await ctx.send("I don't have permission to create channels.", ephemeral=True)
                    except:
                        await ctx.send("I don't have permission to create channels.")
                    return None
                except Exception as e:
                    await ctx.send(f"Error creating channel: {str(e)}")
                    return None
                
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            return None
    
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Handle member role updates"""
        await self.tournament_manager.handle_member_update(before, after)
