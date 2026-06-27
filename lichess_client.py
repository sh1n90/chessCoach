import json
import logging
from typing import List, Dict, Any
import requests
import config

log = logging.getLogger("chesscoach.lichess")


def fetch_user_games(username: str, max_games: int = 100) -> List[Dict[str, Any]]:
    log.info("Fetching up to %d games for user '%s' from Lichess", max_games, username)
    games = []
    page = 1
    while len(games) < max_games:
        batch_size = min(50, max_games - len(games))
        params = {
            "max": batch_size,
            "page": page,
            "moves": True,
            "pgnInJson": True,
        }
        log.debug("Requesting page %d (batch_size=%d) from Lichess API", page, batch_size)
        resp = requests.get(
            f"{config.LICHESS_API_BASE}/games/user/{username}",
            params=params,
            headers={"Accept": "application/x-ndjson"},
            timeout=30,
        )
        if resp.status_code == 404:
            log.warning("User '%s' not found on Lichess", username)
            raise ValueError(f"User '{username}' not found on Lichess")
        resp.raise_for_status()
        if not resp.text.strip():
            log.info("No more games available (empty response)")
            break
        lines = [l for l in resp.text.strip().split("\n") if l.strip()]
        if not lines:
            break
        batch = [json.loads(l) for l in lines]
        games.extend(batch)
        log.info("Fetched %d games from page %d (total so far: %d)", len(batch), page, len(games))
        page += 1

    log.info("Done fetching. Total games retrieved: %d", len(games))
    return games[:max_games]
