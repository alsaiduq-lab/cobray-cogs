from typing import TypedDict, Optional

DEFAULT_TOURNAMENT_CONFIG = {
    "best_of": 3,
    "deck_check_required": False,
    "seeding_enabled": False,
    "tournament_mode": "single_elimination",  # single_elimination, double_elimination, swiss, round_robin
    "extra_deck_limit": 9,
    "match_timeout_minutes": 30,  # Time limit for matches
    "require_confirmation": True,  # Require both players to confirm match results
    "automatic_dq": True,  # Automatically DQ players who don't report in time
    "rounds_swiss": 3,      # Number of Swiss rounds before top cut
    "top_cut": 8,           # Number of players advancing to elimination bracket
    "allow_draws": False,   # Whether draws are allowed in matches
    "send_announcements": True,  # Whether to send announcements to announcement channel
    "send_reminders": True,  # Whether to send match reminders to players
    "reminder_minutes": 15   # How many minutes before match to send reminder
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
    DRAW = "draw"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    
class TournamentMode:
    SINGLE_ELIMINATION = "single_elimination"
    DOUBLE_ELIMINATION = "double_elimination" 
    SWISS = "swiss"
    ROUND_ROBIN = "round_robin"

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
    draws: int
    match_points: int      # Used for Swiss and Round Robin
    tiebreaker_points: int  # Used for tiebreakers
    seed: int
    registration_time: str
    dq_info: Optional[dict]
    active: bool            # Whether player is still in tournament

class MatchInfo(TypedDict):
    player1: int
    player2: int
    score: Optional[str]
    round: int
    bracket: str             # 'winners', 'losers', 'swiss', etc.
    winner: Optional[int]
    loser: Optional[int]
    status: str
    scheduled_time: Optional[str]
    completed_time: Optional[str]
    reported_by: Optional[int]
    confirmed_by: Optional[int]

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
    "INVALID_SCORE": lambda best_of: f"Invalid score. This is a best of {best_of} match.",
    "NOT_AUTHORIZED": "You are not authorized to perform this action.",
    "TOURNAMENT_NOT_STARTED": "No tournament is currently in progress!",
    "MATCH_REQUIRES_CONFIRMATION": "This match result needs to be confirmed by your opponent.",
    "DRAWS_NOT_ALLOWED": "Draws are not allowed in this tournament format.",
    "INVALID_TOURNAMENT_MODE": "Invalid tournament mode specified. Valid modes are: single_elimination, double_elimination, swiss, round_robin",
    "ALREADY_REPORTED": "This match result has already been reported. Waiting for confirmation.",
    "PLAYER_INACTIVE": "This player is no longer active in the tournament."
}

ROUND_MESSAGES = {
    "COMPLETE": lambda round_num: f"Round {round_num} complete! Starting Round {round_num + 1}...",
    "SWISS_COMPLETE": lambda top_cut: f"Swiss rounds complete! Top {top_cut} advancing to elimination bracket.",
    "TOURNAMENT_COMPLETE": "🏆 Tournament Complete! 🏆",
    "MATCH_SCHEDULED": lambda p1, p2, time: f"Match scheduled: {p1.mention} vs {p2.mention} at {time}",
    "MATCH_REMINDER": lambda p1, p2: f"Reminder: {p1.mention} vs {p2.mention} match is due soon!",
    "MATCH_TIMEOUT_WARNING": lambda p1, p2: f"Warning: {p1.mention} vs {p2.mention} match is about to time out!"
}
