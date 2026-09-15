"""Sleeper data helpers: NFL state, players, weekly projections, rosters."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import requests

SLEEPER_APP = "https://api.sleeper.app/v1"
SLEEPER_PROJECTIONS = "https://api.sleeper.com"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Half-PPR is the default scoring for this project.
SCORING_KEY = "pts_half_ppr"


def _get(url: str, *, params: dict | None = None, browser: bool = False) -> Any:
    headers = {"User-Agent": BROWSER_UA} if browser else {"User-Agent": "ff-startsit/1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_nfl_state() -> dict:
    return _get(f"{SLEEPER_APP}/state/nfl")


@lru_cache(maxsize=1)
def get_players() -> dict[str, dict]:
    """Full NFL player map. Cache in-process; call once per session."""
    return _get(f"{SLEEPER_APP}/players/nfl")


def get_user(username: str) -> dict:
    return _get(f"{SLEEPER_APP}/user/{username}")


def get_user_leagues(user_id: str, season: str) -> list[dict]:
    return _get(f"{SLEEPER_APP}/user/{user_id}/leagues/nfl/{season}")


def get_rosters(league_id: str) -> list[dict]:
    return _get(f"{SLEEPER_APP}/league/{league_id}/rosters")


def get_league_users(league_id: str) -> list[dict]:
    return _get(f"{SLEEPER_APP}/league/{league_id}/users")


def get_weekly_projections(season: int | str, week: int) -> dict[str, dict]:
    """
    Undocumented Sleeper projections host.
    Returns a dict keyed by player_id when possible.
    """
    url = f"{SLEEPER_PROJECTIONS}/projections/nfl/{season}/{week}"
    raw = _get(url, params={"season_type": "regular"}, browser=True)

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        out: dict[str, dict] = {}
        for row in raw:
            pid = str(row.get("player_id") or row.get("playerId") or "")
            if pid:
                stats = row.get("stats") or row
                out[pid] = stats if isinstance(stats, dict) else row
        return out
    return {}


def projected_half_ppr(proj: dict) -> float:
    if not proj:
        return 0.0
    if SCORING_KEY in proj and proj[SCORING_KEY] is not None:
        return float(proj[SCORING_KEY])
    # Fallback: compute half-PPR from raw projected counting stats.
    rec = float(proj.get("rec") or 0)
    rec_yd = float(proj.get("rec_yd") or 0)
    rec_td = float(proj.get("rec_td") or 0)
    rush_yd = float(proj.get("rush_yd") or 0)
    rush_td = float(proj.get("rush_td") or 0)
    pass_yd = float(proj.get("pass_yd") or 0)
    pass_td = float(proj.get("pass_td") or 0)
    ints = float(proj.get("pass_int") or 0)
    fum = float(proj.get("fum_lost") or proj.get("fum") or 0)
    return (
        rec * 0.5
        + rec_yd * 0.1
        + rec_td * 6
        + rush_yd * 0.1
        + rush_td * 6
        + pass_yd * 0.04
        + pass_td * 4
        - ints * 2
        - fum * 2
    )


def availability_factor(player: dict) -> float:
    status = (player.get("injury_status") or player.get("status") or "").lower()
    if status in {"out", "ir", "pup", "suspended", "covid-19"}:
        return 0.0
    if status in {"doubtful"}:
        return 0.25
    if status in {"questionable"}:
        return 0.80
    return 1.0


def display_name(player: dict) -> str:
    full = player.get("full_name")
    if full:
        return full
    first = player.get("first_name") or ""
    last = player.get("last_name") or ""
    return f"{first} {last}".strip() or "Unknown"


def find_my_sleeper_roster(username: str, league_id: str) -> list[str]:
    user = get_user(username)
    user_id = user.get("user_id")
    for roster in get_rosters(league_id):
        if str(roster.get("owner_id")) == str(user_id):
            return [str(p) for p in (roster.get("players") or [])]
    return []
