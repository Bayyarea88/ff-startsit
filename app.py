"""Half-PPR start/sit board for Sleeper + ESPN leagues."""

from __future__ import annotations

import statistics
from collections import defaultdict

import pandas as pd
import streamlit as st

from data.espn import load_espn_roster_names, match_espn_to_sleeper
from data.matchups import (
    defense_vs_position,
    load_schedule,
    load_weekly_stats,
    matchup_row,
    opponent_for,
)
from data.sleeper import (
    availability_factor,
    display_name,
    find_my_sleeper_roster,
    get_nfl_state,
    get_players,
    get_user,
    get_user_leagues,
    get_weekly_projections,
    projected_half_ppr,
)
from model.recommend import label_from_points

SKILL_POS = {"QB", "RB", "WR", "TE"}


@st.cache_data(ttl=6 * 3600)
def cached_players() -> dict:
    return get_players()


@st.cache_data(ttl=3600)
def cached_state() -> dict:
    return get_nfl_state()


@st.cache_data(ttl=1800)
def cached_projections(season: str, week: int) -> dict:
    return get_weekly_projections(season, week)


@st.cache_data(ttl=3600)
def cached_leagues(username: str, season: str) -> list[dict]:
    user = get_user(username)
    return get_user_leagues(user["user_id"], season)


@st.cache_data(ttl=6 * 3600)
def cached_weekly_stats(years: tuple[int, ...]) -> pd.DataFrame:
    return load_weekly_stats(list(years))


@st.cache_data(ttl=6 * 3600)
def cached_schedule(season: int) -> pd.DataFrame:
    return load_schedule(season)


@st.cache_data(ttl=3600)
def cached_dvp(years: tuple[int, ...], season: int, week: int) -> pd.DataFrame:
    return defense_vs_position(cached_weekly_stats(years), season, week)


def build_board(
    week: int,
    season: str,
    positions: list[str],
    roster_ids: set[str] | None,
    schedule: pd.DataFrame,
    dvp: pd.DataFrame,
) -> pd.DataFrame:
    players = cached_players()
    projs = cached_projections(season, week)
    rows = []
    for pid, proj in projs.items():
        p = players.get(pid) or {}
        pos = p.get("position")
        if pos not in positions:
            continue
        if roster_ids is not None and pid not in roster_ids:
            continue
        if p.get("active") is False:
            continue
        base = projected_half_ppr(proj) * availability_factor(p)
        team = p.get("team") or ""
        opp, home = opponent_for(schedule, team, week)
        mu = matchup_row(dvp, opp, pos)
        adj = base * mu["mult"]
        loc = ""
        if opp:
            loc = f"{'vs' if home else '@'} {opp}"
        rows.append(
            {
                "player_id": pid,
                "player": display_name(p),
                "pos": pos,
                "nfl_team": team,
                "opp": loc,
                "injury": p.get("injury_status") or "",
                "base": round(base, 2),
                "mult": mu["mult"],
                "proj": round(adj, 2),
                "dvp_rank": mu["dvp_rank"],
                "dvp_pts": mu["dvp_pts"],
                "matchup": mu["matchup"],
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    medians: dict[str, float] = {}
    for pos, grp in df.groupby("pos"):
        vals = grp["proj"].tolist()
        medians[pos] = statistics.median(vals) if vals else 0.0

    df["vs_pos"] = df.apply(lambda r: round(r["proj"] - medians.get(r["pos"], 0), 2), axis=1)
    df["call"] = df.apply(lambda r: label_from_points(r["proj"], medians.get(r["pos"], 0)), axis=1)
    return df.sort_values(["pos", "proj"], ascending=[True, False]).reset_index(drop=True)


def multiweek_strip(
    player_ids: list[str],
    season: str,
    start_week: int,
    n_weeks: int,
    schedule: pd.DataFrame,
    dvp: pd.DataFrame,
) -> pd.DataFrame:
    players = cached_players()
    data = defaultdict(dict)
    for w in range(start_week, start_week + n_weeks):
        projs = cached_projections(season, w)
        for pid in player_ids:
            p = players.get(pid) or {}
            pos = p.get("position")
            team = p.get("team") or ""
            base = projected_half_ppr(projs.get(pid) or {}) * availability_factor(p)
            opp, home = opponent_for(schedule, team, w)
            mu = matchup_row(dvp, opp, pos)
            adj = round(base * mu["mult"], 1)
            tag = ""
            if opp:
                prefix = "vs" if home else "@"
                tag = f" {prefix}{opp}"
                if mu["dvp_rank"]:
                    tag += f" ({mu['dvp_rank']})"
            data[pid][f"W{w}"] = f"{adj}{tag}"
            data[pid]["player"] = display_name(p)
            data[pid]["pos"] = pos
    return pd.DataFrame.from_dict(data, orient="index").reset_index(names="player_id")


st.set_page_config(page_title="Half-PPR Start/Sit", layout="wide")
st.title("Half-PPR Start / Sit")
st.caption("Sleeper projections × defense-vs-position, optional Sleeper/ESPN roster filter.")

state = cached_state()
season = str(state.get("season") or "2026")
default_week = int(state.get("week") or 1)

with st.sidebar:
    st.header("Settings")
    week = st.number_input("NFL week", min_value=1, max_value=18, value=min(max(default_week, 1), 18))
    positions = st.multiselect("Positions", ["QB", "RB", "WR", "TE"], default=["QB", "RB", "WR", "TE"])
    look_ahead = st.slider("Upcoming weeks to show", 1, 4, 3)

    st.subheader("Sleeper roster (optional)")
    sleeper_user = st.text_input("Sleeper username")
    sleeper_league_id = ""
    if sleeper_user:
        try:
            leagues = cached_leagues(sleeper_user.strip(), season)
            names = {f"{lg.get('name')} ({lg.get('league_id')})": lg.get("league_id") for lg in leagues}
            if names:
                choice = st.selectbox("Sleeper league", list(names))
                sleeper_league_id = names[choice]
            else:
                st.info("No Sleeper NFL leagues found for that user this season.")
        except Exception as exc:
            st.error(f"Sleeper lookup failed: {exc}")

    st.subheader("ESPN roster (optional)")
    espn_league_id = st.text_input("ESPN league ID")
    espn_team = st.text_input("Your ESPN team name")
    espn_s2 = st.text_input("espn_s2 cookie (private league)", type="password")
    swid = st.text_input("SWID cookie (private league)")

roster_ids: set[str] | None = None
if sleeper_user and sleeper_league_id:
    try:
        roster_ids = set(find_my_sleeper_roster(sleeper_user.strip(), sleeper_league_id))
        st.success(f"Loaded {len(roster_ids)} Sleeper roster players")
    except Exception as exc:
        st.error(f"Could not load Sleeper roster: {exc}")

if espn_league_id:
    try:
        espn_rows = load_espn_roster_names(
            league_id=int(espn_league_id),
            year=int(season),
            team_name=espn_team or None,
            espn_s2=espn_s2 or None,
            swid=swid or None,
        )
        matched = match_espn_to_sleeper(espn_rows, cached_players())
        st.success(f"Matched {len(matched)}/{len(espn_rows)} ESPN players to Sleeper IDs")
        roster_ids = (roster_ids or set()) | set(matched)
    except Exception as exc:
        st.warning(
            "ESPN load failed. Public leagues only need the ID. "
            f"Private leagues need espn_s2 + SWID. Detail: {exc}"
        )

season_i = int(season)
years = (season_i - 1, season_i)
try:
    schedule = cached_schedule(season_i)
    dvp = cached_dvp(years, season_i, int(week))
except Exception as exc:
    st.warning(f"Could not load nflverse matchup data: {exc}")
    schedule = pd.DataFrame()
    dvp = pd.DataFrame()

board = build_board(int(week), season, positions, roster_ids, schedule, dvp)

st.subheader(f"Week {week} board ({season}, Half-PPR)")
if board.empty:
    st.warning("No projection rows. Sleeper projections can be empty before the season slate is posted.")
else:
    show = ["player", "pos", "nfl_team", "opp", "injury", "base", "matchup", "dvp_rank", "proj", "vs_pos", "call"]
    st.dataframe(board[show], use_container_width=True, hide_index=True)

    top_ids = board.head(40)["player_id"].tolist()
    strip = multiweek_strip(top_ids, season, int(week), look_ahead, schedule, dvp)
    if not strip.empty:
        st.subheader("Upcoming weeks")
        cols = ["player", "pos"] + [c for c in strip.columns if c.startswith("W")]
        st.dataframe(strip[cols], use_container_width=True, hide_index=True)

if not dvp.empty:
    st.subheader("Defense vs position (Half-PPR pts allowed / game)")
    dvp_view = dvp.copy()
    dvp_view = dvp_view[dvp_view["position"].isin(positions)]
    dvp_view = dvp_view.sort_values(["position", "rank"])
    st.dataframe(
        dvp_view[["defense", "position", "pts_allowed", "rank", "multiplier", "games"]],
        use_container_width=True,
        hide_index=True,
    )

st.markdown(
    """
**How to read this**
- `base` is Sleeper Half-PPR, reduced if the player is Q/D/OUT.
- `matchup` is that defense's rank vs the player's position (1 = toughest, 32 = easiest).
- `proj` is `base × matchup multiplier` (clamped 0.80–1.20).
- Before week 4, DVP blends last season (70%) with this season (30%). After that it uses this year only.
- `vs_pos` is adjusted points above/below the median player in this table.
- ESPN matching is by name. Nicknames can miss a player.
"""
)
