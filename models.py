from pydantic import BaseModel
from typing import Optional, List, Dict, Tuple


class MissedDoubleAttack(BaseModel):
    move_number: int
    player: str
    fen_before: str
    fen_after: str
    played_move: str
    missed_move: str
    missed_move_san: str
    description: str
    victim_piece: str
    attacker_piece: str
    squares_attacked: List[str]


class GameAnalysis(BaseModel):
    game_id: str
    white: str
    black: str
    result: str
    date: str
    opening: str
    missed_double_attacks: List["MissedDoubleAttack"]
    total_moves: int
    analyzed_at: str


class WeaknessSummary(BaseModel):
    total_double_attacks_missed: int
    by_piece_type: Dict[str, int]
    by_game_phase: Dict[str, int]
    most_common_victim_pieces: List[Tuple[str, int]]
    total_games_analyzed: int


class UserAnalysisRequest(BaseModel):
    username: str
    game_count: int = 100


class AnalysisResponse(BaseModel):
    username: str
    games_analyzed: int
    games: List[GameAnalysis]
    weakness_summary: WeaknessSummary
