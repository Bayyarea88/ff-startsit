import statistics

import pandas as pd
import requests
import streamlit as st

APP = "https://api.sleeper.app/v1"
PROJ = "https://api.sleeper.com"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def get(url, params=None, browser=False):
    headers = {"User-Agent": UA if browser else "ff-startsit/1.0"}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=3600)
def nfl_state():
    return get(f"{APP}/state/nfl")


@st.cache_data(ttl=6 * 3600)
def all_players():
    return get(f"{APP}/players/nfl")


@st.cache_data(ttl=1800)
def week_projections(season, week):
    raw = get(
        f"{PROJ}/projections/nfl/{season}/{week}",
        params={"season_type": "regular"},
        browser=True,
    )
    if isinstance(raw, dict):
        return raw
    out = {}
    if isinstance(raw, list):
        for row in raw:
            pid = str(row.get("player_id") or "")
            if pid:
                out[pid] = row.get("stats") or row
    return out


@st.cache_data(ttl=3600)
def user_leagues(username, season):
    user = get(f"{APP}/user/{username}")
    return user, get(f"{APP}/user/{user['user_id']}/leagues/nfl/{season}")


def half_ppr(proj):
    if not proj:
        return 0.0
    if proj.get("pts_half_ppr") is not None:
        return float(proj["pts_half_ppr"])
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


def avail(player):
    status = (player.get("injury_status") or "").lower()
    if status in {"out", "ir", "pup", "suspended"}:
        return 0.0
    if status == "doubtful":
        return 0.25
    if status == "questionable":
        return 0.80
    return 1.0


def name_of(p):
    return p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()


def label(pts, median):
    gap = pts - median
    if gap >= 4:
        return "Strong Start"
    if gap >= 1.5:
        return "Lean Start"
    if gap <= -4:
        return "Sit"
    if gap <= -1.5:
        return "Lean Sit"
    return "Toss-up"


def my_roster(username, league_id):
    user = get(f"{APP}/user/{username}")
    for roster in get(f"{APP}/league/{league_id}/rosters"):
        if str(roster.get("owner_id")) == str(user.get("user_id")):
            return [str(x) for x in (roster.get("players") or [])]
    return []


st.set_page_config(page_title="Half-PPR Start/Sit", layout="wide")
st.title("Half-PPR Start / Sit")

state = nfl_state()
season = str(state.get("season") or "2026")
default_week = int(state.get("week") or 1)

with st.sidebar:
    st.header("Settings")
    week = st.number_input("NFL week", 1, 18, min(max(default_week, 1), 18))
    positions = st.multiselect("Positions", ["QB", "RB", "WR", "TE"], ["QB", "RB", "WR", "TE"])
    username = st.text_input("Sleeper username")
    league_id = ""
    if username.strip():
        try:
            _user, leagues = user_leagues(username.strip(), season)
            options = {f"{lg.get('name')} ({lg.get('league_id')})": lg.get("league_id") for lg in leagues}
            if options:
                choice = st.selectbox("Sleeper league", list(options))
                league_id = options[choice]
            else:
                st.info("No NFL leagues found for that user.")
        except Exception as exc:
            st.error(f"Sleeper lookup failed: {exc}")

roster_ids = None
if username.strip() and league_id:
    try:
        roster_ids = set(my_roster(username.strip(), league_id))
        st.sidebar.success(f"Loaded {len(roster_ids)} roster players")
    except Exception as exc:
        st.sidebar.error(str(exc))

players = all_players()
projs = week_projections(season, int(week))

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
    pts = half_ppr(proj if isinstance(proj, dict) else {}) * avail(p)
    rows.append(
        {
            "player": name_of(p) or pid,
            "pos": pos,
            "nfl_team": p.get("team") or "",
            "injury": p.get("injury_status") or "",
            "proj": round(pts, 2),
        }
    )

df = pd.DataFrame(rows)
st.subheader(f"Week {week} · {season} · Half-PPR")

if df.empty:
    st.warning("No projection rows. Try another week, or Sleeper has not posted this week yet.")
else:
    med = {}
    for pos, grp in df.groupby("pos"):
        med[pos] = statistics.median(grp["proj"].tolist())
    df["vs_pos"] = df.apply(lambda r: round(r["proj"] - med.get(r["pos"], 0), 2), axis=1)
    df["call"] = df.apply(lambda r: label(r["proj"], med.get(r["pos"], 0)), axis=1)
    df = df.sort_values(["pos", "proj"], ascending=[True, False])
    st.dataframe(
        df[["player", "pos", "nfl_team", "injury", "proj", "vs_pos", "call"]],
        use_container_width=True,
        hide_index=True,
    )

st.caption("proj = Sleeper Half-PPR. call is vs the other players in this table.")
