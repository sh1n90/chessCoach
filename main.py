import logging
import time
from typing import List
from fastapi import FastAPI, HTTPException, Request
from datetime import datetime, timezone
import lichess_client
import analyzer
import weakness
import models

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("chesscoach")

app = FastAPI(title="Chess Weakness OS")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    body = await request.body()
    log.info(">>> %s %s - body: %s", request.method, request.url.path, body.decode()[:500])
    response = await call_next(request)
    elapsed = time.time() - start
    log.info("<<< %s %s -> %d (%.2fs)", request.method, request.url.path, response.status_code, elapsed)
    return response


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/analyze", response_model=models.AnalysisResponse)
def analyze_user(req: models.UserAnalysisRequest):
    username = req.username.strip().lower()
    log.info("=== START analysis for user '%s' (%d games) ===", username, req.game_count)

    t0 = time.time()
    try:
        raw_games = lichess_client.fetch_user_games(username, req.game_count)
    except ValueError as e:
        log.error("User not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error("Failed to fetch games: %s", e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch games: {e}")

    if not raw_games:
        log.warning("No games found for user '%s'", username)
        raise HTTPException(status_code=404, detail=f"No games found for user '{username}'")

    log.info("Fetched %d raw games from Lichess", len(raw_games))

    analyzed = []
    errors = 0

    for i, raw in enumerate(raw_games):
        pgn = raw.get("pgn", "")
        game_id = raw.get("id", "?")
        speed = raw.get("speed", "?")
        if not pgn:
            log.warning("Game %s: no PGN, skipping", game_id)
            continue
        log.info("[%d/%d] Analyzing game %s (%s)...", i + 1, len(raw_games), game_id, speed)
        try:
            result = analyzer.analyze_game(pgn, game_id)
            analyzed.append(result)
            log.info("[%d/%d] Game %s done: %d missed attacks",
                     i + 1, len(raw_games), game_id, len(result.missed_double_attacks))
        except Exception as e:
            errors += 1
            log.error("[%d/%d] Game %s analysis failed: %s", i + 1, len(raw_games), game_id, e)

    summary = weakness.build_summary(analyzed)
    elapsed = time.time() - t0

    log.info("=== FINISHED analysis for '%s': %d games, %d missed attacks, %d errors, %.1fs ===",
             username, len(analyzed), summary.total_double_attacks_missed, errors, elapsed)

    return models.AnalysisResponse(
        username=username,
        games_analyzed=len(analyzed),
        games=analyzed,
        weakness_summary=summary,
    )
