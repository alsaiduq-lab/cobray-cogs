import random

import discord
from .ai import PokerAI, STARTER_NAMES
import logging


class PokerActionView(discord.ui.View):
    def __init__(self, game, current_player):
        super().__init__()
        self.game = game
        self.current_player = current_player
        self.action = None
        self.raise_amount = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Validate that only the current player can use the buttons"""
        if interaction.user != self.current_player:
            await interaction.response.send_message(
                f"It's {self.current_player.display_name}'s turn!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Call", style=discord.ButtonStyle.primary)
    async def call(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.action = "call"
        # Make buttons visibly disabled after use
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self, content=f"{interaction.user.display_name} is calling...")
        self.stop()

    @discord.ui.button(label="Raise", style=discord.ButtonStyle.secondary)
    async def raise_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = RaiseModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Fold", style=discord.ButtonStyle.danger)
    async def fold(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.action = "fold"
        # Make buttons visibly disabled after use
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self, content=f"{interaction.user.display_name} is folding...")
        self.stop()

    @discord.ui.button(label="End Game", style=discord.ButtonStyle.danger, row=1, custom_id="end_game")
    async def end_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.current_player:
            await interaction.response.send_message(
                "Only the current player can end the game.",
                ephemeral=True
            )
            return
        await self.game.clean_shutdown()
        await interaction.response.edit_message(content="Game ended.", view=None)
        self.stop()


class RaiseModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Raise Amount")
        self.view = view
        self.amount = discord.ui.TextInput(
            label="Amount to raise",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            self.view.raise_amount = amount
            self.view.action = "raise"
            await interaction.response.edit_message(view=None)
            self.view.stop()
        except ValueError:
            await interaction.response.send_message("Please enter a valid number", ephemeral=True)


class GetPlayersView(discord.ui.View):
    def __init__(self, ctx, max_players):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.max_players = max_players
        self.players = [ctx.author]
        self.log = logging.getLogger('red.cobraycogs.poker')
        self.used_names = set()  # Track which names have been used

    def generate_message(self):
        msg = "Current Players:\n"
        for idx, player in enumerate(self.players, start=1):
            msg += f"Player {idx} - {self.get_player_name(player)}\n"
        msg += f"\nClick to join or add AI. Max players: {self.max_players}"
        return msg

    def get_player_name(self, player):
        if isinstance(player, discord.Member):
            return player.display_name
        elif isinstance(player, PokerAI):
            return player.display_name
        else:
            return str(player)

    def get_available_name(self):
        """Get a random unused name from STARTER_NAMES."""
        available_names = [name for name in STARTER_NAMES if name not in self.used_names]
        if not available_names:
            return None
        name = random.choice(available_names)
        self.used_names.add(name)
        return name

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, custom_id="join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.ctx.author.id:
            await interaction.response.send_message('You are already in the game.', ephemeral=True)
            return

        if len(self.players) >= self.max_players:
            await interaction.response.send_message('The game is full.', ephemeral=True)
            return

        if interaction.user in self.players:
            await interaction.response.send_message('You already joined.', ephemeral=True)
            return

        self.players.append(interaction.user)
        await self.update_view(interaction)

    @discord.ui.button(label="Add Easy AI", style=discord.ButtonStyle.blurple, custom_id="easy_ai")
    async def add_easy_ai(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message('Only the game creator can add AI.', ephemeral=True)
                return

            if len(self.players) >= self.max_players:
                await interaction.response.send_message('The game is full.', ephemeral=True)
                return

            ai_name = self.get_available_name()
            if not ai_name:
                await interaction.response.send_message('No more unique AI names available.', ephemeral=True)
                return

            ai = PokerAI(difficulty='easy')
            ai.display_name = ai_name  # Set the name after creation
            self.players.append(ai)
            await self.update_view(interaction)

        except Exception as e:
            self.log.exception(f"Error in add_easy_ai: {e}")
            await interaction.response.send_message('An error occurred while adding the AI player.', ephemeral=True)

    @discord.ui.button(label="Add Hard AI", style=discord.ButtonStyle.danger, custom_id="hard_ai")
    async def add_hard_ai(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id != self.ctx.author.id:
                await interaction.response.send_message('Only the game creator can add AI.', ephemeral=True)
                return

            if len(self.players) >= self.max_players:
                await interaction.response.send_message('The game is full.', ephemeral=True)
                return

            ai_name = self.get_available_name()
            if not ai_name:
                await interaction.response.send_message('No more unique AI names available.', ephemeral=True)
                return

            ai = PokerAI(difficulty='hard')
            ai.display_name = ai_name  # Set the name after creation
            self.players.append(ai)
            await self.update_view(interaction)

        except Exception as e:
            self.log.exception(f"Error in add_hard_ai: {e}")
            await interaction.response.send_message('An error occurred while adding the AI player.', ephemeral=True)

    async def update_view(self, interaction):
        """Update the view and handle button states."""
        if len(self.players) >= self.max_players:
            # Disable all join/add buttons when max players reached
            for child in self.children:
                if child.custom_id in ['join', 'easy_ai', 'hard_ai']:
                    child.disabled = True
            view = self
        else:
            view = self

        await interaction.response.edit_message(content=self.generate_message(), view=view)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.green, custom_id="start")
    async def start_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('Only the game creator can start the game.', ephemeral=True)
            return

        if len(self.players) < 2:
            await interaction.response.send_message('Need at least 2 players to start.', ephemeral=True)
            return

        await interaction.response.edit_message(view=None)
        self.stop()


class ConfirmView(discord.ui.View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=60)
        self.member = member
        self.result = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow the specified member to interact
        if interaction.user.id != self.member.id:
            await interaction.response.send_message('You cannot interact with this button.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Accept', style=discord.ButtonStyle.green)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.result = True
        self.stop()

    @discord.ui.button(label='Deny', style=discord.ButtonStyle.red)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.stop()


class EndGameView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=60)
        self.game = game
        self.votes = set()  # Track who has voted to end
        self.required_votes = max(2, (len(game.active_players) + 1) // 2)  # Majority needed
        self.ended = False
        self.log = logging.getLogger('red.cobraycogs.poker')

    def vote_count_message(self):
        """Generate the current vote status message."""
        current_votes = len(self.votes)
        return f"Votes to end game: {current_votes}/{self.required_votes}"

    @discord.ui.button(label="Vote to End Game", style=discord.ButtonStyle.danger)
    async def vote_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Check if player is in the game
            if interaction.user not in self.game.all_players:
                await interaction.response.send_message(
                    "Only players in the game can vote to end it.",
                    ephemeral=True
                )
                return

            # Add vote
            self.votes.add(interaction.user)
            votes_needed = self.required_votes - len(self.votes)

            # If only one player left, end immediately
            if len(self.game.active_players) <= 1:
                await self.end_game(interaction)
                return

            # Check if we have enough votes
            if len(self.votes) >= self.required_votes:
                await self.end_game(interaction)
            else:
                # Update the message with current vote count
                await interaction.response.edit_message(
                    content=f"{self.vote_count_message()}\nNeed {votes_needed} more vote(s).",
                    view=self
                )

        except Exception as e:
            self.log.exception("Error in vote_end")
            await interaction.response.send_message(
                "An error occurred while processing your vote.",
                ephemeral=True
            )

    @discord.ui.button(label="Cancel Vote", style=discord.ButtonStyle.secondary)
    async def cancel_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user not in self.votes:
                await interaction.response.send_message(
                    "You haven't voted to end the game.",
                    ephemeral=True
                )
                return

            self.votes.remove(interaction.user)
            votes_needed = self.required_votes - len(self.votes)
            await interaction.response.edit_message(
                content=f"{self.vote_count_message()}\nNeed {votes_needed} more vote(s).",
                view=self
            )

        except Exception as e:
            self.log.exception("Error in cancel_vote")
            await interaction.response.send_message(
                "An error occurred while processing your vote cancellation.",
                ephemeral=True
            )

    async def initiate_end_game_vote(self, interaction: discord.Interaction = None):
        """Start the end game voting process."""
        try:
            view = EndGameView(self)

            if len(self.active_players) <= 1:
                content = "Only one player remaining. Click to end game."
            else:
                content = f"Vote to end game. Required votes: {view.required_votes}"

            message = await self.channel.send(content, view=view)
            view.message = message  # Store for timeout handling

            return view

        except Exception as e:
            self.log.exception("Error initiating end game vote")
            if interaction:
                await interaction.response.send_message(
                    "An error occurred while starting the end game vote.",
                    ephemeral=True
                )
            return None

    async def end_game(self, interaction: discord.Interaction):
        """Handle the actual game ending process."""
        if self.ended:
            return

        self.ended = True
        try:
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)

            # Clean up the game
            await self.game.clean_shutdown()

            # Final message
            if len(self.game.active_players) <= 1:
                message = "Game ended - only one player remaining."
            else:
                voters = ", ".join([player.display_name for player in self.votes])
                message = f"Game ended by vote. (Voters: {voters})"

            await self.game.channel.send(message)
            self.stop()

        except Exception as e:
            self.log.exception("Error ending game")
            await self.game.channel.send(
                "An error occurred while ending the game, but the game has been terminated."
            )
            self.stop()

    async def on_timeout(self):
        """Handle view timeout."""
        try:
            if not self.ended:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(
                    content="Vote to end game has timed out.",
                    view=self
                )
        except:
            pass