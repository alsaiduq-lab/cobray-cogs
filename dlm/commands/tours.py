from discord import app_commands, Interaction
from discord.ext import commands
import discord
import logging
from typing import List, Optional
from datetime import datetime
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from ..core.api import DLMApi, DLMAPIError
from ..core.registry import CardRegistry

log = logging.getLogger("red.dlm.commands.tournaments")

class TournamentCommands:
   """Handler for tournament-related commands."""

   def __init__(self, bot: commands.Bot, api: DLMApi, registry: CardRegistry):
       self.bot = bot
       self.api = api
       self.registry = registry

   def get_commands(self) -> List[app_commands.Command]:
       """Return all tournament-related slash commands."""
       return [
           self._tournament_search_command(),
           self.tournament_recent_command() 
       ]

   def _tournament_search_command(self) -> app_commands.Command:
       """Create the tournament search slash command."""
       @app_commands.command(
           name="tournament",
           description="Search for tournaments"
       )
       @app_commands.describe(
           name="Name of the tournament to search for"
       )
       async def tournament(interaction: Interaction, name: str):
           await interaction.response.defer()

           try:
               tournaments = await self.registry.search_tournaments(name)
               if not tournaments:
                   await interaction.followup.send(
                       f"No tournaments found matching: {name}",
                       ephemeral=True
                   )
                   return

               embeds = self._create_tournament_embeds(tournaments, name)
               for embed in embeds[:3]:
                   await interaction.followup.send(embed=embed)

           except Exception as e:
               log.error(f"Error in tournament search: {e}", exc_info=True)
               await interaction.followup.send(
                   "Something went wrong... :pensive:",
                   ephemeral=True
               )

       return tournament

   def tournament_recent_command(self) -> app_commands.Command:
       """Create the recent tournaments slash command."""
       @app_commands.command(
           name="recent_tourny",
           description="Get recent tournaments"
       )
       @app_commands.describe(
           limit="Number of tournaments to show (max 10)"
       )
       async def recent(interaction: Interaction, limit: int = 5):
           await interaction.response.defer()

           try:
               if limit > 10:
                   limit = 10
                   await interaction.followup.send("Limiting results to 10 tournaments maximum.")

               tournaments = await self.api.get_recent_tournaments(limit)
               if not tournaments:
                   await interaction.followup.send("No tournament data found.")
                   return

               embeds = []
               for tourney in tournaments[:limit]:
                   embed = discord.Embed(
                       title=f"{tourney.get('shortName', '')} - {tourney.get('name', 'Unknown Tournament')}".strip(),
                       color=discord.Color.blue()
                   )

                   # Add placements
                   if placements := tourney.get('placements'):
                       placement_text = "\n".join(
                           f"{p['place']}: {p.get('tpcPoints', 0)} TPC Points" 
                           for p in placements
                       )
                       if placement_text:
                           embed.add_field(
                               name="Placements",
                               value=placement_text,
                               inline=False
                           )

                   # Add next date if available
                   if next_date := tourney.get('nextDate'):
                       try:
                           dt = datetime.fromisoformat(next_date.replace("Z", "+00:00"))
                           timestamp = int(dt.timestamp())
                           embed.add_field(
                               name="Next Tournament",
                               value=f"<t:{timestamp}:F>",
                               inline=False
                           )
                       except ValueError:
                           pass

                   # Add player cap if it exists
                   if player_cap := tourney.get('playerCap'):
                       embed.add_field(
                           name="Player Cap",
                           value=str(player_cap),
                           inline=True
                       )

                   # Add stream if available
                   if stream := tourney.get('stream'):
                       embed.add_field(
                           name="Stream",
                           value=stream,
                           inline=True
                       )

                   embeds.append(embed)

               for embed in embeds:
                   await interaction.followup.send(embed=embed)

           except Exception as e:
               log.error(f"Error fetching recent tournaments: {e}", exc_info=True)
               await interaction.followup.send(
                   "Something went wrong... :pensive:",
                   ephemeral=True
               )

       return recent

   @commands.group(name="tournament")
   async def tournament_group(self, ctx: commands.Context):
       """Tournament related commands."""
       if ctx.invoked_subcommand is None:
           await ctx.send_help(ctx.command)

   @tournament_group.command(name="search", aliases=["find"])
   @commands.cooldown(1, 30, commands.BucketType.user)
   async def text_tournament_search(self, ctx: commands.Context, *, name: str = None):
       """Search for tournaments by name."""
       log.info(f"Tournament search requested by {ctx.author} for: {name}")
       async with ctx.typing():
           try:
               tournaments = await self.registry.search_tournaments(name)
               if not tournaments:
                   return await ctx.send(f"No tournaments found matching: {name}")

               embeds = self._create_tournament_embeds(tournaments, name)
               if len(embeds) == 1:
                   await ctx.send(embed=embeds[0])
               else:
                   await menu(ctx, embeds, DEFAULT_CONTROLS)

           except Exception as e:
               log.error(f"Error in tournament search: {e}", exc_info=True)
               await ctx.send("Something went wrong... :pensive:")

   @tournament_group.command(name="recent")
   @commands.cooldown(1, 60, commands.BucketType.user)
   async def text_recent_tournaments(self, ctx: commands.Context, limit: int = 5):
       """Show recent tournaments."""
       try:
           if limit > 10:
               limit = 10
               await ctx.send("Limiting results to 10 tournaments maximum.")

           async with ctx.typing():
               tournaments = await self.api.get_recent_tournaments(limit)
               if not tournaments:
                   return await ctx.send("No tournament data found.")

               embeds = []
               for tourney in tournaments:
                   embed = discord.Embed(
                       title=f"{tourney.get('shortName', '')} - {tourney.get('name', 'Unknown Tournament')}".strip(),
                       color=discord.Color.blue()
                   )

                   # Add placements
                   if placements := tourney.get('placements'):
                       placement_text = "\n".join(
                           f"{p['place']}: {p.get('tpcPoints', 0)} TPC Points" 
                           for p in placements
                       )
                       if placement_text:
                           embed.add_field(
                               name="Placements",
                               value=placement_text,
                               inline=False
                           )

                   # Add date only if it exists
                   if date_str := tourney.get("date"):
                       try:
                           dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                           timestamp = int(dt.timestamp())
                           embed.add_field(
                               name="Date",
                               value=f"<t:{timestamp}:F>",
                               inline=False
                           )
                       except ValueError:
                           pass

                   # Add player cap if it exists
                   if player_cap := tourney.get('playerCap'):
                       embed.add_field(
                           name="Player Cap",
                           value=str(player_cap),
                           inline=True
                       )

                   # Add stream if available
                   if stream := tourney.get('stream'):
                       embed.add_field(
                           name="Stream",
                           value=stream,
                           inline=True
                       )

                   embeds.append(embed)

               if len(embeds) == 1:
                   await ctx.send(embed=embeds[0])
               else:
                   await menu(ctx, embeds, DEFAULT_CONTROLS)

       except Exception as e:
           log.error(f"Error fetching tournament data: {e}", exc_info=True)
           await ctx.send("Something went wrong... :pensive:")

   def _create_tournament_embeds(self, tournaments: List[dict], search_query: str) -> List[discord.Embed]:
       """Create tournament embed pages."""
       embeds = []
       chunk_size = 3
       for i in range(0, len(tournaments), chunk_size):
           chunk = tournaments[i:i + chunk_size]
           embed = discord.Embed(
               title=f"Tournaments matching: {search_query}",
               description=f"Showing {i + 1}–{min(len(tournaments), i + chunk_size)} "
                          f"of {len(tournaments)} results",
               color=discord.Color.blue()
           )
           for t in chunk:
               next_date = "No upcoming date"
               if t.get("nextDate"):
                   try:
                       dt = datetime.fromisoformat(t["nextDate"].replace("Z", "+00:00"))
                       timestamp = int(dt.timestamp())
                       next_date = f"<t:{timestamp}:F>"
                   except ValueError:
                       next_date = t["nextDate"]
               embed.add_field(
                   name=f"{t.get('shortName', 'N/A')} — {t.get('name', 'Unknown Tournament')}",
                   value=f"Next Date: {next_date}",
                   inline=False
               )
           embeds.append(embed)
       return embeds
