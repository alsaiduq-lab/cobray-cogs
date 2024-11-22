from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import random
import logging
import uuid

STARTER_NAMES = ["Ace", "Chip", "Skylark", "Timmy", "Bob", "Enzo", "Mike", "Dot", "Andrea", "Turbo", "Surfer"]

@dataclass
class PokerAI:
    difficulty: str = 'easy'
    profile_manager: Optional[object] = None
    display_name: str = field(default_factory=lambda: random.choice(STARTER_NAMES))
    id: str = field(default_factory=lambda: f"AI_{uuid.uuid4().hex[:8]}")
    current_hand_strength: float = 0.0
    raise_count: int = 0

    def __post_init__(self):
        self.mention = self.display_name
        self.log = logging.getLogger('red.cobraycogs.poker')
        self._player_profile = None
        self.session_stats = {
            'hands_played': 0,
            'hands_won': 0,
            'total_profit': 0,
            'preflop_vpip': 0,
            'preflop_pfr': 0,
            'aggression_frequency': 0.0
        }
        PokerAI.ensure_unique_name(self)

    @property
    def player_profile(self):
        if self._player_profile is None and self.profile_manager is not None:
            self._player_profile = self.profile_manager.get_profile(self.id, self.display_name)
        return self._player_profile

    @classmethod
    def ensure_unique_name(cls, ai_player):
        existing_names = [p.display_name for p in cls.all_ai_players if p != ai_player]
        while ai_player.display_name in existing_names:
            ai_player.display_name += f" {random.randint(1, 999)}"
        ai_player.mention = ai_player.display_name

    all_ai_players = []

    def __hash__(self):
        return hash(self.id)

    def __str__(self):
        return self.display_name

    def __repr__(self):
        return f"PokerAI(name='{self.display_name}', id='{self.id}')"

    def __eq__(self, other):
        if not isinstance(other, PokerAI):
            return NotImplemented
        return self.id == other.id

    def decide_action(self, game_state: Dict) -> Tuple[str, Optional[int]]:
        try:
            call_amount = game_state.get('call_amount', 0)
            pot = game_state.get('pot', 0)
            min_raise = game_state.get('min_raise', 20)
            max_raise = game_state.get('max_raise', 1000)
            position = game_state.get('position', 'middle')
            round_name = game_state.get('round_name', 'preflop')
            current_bet = game_state.get('current_bet', 0)
            my_chips = game_state.get('my_chips', 0)
            my_current_bet = game_state.get('my_current_bet', 0)

            if call_amount >= my_chips > 0:
                pot_odds = my_chips / (pot + my_chips)
                if self.current_hand_strength > pot_odds * 1.2:
                    self.log.info(f"AI {self.display_name} going all-in with strength {self.current_hand_strength}")
                    return "call", None
                return "fold", None

            hole_cards = game_state.get('hole_cards', [])
            self.current_hand_strength = self._evaluate_hand_strength(hole_cards)

            if self.player_profile:
                tendencies = self.player_profile.get_tendencies()
                self.current_hand_strength = self._adjust_hand_strength(
                    self.current_hand_strength,
                    tendencies,
                    position,
                    round_name
                )

            opponent_tendencies = []
            if self.profile_manager:
                opponents = game_state.get('active_players', [])
                for opp in opponents:
                    if hasattr(opp, 'id'):
                        tendencies = self.profile_manager.get_player_tendencies(opp.id)
                        opponent_tendencies.append(tendencies)

            if opponent_tendencies:
                avg_aggression = sum(t.get('aggression', 1.0) for t in opponent_tendencies) / len(opponent_tendencies)
                avg_bluff_freq = sum(t.get('bluff_frequency', 0.2) for t in opponent_tendencies) / len(opponent_tendencies)

                if avg_bluff_freq > 0.3:
                    self.current_hand_strength *= 1.2
                if avg_aggression > 1.2:
                    self.current_hand_strength *= 0.9

            decision, amount = (self._make_easy_decision if self.difficulty == 'easy' else self._make_hard_decision)(
                self.current_hand_strength,
                call_amount,
                pot,
                min_raise,
                max_raise,
                my_chips if self.difficulty == 'easy' else current_bet,
                my_chips
            )

            if self.player_profile:
                self.player_profile.record_action(
                    action=decision,
                    amount=amount,
                    round_name=round_name,
                    position=position,
                    hand_strength=self.current_hand_strength
                )

            return decision, amount

        except Exception as e:
            self.log.exception(f"Error in AI decision making: {e}")
            return ("check", None) if call_amount == 0 else ("fold", None)

    def _adjust_hand_strength(self, base_strength: float, tendencies: Dict, position: str, round_name: str) -> float:
        try:
            adjusted_strength = base_strength

            if position in ['late', 'button']:
                if tendencies['positional_awareness'] > 0.6:
                    adjusted_strength *= 1.1
            elif position in ['early', 'utg']:
                if tendencies['positional_awareness'] < 0.4:
                    adjusted_strength *= 0.9

            if round_name == 'preflop':
                if tendencies['pfr'] > 0.25:
                    adjusted_strength *= 1.1
            else:
                if tendencies['aggression'] > 1.2:
                    adjusted_strength *= 1.05

            if tendencies['win_rate'] > 0.55:
                adjusted_strength *= 1.1
            elif tendencies['win_rate'] < 0.45:
                adjusted_strength *= 0.9

            return min(max(adjusted_strength, 0.0), 1.0)

        except Exception as e:
            self.log.error(f"Error adjusting hand strength: {e}")
            return base_strength

    def _evaluate_hand_strength(self, hole_cards: List) -> float:
        try:
            if not hole_cards or len(hole_cards) != 2:
                return 0.5

            values = [self._card_value_to_number(card.value) for card in hole_cards]
            suited = hole_cards[0].suit == hole_cards[1].suit
            values.sort(reverse=True)

            if values[0] == values[1]:
                pair_strength = 0.6 + (values[0] / 14) * 0.4
                return min(1.0, pair_strength)

            base_strength = (values[0] + values[1]) / 28

            if suited:
                base_strength *= 1.2

            if abs(values[0] - values[1]) == 1:
                base_strength *= 1.1

            if values[0] >= 12:
                base_strength *= 1.1

            gap = values[0] - values[1] - 1
            if gap > 0:
                base_strength *= (1.0 - (gap * 0.05))

            return min(1.0, base_strength)

        except Exception as e:
            self.log.exception(f"Error in hand strength evaluation: {e}")
            return 0.5

    def _make_easy_decision(
            self, hand_strength: float, call_amount: int,
            pot: int, min_raise: int, max_raise: int, my_chips: int
    ) -> Tuple[str, Optional[int]]:
        try:
            if call_amount >= my_chips:
                if hand_strength > 0.7 and my_chips > 0:
                    return "call", None
                return "fold", None

            if call_amount == 0:
                if hand_strength > 0.8 and my_chips >= min_raise:
                    raise_amount = min(min_raise * 2, max_raise, my_chips)
                    return "raise", raise_amount
                return "check", None

            if hand_strength > 0.8:
                if my_chips >= min_raise and self.raise_count < 2:
                    raise_amount = min(min_raise * 2, max_raise, my_chips)
                    self.raise_count += 1
                    return "raise", raise_amount
                return "call", None

            if hand_strength > 0.6:
                pot_odds = call_amount / (pot + call_amount)
                if pot_odds < 0.2 and call_amount < my_chips:
                    return "call", None
                return "fold", None

            if call_amount > my_chips // 4:
                return "fold", None

            if call_amount == 0:
                return "check", None

            return "fold", None

        except Exception as e:
            self.log.exception(f"Error in easy decision making: {e}")
            return ("check", None) if call_amount == 0 else ("fold", None)

    def _make_hard_decision(
            self, hand_strength: float, call_amount: int, pot: int,
            min_raise: int, max_raise: int, current_bet: int, my_chips: int
    ) -> Tuple[str, Optional[int]]:
        try:
            if call_amount >= my_chips:
                if hand_strength > 0.75 and my_chips > 0:
                    return "call", None
                return "fold", None

            if call_amount == 0:
                if hand_strength > 0.7:
                    if my_chips >= min_raise and self.raise_count < 3:
                        raise_amount = min(min_raise * 2, max_raise, my_chips)
                        self.raise_count += 1
                        return "raise", raise_amount
                return "check", None

            pot_odds = call_amount / (pot + call_amount) if pot + call_amount > 0 else 0

            if hand_strength > 0.85:
                if my_chips >= min_raise and self.raise_count < 3:
                    raise_amount = min(current_bet + min_raise * 2, max_raise, my_chips)
                    self.raise_count += 1
                    return "raise", raise_amount
                return "call", None

            if hand_strength > 0.7:
                if pot_odds < 0.25 and my_chips >= min_raise and self.raise_count < 2:
                    raise_amount = min(current_bet + min_raise, max_raise, my_chips)
                    self.raise_count += 1
                    return "raise", raise_amount
                if pot_odds < 0.3 and call_amount < my_chips:
                    return "call", None
                return "fold", None

            if hand_strength > 0.5:
                if pot_odds < 0.2 and call_amount < my_chips // 3:
                    return "call", None
                return "fold", None

            if call_amount == 0:
                return "check", None

            return "fold", None

        except Exception as e:
            self.log.exception(f"Error in hard decision making: {e}")
            return ("check", None) if call_amount == 0 else ("fold", None)

    @staticmethod
    def _card_value_to_number(value: str) -> int:
        value_map = {
            'A': 14, 'K': 13, 'Q': 12, 'J': 11,
            '10': 10, '9': 9, '8': 8, '7': 7,
            '6': 6, '5': 5, '4': 4, '3': 3, '2': 2
        }
        return value_map.get(value, 2)

    def record_hand_result(self, won: bool, profit: int):
        try:
            self.session_stats['hands_played'] += 1
            if won:
                self.session_stats['hands_won'] += 1
            self.session_stats['total_profit'] += profit

            if self.player_profile:
                session_id = f"session_{self.id}"
                history = self.player_profile.session_history[session_id]
                history.total_hands += 1
                if won:
                    history.total_wins += 1
                history.chips_won += profit

        except Exception as e:
            self.log.error(f"Error recording hand result: {e}")

    def reset_for_new_hand(self):
        self.raise_count = 0
        self.current_hand_strength = 0.0
