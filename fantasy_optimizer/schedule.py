"""Pro-team game schedules, for counting games played per fantasy week.

In weekly head-to-head basketball the number of games a player gets matters
as much as how good he is: a 4-game week is worth a third more than a
3-game week. The NBA publishes its full season schedule as public JSON.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

NBA_SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"

# Yahoo's editorial team abbreviations that differ from NBA tricodes.
YAHOO_TO_NBA = {
    "GS": "GSW", "NY": "NYK", "NO": "NOP", "SA": "SAS", "PHO": "PHX",
    "UTAH": "UTA", "BRK": "BKN", "BK": "BKN", "CHO": "CHA", "WSH": "WAS",
    "NOR": "NOP", "SAN": "SAS", "GSW": "GSW",
}


def normalize(abbr: str) -> str:
    abbr = (abbr or "").upper()
    return YAHOO_TO_NBA.get(abbr, abbr)


class Schedule:
    """Which teams play on which dates."""

    def __init__(self, games: dict[dt.date, set[str]]):
        self.games = {d: {normalize(t) for t in teams} for d, teams in games.items()}
        teams = set().union(*self.games.values()) if self.games else set()
        self.teams = teams
        days = sorted(self.games)
        if days and teams:
            weeks = max(((days[-1] - days[0]).days + 1) / 7.0, 1.0)
            total = sum(len(t) for t in self.games.values())
            self.avg_games_per_week = total / len(teams) / weeks
        else:
            self.avg_games_per_week = 0.0

    def knows(self, team: str) -> bool:
        return normalize(team) in self.teams

    def plays_on(self, team: str, day: dt.date) -> bool:
        return normalize(team) in self.games.get(day, set())

    def games_between(self, team: str, start: dt.date, end: dt.date) -> int:
        team = normalize(team)
        return sum(1 for d, teams in self.games.items()
                   if start <= d <= end and team in teams)


def parse_nba_schedule(data: dict) -> Schedule:
    """Parse the NBA's scheduleLeagueV2.json. Preseason games are skipped."""
    games: dict[dt.date, set[str]] = defaultdict(set)
    for day in data.get("leagueSchedule", {}).get("gameDates", []):
        raw = day.get("gameDate", "")
        try:
            date = dt.datetime.strptime(raw.split(" ")[0], "%m/%d/%Y").date()
        except ValueError:
            continue
        for g in day.get("games", []):
            if str(g.get("gameId", "")).startswith("001"):  # preseason
                continue
            for side in ("homeTeam", "awayTeam"):
                code = (g.get(side) or {}).get("teamTricode")
                if code:
                    games[date].add(code)
    return Schedule(dict(games))


def fetch_nba_schedule(cache=None) -> Schedule | None:
    """Download the season schedule; None if it can't be reached."""
    data = cache.get(NBA_SCHEDULE_URL, 12 * 3600) if cache else None
    if data is None:
        try:
            import requests
            resp = requests.get(NBA_SCHEDULE_URL, timeout=20,
                                headers={"User-Agent": "fantasy-optimizer"})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None
        if cache:
            cache.put(NBA_SCHEDULE_URL, data)
    schedule = parse_nba_schedule(data)
    return schedule if schedule.teams else None
