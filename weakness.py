import logging
from collections import Counter
from typing import List
import models

log = logging.getLogger("chesscoach.weakness")


def build_summary(games: List[models.GameAnalysis]) -> models.WeaknessSummary:
    log.info("Building weakness summary from %d games", len(games))
    total_missed = 0
    by_piece = Counter()
    by_phase = Counter()

    piece_victims = Counter()

    for g in games:
        for attack in g.missed_double_attacks:
            total_missed += 1
            by_piece[attack.attacker_piece] += 1
            for vp in attack.victim_piece.split(", "):
                piece_victims[vp.strip()] += 1
            if attack.move_number <= 15:
                by_phase["opening"] += 1
            elif attack.move_number <= 40:
                by_phase["middlegame"] += 1
            else:
                by_phase["endgame"] += 1

    log.info("Summary: %d total missed attacks across %d games", total_missed, len(games))
    log.info("By piece type: %s", dict(by_piece.most_common()))
    log.info("By game phase: %s", dict(by_phase.most_common()))

    return models.WeaknessSummary(
        total_double_attacks_missed=total_missed,
        by_piece_type=dict(by_piece.most_common()),
        by_game_phase=dict(by_phase.most_common()),
        most_common_victim_pieces=piece_victims.most_common(5),
        total_games_analyzed=len(games),
    )
