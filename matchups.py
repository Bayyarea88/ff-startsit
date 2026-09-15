"""Defense vs position (Half-PPR points allowed) + weekly opponents."""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{year}.csv"
)
GAMES_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
)

SKILL = {"QB", "RB", "WR", "TE"}


def _get_csv(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))


def load_weekly_stats(years: list[int]) -> pd.DataFrame:
    frames = []
    for year in years:
        try:
            df = _get_csv(STATS_URL.format(year=year))
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "season_type" in out.columns:
        out = out[out["season_type"].fillna("REG").isin(["REG", "regular", "Regular"])]
    out = out[out["position"].isin(SKILL)].copy()
    rec = out["receptions"].fillna(0) if "receptions" in out.columns else 0
    std = out["fantasy_points"].fillna(0) if "fantasy_points" in out.columns else 0
    out["half_ppr"] = std + 0.5 * rec
    return out


def defense_vs_position(weekly: pd.DataFrame, current_season: int, current_week: int) -> pd.DataFrame:
    """
    Half-PPR fantasy points allowed per game by defense, by position.

    Early season (fewer than 4 current-season games): blend last year 70% + current 30%.
    After week 4: use current season only.
    """
    if weekly.empty:
        return pd.DataFrame()

    needed = {"opponent_team", "position", "half_ppr", "season", "week"}
    if not needed.issubset(weekly.columns):
        return pd.DataFrame()

    cur = weekly[(weekly["season"] == current_season) & (weekly["week"] < current_week)]
    prev = weekly[weekly["season"] == current_season - 1]

    def _agg(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["defense", "position", "pts_allowed", "games"])
        g = (
            df.groupby(["opponent_team", "position"], as_index=False)
            .agg(pts_allowed=("half_ppr", "sum"), games=("week", "nunique"))
        )
        g["pts_allowed"] = g["pts_allowed"] / g["games"].clip(lower=1)
        return g.rename(columns={"opponent_team": "defense"})

    cur_agg = _agg(cur)
    prev_agg = _agg(prev)
    games_played = int(cur["week"].nunique()) if not cur.empty else 0

    if games_played >= 4 and not cur_agg.empty:
        used = cur_agg
    elif not prev_agg.empty and not cur_agg.empty:
        merged = prev_agg.merge(
            cur_agg, on=["defense", "position"], how="outer", suffixes=("_prev", "_cur")
        )
        merged["pts_allowed"] = (
            0.7 * merged["pts_allowed_prev"].fillna(merged["pts_allowed_cur"])
            + 0.3 * merged["pts_allowed_cur"].fillna(merged["pts_allowed_prev"])
        )
        merged["games"] = merged["games_cur"].fillna(0) + merged["games_prev"].fillna(0)
        used = merged[["defense", "position", "pts_allowed", "games"]]
    elif not cur_agg.empty:
        used = cur_agg
    else:
        used = prev_agg

    if used.empty:
        return used

    used["league_avg"] = used.groupby("position")["pts_allowed"].transform("mean")
    used["multiplier"] = (used["pts_allowed"] / used["league_avg"]).clip(0.80, 1.20)
    # Rank 1 = toughest (fewest points allowed)
    used["rank"] = used.groupby("position")["pts_allowed"].rank(method="min", ascending=True)
    used["rank"] = used["rank"].astype(int)
    return used


def load_schedule(season: int) -> pd.DataFrame:
    games = _get_csv(GAMES_URL)
    games = games[(games["season"] == season) & (games["game_type"] == "REG")].copy()
    home = games[["week", "home_team", "away_team"]].rename(
        columns={"home_team": "team", "away_team": "opponent"}
    )
    home["home"] = True
    away = games[["week", "away_team", "home_team"]].rename(
        columns={"away_team": "team", "home_team": "opponent"}
    )
    away["home"] = False
    return pd.concat([home, away], ignore_index=True)


def opponent_for(schedule: pd.DataFrame, team: str, week: int) -> tuple[str | None, bool | None]:
    if schedule.empty or not team:
        return None, None
    hit = schedule[(schedule["team"] == team) & (schedule["week"] == week)]
    if hit.empty:
        return None, None
    row = hit.iloc[0]
    return str(row["opponent"]), bool(row["home"])


def matchup_row(dvp: pd.DataFrame, defense: str | None, position: str) -> dict:
    empty = {
        "opp": defense or "",
        "dvp_pts": None,
        "dvp_rank": None,
        "mult": 1.0,
        "matchup": "",
    }
    if dvp.empty or not defense:
        return empty
    hit = dvp[(dvp["defense"] == defense) & (dvp["position"] == position)]
    if hit.empty:
        empty["opp"] = defense
        return empty
    row = hit.iloc[0]
    rank = int(row["rank"])
    pts = float(row["pts_allowed"])
    mult = float(row["multiplier"])
    if rank <= 8:
        grade = "Tough"
    elif rank >= 25:
        grade = "Easy"
    else:
        grade = "Avg"
    return {
        "opp": defense,
        "dvp_pts": round(pts, 1),
        "dvp_rank": rank,
        "mult": round(mult, 3),
        "matchup": f"{grade} ({rank}/32)",
    }
