"""ESPN roster helper.

Public leagues only need league_id + year.
Private leagues need espn_s2 and swid cookies from a logged-in browser.
"""

from __future__ import annotations


def load_espn_roster_names(
    league_id: int,
    year: int,
    team_name: str | None = None,
    espn_s2: str | None = None,
    swid: str | None = None,
) -> list[dict]:
    from espn_api.football import League

    kwargs = {"league_id": league_id, "year": year}
    if espn_s2 and swid:
        kwargs["espn_s2"] = espn_s2
        kwargs["swid"] = swid

    league = League(**kwargs)
    teams = league.teams
    if team_name:
        needle = team_name.lower()
        teams = [t for t in teams if needle in t.team_name.lower() or needle in (t.owner or "").lower()]
        if not teams:
            raise ValueError(f"No ESPN team matched '{team_name}'")
    team = teams[0]
    rows = []
    for p in team.roster:
        rows.append(
            {
                "name": p.name,
                "position": p.position,
                "team": getattr(p, "proTeam", None) or getattr(p, "pro_team", None),
                "injured": bool(getattr(p, "injured", False)),
            }
        )
    return rows


def match_espn_to_sleeper(espn_players: list[dict], sleeper_players: dict[str, dict]) -> list[str]:
    """Best-effort name match so ESPN roster can use Sleeper projections."""
    index: dict[str, str] = {}
    for pid, p in sleeper_players.items():
        name = (p.get("full_name") or "").lower().strip()
        if name:
            index[name] = pid
        alt = f"{p.get('first_name', '')} {p.get('last_name', '')}".lower().strip()
        if alt:
            index[alt] = pid

    ids = []
    for row in espn_players:
        key = (row.get("name") or "").lower().strip()
        pid = index.get(key)
        if pid:
            ids.append(pid)
    return ids
