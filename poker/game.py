import asyncio
import logging
import random
from dataclasses import dataclass
from io import BytesIO
from typing import List

import discord
from PIL import Image
from redbot.core.data_manager import bundled_data_path

from .ai import PokerAI
from .views import PokerActionView

CHIP_EMOJI = "💰"


@dataclass
class Card:
    suit: str
    value: str

    def __str__(self):
        return f"{self.value}{self.suit}"


class PokerGame:
    def __init__(self, ctx, channel, cog, *players):
        self.ctx = ctx
        self.channel = channel
        self.bot = ctx.bot
        self.cog = cog
        self.game_ended = False  # Add this flag

        # Create display name mapping and validate unique names
        self.display_names = {}
        name_counts = {}
        unique_players = []

        for player in players:
            if len(unique_players) >= 8:  # Hard limit at 8 players
                break

            base_name = player.display_name
            if base_name in name_counts:
                name_counts[base_name] += 1
                self.display_names[player] = f"{base_name}_{name_counts[base_name]}"
            else:
                name_counts[base_name] = 1
                self.display_names[player] = base_name
            unique_players.append(player)

        # Store all players and initialize their states
        self.all_players = list(unique_players)  # Only use validated unique players
        self.active_players = list(unique_players)
        self.players = {player: [] for player in unique_players}
        self.player_chips = {player: 1000 for player in unique_players}
        self.player_bets = {player: 0 for player in unique_players}

        self.deck = self._create_deck()
        self.community_cards = []
        self.current_pot = 0
        self.current_bet = 0
        self.last_bet = 0
        self.small_blind = 10
        self.big_blind = 20
        self.dealer_idx = 0
        self.turn_idx = 0
        self.log = logging.getLogger('red.cobraycogs.poker')
        self._task = asyncio.create_task(self.run())
        self._task.add_done_callback(self.error_callback)

        self.last_action_time = asyncio.get_event_loop().time()
        self.timeout_task = asyncio.create_task(self.check_timeout())
        self.GAME_TIMEOUT = 300  # 5 minutes without activity
        self.timeout_warned = False

    @staticmethod
    def _create_deck():
        suits = ['♠', '♥', '♦', '♣']
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [Card(suit, value) for suit in suits for value in values]

    async def send_hand(self, player):
        if isinstance(player, discord.Member) and player in self.players:
            if await self.cog.config.guild(self.channel.guild).do_image():
                img = await self.generate_hand_image(self.players[player])
                await player.send(
                    content=f"Your hole cards ({self.player_chips[player]} {CHIP_EMOJI})",
                    file=discord.File(img, 'hand.png')
                )
            else:
                cards_str = ' '.join(str(card) for card in self.players[player])
                await player.send(f"Your hole cards: {cards_str} ({self.player_chips[player]} {CHIP_EMOJI})")

    async def generate_hand_image(self, cards: List[Card]) -> BytesIO:
        path = bundled_data_path(self.cog)
        result = Image.new('RGB', (800, 400), (0, 82, 33))

        x_offset = 20
        for card in cards:
            try:
                card_filename = self._get_card_filename(card)
                card_img = Image.open(path / "cards" / card_filename).convert('RGBA')
                white_bg = Image.new('RGBA', card_img.size, 'white')
                white_bg.paste(card_img, (0, 0), card_img)
                white_bg = white_bg.resize((120, 180))
                result.paste(white_bg, (x_offset, 20))
            except FileNotFoundError:
                self.log.warning(f"Card image not found: {card}")
            x_offset += 140

        buffer = BytesIO()
        result.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    async def generate_community_image(self) -> BytesIO:
        path = bundled_data_path(self.cog)
        result = Image.new('RGB', (800, 200), (0, 82, 33))

        x_offset = 20
        for card in self.community_cards:
            card_filename = self._get_card_filename(card)
            card_img_path = path / "cards" / card_filename

            try:
                self.log.debug(f"Loading card image from: {card_img_path}")
                card_img = Image.open(card_img_path).convert('RGBA')
                white_bg = Image.new('RGBA', card_img.size, 'white')
                white_bg.paste(card_img, (0, 0), card_img)
                white_bg = white_bg.resize((120, 180))
                result.paste(white_bg, (x_offset, 10))
                x_offset += 140
            except FileNotFoundError:
                self.log.warning(f"Card image not found for {card} at path: {card_img_path}")
                x_offset += 140  # Ensure offset increases to avoid overlay issues

        buffer = BytesIO()
        result.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    async def process_bet(self, player, amount):
        """Process a bet for a player, updating all relevant state."""
        if amount > self.player_chips[player]:
            return False

        self.player_chips[player] -= amount
        self.player_bets[player] += amount
        self.current_pot += amount
        return True

    def create_game_state(self, player):
        return {
            'hole_cards': self.players[player],
            'community_cards': self.community_cards,
            'call_amount': self.current_bet - self.player_bets[player],
            'pot': self.current_pot,
            'min_raise': self.big_blind,
            'max_raise': self.player_chips[player],
            'active_players_count': len(self.active_players)
        }

    async def betting_round(self, round_name):
        """Handle a complete betting round."""
        self.turn_idx = (self.dealer_idx + 1) % len(self.active_players)
        last_raise_idx = (self.dealer_idx + 2) % len(self.active_players)  # Big blind position
        action_count = 0
        max_actions = len(self.active_players) * 8
        players_acted = set()
        last_valid_action = None

        self.log.debug(f"Starting betting round: {round_name} with {len(self.active_players)} players")

        while True:
            player = self.active_players[self.turn_idx]
            call_amount = self.current_bet - self.player_bets[player]
            min_raise = self.current_bet + max(self.big_blind, self.current_bet - self.last_bet)

            self.log.debug(f"Betting round state: Round={round_name}, Player={self.get_player_name(player)}, "
                           f"Call={call_amount}, Current bet={self.current_bet}, Min raise={min_raise}, "
                           f"Active players={len(self.active_players)}")

            # Check if we're heads up (1v1)
            is_heads_up = len(self.active_players) <= 2

            action_success = False
            if isinstance(player, PokerAI):
                game_state = self.create_game_state(player)
                game_state['min_raise'] = min_raise
                game_state['is_heads_up'] = is_heads_up

                attempts = 0
                while attempts < 3 and not action_success:
                    action, amount = player.decide_action(game_state)
                    if is_heads_up and action == "fold":
                        action = "call"  # Convert fold to call in heads up
                    if action == "raise":
                        if amount < min_raise:
                            self.log.debug(f"AI attempted invalid raise of {amount} (min: {min_raise})")
                            action = "call"  # Convert to call if raise is too small
                            amount = None
                    action_success = await self.handle_action(player, action, amount, call_amount)
                    attempts += 1
                if not action_success:
                    action_success = await self.handle_action(player, "call", None, call_amount)
            else:
                action, amount = await self.prompt_player_using_view(player, call_amount)
                if action is not None:
                    action_success = await self.handle_action(player, action, amount, call_amount)

            if action_success:
                action_count += 1
                players_acted.add(player)
                last_valid_action = action

                # Always move to next player after a successful action
                self.turn_idx = (self.turn_idx + 1) % len(self.active_players)

                if action == "raise":
                    last_raise_idx = (self.turn_idx - 1) % len(self.active_players)
            else:
                # If action failed, show error but still move to next player to prevent loops
                self.log.debug(f"Action failed for {self.get_player_name(player)}, moving to next player")
                self.turn_idx = (self.turn_idx + 1) % len(self.active_players)
                continue

            # Break conditions
            if action_count >= max_actions:
                self.log.warning(f"Breaking from betting round {round_name} due to max actions reached")
                break

            if len(self.active_players) <= 1:
                self.log.debug(f"Breaking from betting round {round_name} - only one player remains")
                break

            # Check if betting round is complete
            all_players_acted = all(p in players_acted for p in self.active_players)
            all_bets_equal = all(self.player_bets[p] == self.current_bet for p in self.active_players)
            round_complete = (all_players_acted and all_bets_equal and
                              (last_valid_action != "raise" or self.turn_idx == last_raise_idx))

            if round_complete:
                self.log.debug(f"Breaking from betting round {round_name} - round complete")
                break

            await asyncio.sleep(3)

    async def prompt_player_using_view(self, player, call_amount):
        """Enhanced player prompting with exact game state format"""
        self.log.debug(f"Prompting {self.get_player_name(player)} for action")

        # Create view specific to this player
        view = PokerActionView(self, player)

        # Build message with only current player's info
        msg = [
            f"⚔️ **{self.get_player_name(player)}'s Turn**\n",
            f"Current bet: {self.current_bet} 💰",
            f"Amount to call: {call_amount} 💰",
            f"Your chips: {self.player_chips[player]} 💰",
            f"Pot: {self.current_pot} 🏆"
        ]

        # Add community cards if they exist
        if self.community_cards:
            cards_str = ' '.join(str(card) for card in self.community_cards)
            msg.append(f"\nCommunity cards: {cards_str}")

        message = await self.channel.send('\n'.join(msg), view=view)
        view.message = message  # Store for timeout handling

        # Set timeout
        view.timeout = 60.0

        # Wait for player action
        await view.wait()

        # Clean up the prompt message
        try:
            await message.delete()
        except:
            pass

        return view.action, view.raise_amount

    def count_human_players(self):
        """Count number of human players currently in the game."""
        return len([p for p in self.active_players if isinstance(p, discord.Member)])

    @property
    def has_multiple_humans(self):
        """Check if there are multiple human players in the game."""
        return self.count_human_players() > 1

    async def check_end_game_button(self):
        """Check if End Game button should be added to the action view."""
        if not self.has_multiple_humans:
            return True  # Show regular end game button for single human player
        return False  # Otherwise use voting system

    async def update_last_action(self):
        """Update the last action timestamp."""
        self.last_action_time = asyncio.get_event_loop().time()
        self.timeout_warned = False

    async def handle_action(self, player, action, amount, call_amount):
        """Handle a player's betting action."""
        try:
            # Update last action time for timeout tracking
            await self.update_last_action()

            self.log.debug(f"Action received - Player: {self.get_player_name(player)}, Action: {action}, "
                           f"Active players: {len(self.active_players)}, Human players: {self.count_human_players()}")

            if action == "fold":
                # In single player mode (vs AI), always allow folding
                if self.count_human_players() == 1:
                    self.active_players.remove(player)
                    await self.channel.send(f"{self.get_player_name(player)} folds!")
                    return True

                # In multiplayer, prevent folding in heads up
                elif len(self.active_players) == 2:
                    await self.channel.send(f"{self.get_player_name(player)} can't fold in heads up play!")
                    return False

                # Normal folding for 3+ players
                self.active_players.remove(player)
                await self.channel.send(f"{self.get_player_name(player)} folds!")
                return True

            elif action == "call":
                if call_amount == 0:
                    await self.channel.send(f"{self.get_player_name(player)} checks!")
                    return True
                else:
                    if not await self.process_bet(player, call_amount):
                        await self.channel.send(f"{self.get_player_name(player)} doesn't have enough chips!")
                        return False
                    await self.channel.send(f"{self.get_player_name(player)} calls {call_amount}!")
                    return True

            elif action == "raise":
                # Calculate minimum raise size
                min_raise = self.current_bet + max(self.big_blind, self.current_bet - self.last_bet)

                self.log.debug(f"Raise validation - Amount: {amount}, Min raise: {min_raise}, "
                               f"Current bet: {self.current_bet}, Last bet: {self.last_bet}")

                if amount < min_raise:
                    await self.channel.send(f"Minimum raise is {min_raise}!")
                    return False

                total_to_call = amount - self.player_bets[player]

                if total_to_call > self.player_chips[player]:
                    await self.channel.send(f"{self.get_player_name(player)} doesn't have enough chips!")
                    return False

                if not await self.process_bet(player, total_to_call):
                    return False

                self.last_bet = self.current_bet
                self.current_bet = amount
                await self.channel.send(f"{self.get_player_name(player)} raises to {amount}!")
                return True

            return False

        except Exception as e:
            self.log.exception(f"Error handling action for {self.get_player_name(player)}")
            return False

    async def show_game_state(self):
        """Show the general game state but without individual player chip counts"""
        community_str = "Community Cards"

        if self.community_cards:
            community_img = await self.generate_community_image()
            await self.channel.send(
                content=community_str,
                file=discord.File(community_img, 'community.png')
            )
        else:
            await self.channel.send("No community cards yet")

        # Display only current bet and pot
        game_info = f"**Current bet**: {self.current_bet} | **Pot**: {self.current_pot}"
        await self.channel.send(game_info)

    def get_player_name(self, player):
        """Get the display name for a player, handling both Member and AI players."""
        try:
            if isinstance(player, discord.Member):
                return self.display_names.get(player, player.display_name)
            elif isinstance(player, PokerAI):
                return player.display_name
            else:
                return str(player)
        except Exception as e:
            self.log.exception(f"Error getting player name: {e}")
            return str(player)  # Fallback to string representation

    @staticmethod
    def _get_card_filename(card: Card) -> str:
        suit_map = {
            '♠': 'spades',
            '♥': 'hearts',
            '♦': 'diamonds',
            '♣': 'clubs'
        }
        value_translation = {
            'J': 'jack',
            'Q': 'queen',
            'K': 'king',
            'A': 'ace'
        }

        translated_rank = value_translation.get(card.value, card.value)
        translated_suit = suit_map.get(card.suit, '')

        return f"{translated_rank}_of_{translated_suit}.png"

    async def run(self):
        try:
            while len(self.active_players) > 1:
                self.log.debug(f"Starting a new round with players: {self.active_players}")
                self.prepare_new_round()
                self.deal_hole_cards()

                # Show game state including player hands and community cards
                await self.show_game_state()

                await self.process_blinds()
                await self.betting_round("pre-flop")

                # Check if only one player remains after pre-flop
                if len(self.active_players) == 1:
                    await self.handle_single_player_win()
                    self.reset_round()
                    continue

                if len(self.deck) >= 3:
                    self.deal_community_cards(3)
                    await self.show_game_state()
                    await self.betting_round("flop")

                    if len(self.active_players) == 1:
                        await self.handle_single_player_win()
                        self.reset_round()
                        continue

                if len(self.deck) >= 1:
                    self.deal_community_cards(1)
                    await self.show_game_state()
                    await self.betting_round("turn")

                    if len(self.active_players) == 1:
                        await self.handle_single_player_win()
                        self.reset_round()
                        continue

                if len(self.deck) >= 1:
                    self.deal_community_cards(1)
                    await self.show_game_state()
                    await self.betting_round("river")

                # Only go to showdown if we have 2 or more players
                if len(self.active_players) >= 2:
                    await self.showdown()
                elif len(self.active_players) == 1:
                    await self.handle_single_player_win()
                else:
                    # This shouldn't happen, but let's handle it gracefully
                    self.log.error("No active players remain - this shouldn't happen!")
                    await self.channel.send("Error: No active players remain. Ending game.")
                    return

                self.reset_round()

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.log.exception("Error in poker game:")
            await self.channel.send("An error occurred. The game will now end.")
            raise

    async def handle_single_player_win(self):
        """Handle case where only one player remains (everyone else folded)."""
        if len(self.active_players) != 1:
            self.log.error("handle_single_player_win called with != 1 players")
            return

        winner = self.active_players[0]
        self.player_chips[winner] += self.current_pot
        await self.channel.send(
            f"{self.get_player_name(winner)} wins {self.current_pot} {CHIP_EMOJI} (all other players folded)!")

        # Reset round immediately
        self.prepare_new_round()

    def prepare_new_round(self):
        """Reset for a new round and restore all players who still have chips."""
        self.community_cards = []
        self.current_pot = 0
        self.current_bet = 0
        self.last_bet = 0

        # Restore ALL players who have chips > 0
        self.active_players = [p for p in self.all_players if self.player_chips[p] > 0]
        self.players = {player: [] for player in self.active_players}  # Reset hole cards
        self.player_bets = {player: 0 for player in self.active_players}

        if len(self.active_players) < 2:
            return

        # Find next valid dealer position
        while True:
            next_dealer = (self.dealer_idx + 1) % len(self.all_players)
            if self.all_players[next_dealer] in self.active_players:
                self.dealer_idx = next_dealer
                break
            self.dealer_idx = next_dealer

        self.turn_idx = self.dealer_idx
        self.deck = self._create_deck()

    def deal_hole_cards(self):
        random.shuffle(self.deck)
        for player in self.active_players:
            if len(self.deck) >= 2:
                self.players[player] = [self.deck.pop() for _ in range(2)]
                asyncio.create_task(self.send_hand(player))
            else:
                self.log.error("Not enough cards in deck to deal hole cards.")

    def deal_community_cards(self, number):
        if len(self.deck) >= number:
            self.community_cards.extend(self.deck.pop() for _ in range(number))
        else:
            self.log.error(f"Not enough cards in deck to deal {number} community cards.")

    async def process_blinds(self):
        """Handle the posting of small and big blinds."""
        if len(self.active_players) < 2:
            return

        sb_pos = (self.dealer_idx + 1) % len(self.active_players)
        bb_pos = (self.dealer_idx + 2) % len(self.active_players)

        # Post small blind
        sb_player = self.active_players[sb_pos]
        if not await self.process_bet(sb_player, self.small_blind):
            self.log.error(f"Failed to post small blind for {self.get_player_name(sb_player)}")
            return
        await self.channel.send(f"{self.get_player_name(sb_player)} posts small blind of {self.small_blind}")
        self.last_bet = self.small_blind

        # Post big blind
        bb_player = self.active_players[bb_pos]
        if not await self.process_bet(bb_player, self.big_blind):
            self.log.error(f"Failed to post big blind for {self.get_player_name(bb_player)}")
            return
        await self.channel.send(f"{self.get_player_name(bb_player)} posts big blind of {self.big_blind}")

        self.current_bet = self.big_blind
        self.last_bet = self.small_blind  # Last bet was small blind

    async def showdown(self):
        """Handle the showdown phase of the game."""
        # Reveal all players' hands
        reveal_message = "**Showdown!**\n"

        # Generate and send images for each player's hand
        for player in self.active_players:
            if await self.cog.config.guild(self.channel.guild).do_image():
                hand_img = await self.generate_hand_image(self.players[player])
                await self.channel.send(
                    content=f"{self.get_player_name(player)}'s hand:",
                    file=discord.File(hand_img, 'hand.png')
                )
            else:
                cards_str = ' '.join(str(card) for card in self.players[player])
                reveal_message += f"{self.get_player_name(player)}'s hand: {cards_str}\n"

        if not await self.cog.config.guild(self.channel.guild).do_image():
            await self.channel.send(reveal_message)

        # Show the final community cards again for clarity
        if self.community_cards:
            community_img = await self.generate_community_image()
            await self.channel.send(
                content="Final community cards:",
                file=discord.File(community_img, 'community.png')
            )

        # Evaluate each player's hand and store results
        hand_rankings = []
        for player in self.active_players:
            score, hand_type = self.evaluate_hand(self.players[player], self.community_cards)
            hand_rankings.append((player, score, hand_type))

        # Sort players by hand strength
        hand_rankings.sort(key=lambda x: x[1], reverse=True)

        # Determine winner(s)
        winning_score = hand_rankings[0][1]
        winners = [(player, hand_type) for player, score, hand_type in hand_rankings if score == winning_score]

        # Split pot if there are multiple winners
        split_amount = self.current_pot // len(winners)
        for winner, hand_type in winners:
            self.player_chips[winner] += split_amount

        # Announce winner(s) and their winning hand
        if len(winners) == 1:
            winner, hand_type = winners[0]
            await self.channel.send(
                f"{self.get_player_name(winner)} wins {self.current_pot} {CHIP_EMOJI} "
                f"with {hand_type}!"
            )
        else:
            winners_str = ", ".join(f"{self.get_player_name(w)} ({h})" for w, h in winners)
            await self.channel.send(
                f"Split pot! {winners_str} each win {split_amount} {CHIP_EMOJI}!"
            )

    def evaluate_hand(self, hole_cards: List[Card], community_cards: List[Card]) -> tuple:
        """
        Evaluate poker hand strength.
        Returns (score, hand_type) tuple for comparison.
        """
        all_cards = hole_cards + community_cards

        # Value mapping for correct ordering
        value_map = {
            '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
            '7': 7, '8': 8, '9': 9, '10': 10,
            'J': 11, 'Q': 12, 'K': 13, 'A': 14
        }

        try:
            # Initialize counts
            value_counts = {}
            suit_counts = {}
            card_values = []

            # Count values and suits
            for card in all_cards:
                value_counts[card.value] = value_counts.get(card.value, 0) + 1
                suit_counts[card.suit] = suit_counts.get(card.suit, 0) + 1
                card_values.append(value_map[card.value])

            # Get unique values for straight checking
            unique_values = sorted(set(card_values))

            # Check for flush
            flush_suit = None
            for suit, count in suit_counts.items():
                if count >= 5:
                    flush_suit = suit
                    break

            # Check for straight (must be 5 consecutive unique values)
            straight = False
            straight_high = 0
            if len(unique_values) >= 5:
                # Check normal straight
                for i in range(len(unique_values) - 4):
                    consecutive_count = 1
                    for j in range(4):
                        if unique_values[i + j + 1] - unique_values[i + j] == 1:
                            consecutive_count += 1
                        else:
                            break
                    if consecutive_count == 5:
                        straight = True
                        straight_high = unique_values[i + 4]
                        break

                # Check Ace-low straight (A,2,3,4,5) specifically
                if not straight and 14 in unique_values:  # If we have an Ace
                    if {2, 3, 4, 5}.issubset(set(unique_values)):
                        straight = True
                        straight_high = 5

            # Get best hand score
            frequencies = [(v, k) for k, v in value_counts.items()]
            frequencies.sort(key=lambda x: (x[0], value_map[x[1]]), reverse=True)

            # Determine hand type and score
            score = 0
            hand_type = "High Card"

            # Four of a kind
            if frequencies[0][0] == 4:
                score = 8000000 + value_map[frequencies[0][1]] * 10000
                hand_type = "Four of a Kind"

            # Full house
            elif frequencies[0][0] == 3 and len(frequencies) > 1 and frequencies[1][0] >= 2:
                score = 7000000 + value_map[frequencies[0][1]] * 10000 + value_map[frequencies[1][1]]
                hand_type = "Full House"

            # Flush
            elif flush_suit:
                flush_cards = sorted([value_map[card.value] for card in all_cards if card.suit == flush_suit],
                                     reverse=True)
                score = 6000000 + sum(v * (10 ** i) for i, v in enumerate(flush_cards[:5]))
                hand_type = "Flush"

            # Straight
            elif straight:
                score = 5000000 + straight_high
                hand_type = "Straight"

            # Three of a kind
            elif frequencies[0][0] == 3:
                score = 4000000 + value_map[frequencies[0][1]] * 10000
                hand_type = "Three of a Kind"

            # Two pair
            elif frequencies[0][0] == 2 and len(frequencies) > 1 and frequencies[1][0] == 2:
                score = 3000000 + max(value_map[frequencies[0][1]], value_map[frequencies[1][1]]) * 10000
                hand_type = "Two Pair"

            # One pair
            elif frequencies[0][0] == 2:
                score = 2000000 + value_map[frequencies[0][1]] * 10000
                hand_type = "One Pair"

            # High card
            else:
                score = 1000000 + max(card_values)
                hand_type = "High Card"

            # Add kickers for tie breaks
            kicker_values = sorted(card_values, reverse=True)[:5]
            for i, value in enumerate(kicker_values):
                score += value * (0.01 ** (i + 1))

            return score, hand_type

        except Exception as e:
            self.log.exception(f"Error in hand evaluation: {e}")
            return -1, "Invalid Hand"

    def reset_round(self):
        """Reset just the current round state without modifying player list."""
        self.community_cards = []
        for player in self.all_players:  # Clear all players' hands, not just active ones
            if player in self.players:
                self.players[player] = []

        self.current_pot = 0
        self.current_bet = 0
        self.last_bet = 0
        self.player_bets = {player: 0 for player in self.active_players}

        if len(self.active_players) < 2:
            return

        # Find next valid dealer position
        while True:
            next_dealer = (self.dealer_idx + 1) % len(self.all_players)
            if self.all_players[next_dealer] in self.active_players:
                self.dealer_idx = next_dealer
                break
            self.dealer_idx = next_dealer

        self.deck = self._create_deck()

    def error_callback(self, fut):
        try:
            fut.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.log.exception("Error in poker game:")
        try:
            self.cog.games.remove(self)
        except ValueError:
            pass

    async def clean_shutdown(self):
        """Cleanly shut down the game."""
        try:
            self.game_ended = True  # Set this first to stop other operations

            # Cancel the timeout task
            if hasattr(self, 'timeout_task'):
                self.timeout_task.cancel()

            # Cancel the main game task
            if hasattr(self, '_task'):
                self._task.cancel()

            # Clear game state
            self.active_players = []
            self.players = {}
            self.player_chips = {}
            self.player_bets = {}

            # Send final message
            await self.channel.send("Game has been ended.")

            # Remove from active games
            try:
                self.cog.games.remove(self)
            except (ValueError, AttributeError):
                pass

        except Exception as e:
            self.log.exception("Error during game shutdown")
            await self.channel.send("Error while ending game, but game has been terminated.")

    async def check_timeout(self):
        """Monitor game for inactivity."""
        try:
            while not self.game_ended:
                current_time = asyncio.get_event_loop().time()
                time_since_last_action = current_time - self.last_action_time

                # Send warning at 4 minutes
                if time_since_last_action > (self.GAME_TIMEOUT - 60) and not self.timeout_warned:
                    await self.channel.send("⚠️ Warning: Game will auto-end in 1 minute due to inactivity!")
                    self.timeout_warned = True

                # End game at 5 minutes
                if time_since_last_action > self.GAME_TIMEOUT:
                    self.game_ended = True
                    await self.channel.send("Game ended due to inactivity.")
                    await self.clean_shutdown()
                    break

                await asyncio.sleep(30)  # Check every 30 seconds

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log.exception("Error in timeout checker")
