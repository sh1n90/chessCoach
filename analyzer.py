import chess
import chess.engine
import chess.pgn
import io
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import config
import models

log = logging.getLogger("chesscoach.analyzer")


PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 100,
}


def _has_double_attack(board: chess.Board) -> Optional[Dict[str, Any]]:
    side = board.turn
    targets = []
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece and piece.color == side:
            attackers = board.attackers(not side, sq)
            if len(attackers) >= 2:
                targets.append({
                    "square": chess.square_name(sq),
                    "piece": piece.symbol().upper(),
                    "defended": len(board.attackers(side, sq)) > 0,
                    "value": PIECE_VALUES.get(piece.piece_type, 0),
                    "attackers": attackers,
                })
    if len(targets) < 2:
        return None

    for t in targets:
        if not t["defended"]:
            return {
                "squares": [t["square"] for t in targets],
                "victim_pieces": list(set(t["piece"] for t in targets)),
                "description": f"Double attacks {', '.join(t['square'] for t in targets)} "
                               f"(targeting {', '.join(t['piece'] for t in targets)})",
            }

    for t in targets:
        for attacker_sq in t["attackers"]:
            attacker = board.piece_at(attacker_sq)
            if attacker is None:
                continue
            attacker_val = PIECE_VALUES.get(attacker.piece_type, 0)
            if attacker_val < t["value"]:
                return {
                    "squares": [t["square"] for t in targets],
                    "victim_pieces": list(set(t["piece"] for t in targets)),
                    "description": f"Double attacks {', '.join(t['square'] for t in targets)} "
                                   f"(targeting {', '.join(t['piece'] for t in targets)})",
                }

    return None


def analyze_game(pgn: str, game_id: str) -> models.GameAnalysis:
    log.info("=== Analyzing game %s ===", game_id)

    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        log.error("Game %s: invalid PGN", game_id)
        raise ValueError("Invalid PGN")

    headers = game.headers
    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    date = headers.get("Date", "?")
    opening = headers.get("Opening", headers.get("ECO", "?"))
    result = headers.get("Result", "*")
    log.info("Game %s: %s vs %s | %s | opening: %s", game_id, white, black, result, opening)

    board = game.board()
    log.info("Starting Stockfish engine...")
    engine = chess.engine.SimpleEngine.popen_uci(config.STOCKFISH_PATH)
    log.info("Stockfish ready")

    missed = []
    ply = 0

    def _score(entry):
        sf = entry.get("score")
        if sf is None:
            return None
        rel = sf.relative
        if rel.is_mate():
            sign = 1 if rel.mate() > 0 else -1
            return sign * (10000 - abs(rel.mate()) * 100)
        return rel.score()

    node = game
    while node.variations:
        node = node.variations[0]
        ply += 1
        move = node.move
        if move is None:
            continue

        turn = board.turn
        player = "white" if turn == chess.WHITE else "black"
        full_move = (ply + 1) // 2
        move_label = f"{full_move}." if turn == chess.WHITE else f"{full_move}..."
        fen_before = board.fen()
        played_san = board.san(move)

        if ply % 10 == 0:
            log.info("Game %s: analyzing ply %d (%s played %s)...",
                     game_id, ply, player, played_san)

        try:
            analysis = engine.analyse(
                board,
                chess.engine.Limit(depth=config.STOCKFISH_DEPTH),
                multipv=config.STOCKFISH_MULTIPV,
            )
        except Exception as e:
            log.warning("Game %s: Stockfish analysis failed at ply %d: %s", game_id, ply, e)
            board.push(move)
            continue

        best_entry = analysis[0] if analysis else None
        best_score = _score(best_entry) if best_entry else None
        best_move = best_entry.get("pv", [None])[0] if best_entry else None

        for pv_entry in analysis:
            pv = pv_entry.get("pv", [])
            if not pv:
                continue
            candidate = pv[0]
            if candidate == move:
                continue

            if candidate != best_move:
                continue

            if not board.is_legal(candidate):
                continue

            board_copy = board.copy()
            board_copy.push(candidate)
            missed_after_fen = board_copy.fen()
            attack_info = _has_double_attack(board_copy)
            if attack_info is not None:
                attacker = board.piece_at(candidate.from_square)
                missed_move_san = board.san(candidate)
                log.info(">>> MISSED DOUBLE ATTACK at %s (%s): played %s, missed %s (best move) -> %s",
                         move_label, player, played_san, missed_move_san, attack_info["description"])
                missed.append(models.MissedDoubleAttack(
                    move_number=full_move,
                    player=player,
                    fen_before=fen_before,
                    fen_after=missed_after_fen,
                    played_move=played_san,
                    missed_move=missed_move_san,
                    missed_move_san=missed_move_san,
                    description=attack_info["description"],
                    victim_piece=", ".join(attack_info["victim_pieces"]),
                    attacker_piece=attacker.symbol().upper() if attacker else "?",
                    squares_attacked=attack_info["squares"],
                ))
                break

        board.push(move)

    engine.quit()
    log.info("Game %s done: %d plies analyzed, %d missed double attacks found",
             game_id, ply, len(missed))

    return models.GameAnalysis(
        game_id=game_id,
        white=white,
        black=black,
        result=result,
        date=date,
        opening=opening,
        missed_double_attacks=missed,
        total_moves=ply,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )
