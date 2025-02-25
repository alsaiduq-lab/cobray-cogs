from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import uuid

from ..utils.constants import (
    DEFAULT_TOURNAMENT_CONFIG,
    MatchStatus,
    TournamentMode,
    VerificationStatus
)


class DeckInfo:
    """Represents player's deck information"""
    def __init__(
        self,
        main_deck_url: Optional[str] = None,
        extra_deck_url: Optional[str] = None,
        side_deck_url: Optional[str] = None,
        verification_status: str = VerificationStatus.PENDING,
        verification_notes: Optional[str] = None,
        verified_by: Optional[int] = None,
        verified_at: Optional[str] = None
    ):
        self.main_deck_url = main_deck_url
        self.extra_deck_url = extra_deck_url
        self.side_deck_url = side_deck_url
        self.verification_status = verification_status
        self.verification_notes = verification_notes
        self.verified_by = verified_by
        self.verified_at = verified_at
    def to_dict(self) -> Dict[str, Any]:
        """Convert DeckInfo to dictionary"""
        return {
            "main_deck_url": self.main_deck_url,
            "extra_deck_url": self.extra_deck_url,
            "side_deck_url": self.side_deck_url,
            "verification_status": self.verification_status,
            "verification_notes": self.verification_notes,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at
        }
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeckInfo':
        """Create DeckInfo from dictionary"""
        return cls(
            main_deck_url=data.get("main_deck_url"),
            extra_deck_url=data.get("extra_deck_url"),
            side_deck_url=data.get("side_deck_url"),
            verification_status=data.get("verification_status", VerificationStatus.PENDING),
            verification_notes=data.get("verification_notes"),
            verified_by=data.get("verified_by"),
            verified_at=data.get("verified_at")
        )


class Participant:
    """Represents a tournament participant"""
    def __init__(
        self,
        user_id: int,
        deck_info: Optional[DeckInfo] = None,
        wins: int = 0,
        losses: int = 0,
        draws: int = 0,
        match_points: int = 0,
        tiebreaker_points: float = 0.0,
        seed: int = 0,
        registration_time: Optional[str] = None,
        dq_info: Optional[Dict[str, Any]] = None,
        active: bool = True
    ):
        self.user_id = user_id
        self.deck_info = deck_info
        self.wins = wins
        self.losses = losses
        self.draws = draws
        self.match_points = match_points
        self.tiebreaker_points = tiebreaker_points
        self.seed = seed
        self.registration_time = registration_time or datetime.now().isoformat()
        self.dq_info = dq_info
        self.active = active
    def to_dict(self) -> Dict[str, Any]:
        """Convert Participant to dictionary"""
        return {
            "deck_info": self.deck_info.to_dict() if self.deck_info else None,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "match_points": self.match_points,
            "tiebreaker_points": self.tiebreaker_points,
            "seed": self.seed,
            "registration_time": self.registration_time,
            "dq_info": self.dq_info,
            "active": self.active
        }
    @classmethod
    def from_dict(cls, user_id: int, data: Dict[str, Any]) -> 'Participant':
        """Create Participant from dictionary"""
        deck_info = None
        if data.get("deck_info"):
            deck_info = DeckInfo.from_dict(data["deck_info"])
        return cls(
            user_id=user_id,
            deck_info=deck_info,
            wins=data.get("wins", 0),
            losses=data.get("losses", 0),
            draws=data.get("draws", 0),
            match_points=data.get("match_points", 0),
            tiebreaker_points=data.get("tiebreaker_points", 0.0),
            seed=data.get("seed", 0),
            registration_time=data.get("registration_time"),
            dq_info=data.get("dq_info"),
            active=data.get("active", True)
        )


class Match:
    """Represents a tournament match"""
    def __init__(
        self,
        match_id: int,
        player1: int,
        player2: int,
        round_num: int,
        bracket: str,
        score: Optional[str] = None,
        winner: Optional[int] = None,
        loser: Optional[int] = None,
        status: str = MatchStatus.PENDING,
        scheduled_time: Optional[str] = None,
        completed_time: Optional[str] = None,
        reported_by: Optional[int] = None,
        confirmed_by: Optional[int] = None
    ):
        self.match_id = match_id
        self.player1 = player1
        self.player2 = player2
        self.round_num = round_num
        self.bracket = bracket
        self.score = score
        self.winner = winner
        self.loser = loser
        self.status = status
        self.scheduled_time = scheduled_time or datetime.now().isoformat()
        self.completed_time = completed_time
        self.reported_by = reported_by
        self.confirmed_by = confirmed_by
    def to_dict(self) -> Dict[str, Any]:
        """Convert Match to dictionary"""
        return {
            "player1": self.player1,
            "player2": self.player2,
            "score": self.score,
            "round": self.round_num,
            "bracket": self.bracket,
            "winner": self.winner,
            "loser": self.loser,
            "status": self.status,
            "scheduled_time": self.scheduled_time,
            "completed_time": self.completed_time,
            "reported_by": self.reported_by,
            "confirmed_by": self.confirmed_by
        }
    @classmethod
    def from_dict(cls, match_id: int, data: Dict[str, Any]) -> 'Match':
        """Create Match from dictionary"""
        return cls(
            match_id=match_id,
            player1=data.get("player1"),
            player2=data.get("player2"),
            round_num=data.get("round"),
            bracket=data.get("bracket"),
            score=data.get("score"),
            winner=data.get("winner"),
            loser=data.get("loser"),
            status=data.get("status", MatchStatus.PENDING),
            scheduled_time=data.get("scheduled_time"),
            completed_time=data.get("completed_time"),
            reported_by=data.get("reported_by"),
            confirmed_by=data.get("confirmed_by")
        )


class Tournament:
    """Represents a tournament with all its data"""
    def __init__(
        self,
        name: str,
        description: str = "",
        guild_id: Optional[int] = None,
        created_by: Optional[int] = None,
        tournament_mode: str = TournamentMode.SINGLE_ELIMINATION,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        self.name = name
        self.description = description
        self.guild_id = guild_id
        self.config = DEFAULT_TOURNAMENT_CONFIG.copy()
        if config:
            self.config.update(config)
        for key in DEFAULT_TOURNAMENT_CONFIG:
            if key in kwargs:
                self.config[key] = kwargs[key]
        self.config["tournament_mode"] = tournament_mode
        self.is_started = False
        self.registration_open = False
        self.current_round = 1
        self.participants: Dict[int, Participant] = {}
        self.matches: Dict[int, Match] = {}
        self.meta = {
            "id": str(uuid.uuid4()),
            "name": name,
            "description": description,
            "start_time": None,
            "end_time": None,
            "current_phase": "registration",
            "created_by": created_by,
            "current_match_id": 1,
            "guild_id": guild_id,
            "scheduled_matches": {},
            "reminder_tasks": {}
        }
    def to_dict(self) -> Dict[str, Any]:
        """Convert Tournament to dictionary"""
        participants_dict = {}
        for user_id, participant in self.participants.items():
            participants_dict[str(user_id)] = participant.to_dict()
        matches_dict = {}
        for match_id, match in self.matches.items():
            matches_dict[str(match_id)] = match.to_dict()
        return {
            "tournament_config": self.config,
            "tournament_meta": self.meta,
            "tournament_started": self.is_started,
            "registration_open": self.registration_open,
            "current_round": self.current_round,
            "participants": participants_dict,
            "matches": matches_dict
        }
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Tournament':
        """Create Tournament from dictionary"""
        meta = data.get("tournament_meta", {})
        tournament = cls(
            name=meta.get("name", "Tournament"),
            description=meta.get("description", ""),
            guild_id=meta.get("guild_id"),
            created_by=meta.get("created_by"),
            config=data.get("tournament_config")
        )
        tournament.is_started = data.get("tournament_started", False)
        tournament.registration_open = data.get("registration_open", False)
        tournament.current_round = data.get("current_round", 1)
        tournament.meta = meta
        participants_dict = data.get("participants", {})
        for user_id_str, participant_data in participants_dict.items():
            user_id = int(user_id_str)
            tournament.participants[user_id] = Participant.from_dict(user_id, participant_data)
        matches_dict = data.get("matches", {})
        for match_id_str, match_data in matches_dict.items():
            match_id = int(match_id_str)
            tournament.matches[match_id] = Match.from_dict(match_id, match_data)
        return tournament
    def get_active_participants(self) -> List[Participant]:
        """Get list of active participants"""
        return [p for p in self.participants.values() if p.active]
    def get_current_round_matches(self) -> List[Match]:
        """Get matches for the current round"""
        return [m for m in self.matches.values() if m.round_num == self.current_round]
    def calculate_tournament_duration(self) -> str:
        """Calculate the duration of the tournament"""
        if not self.meta.get("start_time") or not self.meta.get("end_time"):
            return "Unknown"
        start_time = datetime.fromisoformat(self.meta["start_time"])
        end_time = datetime.fromisoformat(self.meta["end_time"])
        duration = end_time - start_time
        hours, remainder = divmod(duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
