from typing import TypedDict, Optional

DEFAULT_TOURNAMENT_CONFIG = {
    "best_of": 3,
    "deck_check_required": False,
    "seeding_enabled": False,
    "double_elimination": False,
    "extra_deck_limit": 9
}

MIN_PARTICIPANTS = 4

VALID_DIMENSIONS = [
    (1080, 1920),  # Common mobile resolution
    (1920, 1080),  # Landscape mobile
    (2436, 1125),  # iPhone X and similar
    (2688, 1242),  # iPhone XS Max and similar
]

class MatchStatus:
    PENDING = "pending"
    COMPLETED = "completed"
    DQ = "dq"

class DeckInfo(TypedDict):
    main_deck_url: Optional[str]
    side_deck_url: Optional[str]
    extra_deck_url: Optional[str]
    verification_status: str
    verification_notes: Optional[str]
    verified_by: Optional[int]
    verified_at: Optional[str]

class ParticipantInfo(TypedDict):
    deck_info: Optional[DeckInfo]
    wins: int
    losses: int
    seed: int
    registration_time: str
    dq_info: Optional[dict]

class MatchInfo(TypedDict):
    player1: int
    player2: int
    score: Optional[str]
    round: int
    winner: Optional[int]
    loser: Optional[int]
    status: str

class VerificationStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

ERROR_MESSAGES = {
    "NO_TOURNAMENT_ROLE": "Tournament role has not been set. An admin must use `/set_tournament_role` first.",
    "NO_MODERATOR": "At least one moderator with tournament role is required to facilitate the tournament.",
    "INSUFFICIENT_PARTICIPANTS": lambda count: f"Not enough participants (minimum {MIN_PARTICIPANTS}, current: {count})",
    "TOURNAMENT_IN_PROGRESS": "A tournament is already in progress!",
    "REGISTRATION_CLOSED": "Registration is currently closed!",
    "ALREADY_REGISTERED": "You are already registered!",
    "DECK_REQUIRED": "Deck screenshots are required for this tournament! Please provide your deck images.",
    "NO_MATCH_FOUND": "No active match found between you and this opponent.",
    "INVALID_SCORE": lambda best_of: f"Invalid score. This is a best of {best_of} match."
}

ROUND_MESSAGES = {
    "COMPLETE": lambda round_num: f"Round {round_num} complete! Starting Round {round_num + 1}...",
    "TOURNAMENT_COMPLETE": "🏆 Tournament Complete! 🏆"
}
