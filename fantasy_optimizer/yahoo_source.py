"""Live data from the Yahoo! Fantasy Sports API via ``yahoo_fantasy_api``.

``yahoo_fantasy_api`` handles OAuth, token refresh and several parsed
endpoints. For stats-heavy calls we use its raw handler and parse the JSON
ourselves so we get stat ids, bye weeks and fantasy points in one request.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import time
from pathlib import Path

from .models import (Category, LeagueInfo, Matchup, Player, StandingsRow,
                     StatLine, TeamWeek)

RATIO_NAMES = {
    "AVG", "OBP", "SLG", "OPS", "ERA", "WHIP", "K/9", "K/BB", "BB/9", "H/9",
    "GAA", "SV%", "FG%", "FT%", "3PT%", "A/T", "AST/TO", "S%", "FO%", "QS%",
    "WIN%", "SB%", "IP/GS",
}
PAGE = 25


def _merge(items) -> dict:
    """Yahoo encodes objects as lists of single-key dicts; merge them."""
    out = {}
    if isinstance(items, dict):
        return dict(items)
    for it in items or []:
        if isinstance(it, dict):
            out.update(it)
        elif isinstance(it, list):
            out.update(_merge(it))
    return out


def _numbered(d) -> list:
    """Values of a Yahoo {"0": x, "1": y, "count": 2} collection, in order."""
    if not isinstance(d, dict):
        return []
    keys = sorted((k for k in d if k.isdigit()), key=int)
    return [d[k] for k in keys]


def _walk(obj, key):
    """Yield every value stored under ``key`` anywhere inside ``obj``."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from _walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, key)


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_stats(stats_obj) -> dict[int, float]:
    out = {}
    for entry in (stats_obj or {}).get("stats", []):
        stat = entry.get("stat", {})
        val = _float(stat.get("value"))
        if val is not None and "stat_id" in stat:
            out[int(stat["stat_id"])] = val
    return out


def parse_player(entry, weeks: float = 1.0, timeframe: str = "season") -> Player:
    """Parse one ``{"player": [...]}`` element from a players collection."""
    raw = entry["player"]
    info = _merge(raw[0])
    extra = _merge(raw[1:])
    bye = None
    if isinstance(info.get("bye_weeks"), dict):
        bye = info["bye_weeks"].get("week")
        bye = int(bye) if bye and str(bye).isdigit() else None
    status = info.get("status", "")
    if isinstance(status, bool):
        status = ""
    selected = None
    if "selected_position" in extra:
        selected = _merge(extra["selected_position"]).get("position")
    p = Player(
        player_id=int(info["player_id"]),
        name=info.get("name", {}).get("full", "?"),
        team_abbr=info.get("editorial_team_abbr", ""),
        positions=[e["position"] for e in info.get("eligible_positions", [])
                   if isinstance(e, dict) and "position" in e],
        position_type=info.get("position_type", ""),
        status=status,
        selected_position=selected,
        bye_week=bye,
    )
    if "percent_owned" in extra:
        p.percent_owned = _float(_merge(extra["percent_owned"]).get("value"))
    if "player_stats" in extra:
        points = None
        if "player_points" in extra:
            points = _float(extra["player_points"].get("total"))
        p.stat_lines[timeframe] = StatLine(parse_stats(extra["player_stats"]),
                                           points, weeks)
    return p


def parse_players(page) -> list[dict]:
    """Return the raw ``{"player": ...}`` entries in a players collection."""
    out = []
    for coll in _walk(page, "players"):
        if isinstance(coll, dict):
            out += [e for e in _numbered(coll) if isinstance(e, dict) and "player" in e]
    return out


def parse_scoreboard(page) -> list[Matchup]:
    matchups = []
    for m in _walk(page, "matchup"):
        if not isinstance(m, dict):
            continue
        teams_coll = next(_walk(m, "teams"), None)
        teams = []
        for t in _numbered(teams_coll):
            parts = t["team"]
            info = _merge(parts[0])
            extra = _merge(parts[1:])
            wp = _float(extra.get("win_probability"))
            teams.append(TeamWeek(
                team_key=info["team_key"],
                week=int(m.get("week", 0)),
                stats=parse_stats(extra.get("team_stats")),
                points=_float((extra.get("team_points") or {}).get("total")),
                projected_points=_float(
                    (extra.get("team_projected_points") or {}).get("total")),
                win_probability=wp,
            ))
        if len(teams) == 2:
            matchups.append(Matchup(int(m.get("week", 0)), m.get("status", ""),
                                    m.get("week_start"), m.get("week_end"),
                                    (teams[0], teams[1])))
    return matchups


def parse_settings(page, today: dt.date | None = None) -> dict:
    """Extract everything we need from ``league/{key}/settings``."""
    league = page["fantasy_content"]["league"]
    info = _merge(league[0])
    settings = _merge(league[1]["settings"])
    cats = []
    for e in settings.get("stat_categories", {}).get("stats", []):
        s = e.get("stat", {})
        if str(s.get("is_only_display_stat", "0")) == "1":
            continue
        if str(s.get("enabled", "1")) != "1":
            continue
        name = s.get("display_name") or s.get("abbr") or s.get("name", "")
        cats.append(Category(
            stat_id=int(s["stat_id"]), name=name,
            position_type=s.get("position_type", ""),
            higher_is_better=str(s.get("sort_order", "1")) == "1",
            is_ratio=name.upper() in RATIO_NAMES or "%" in name,
        ))
    modifiers = {}
    for e in settings.get("stat_modifiers", {}).get("stats", []):
        s = e.get("stat", {})
        v = _float(s.get("value"))
        if v is not None:
            modifiers[int(s["stat_id"])] = v
    slots = {}
    for e in settings.get("roster_positions", []):
        rp = e.get("roster_position", {})
        if "position" in rp:
            slots[rp["position"]] = slots.get(rp["position"], 0) + int(rp.get("count", 1))

    today = today or dt.date.today()
    start = dt.date.fromisoformat(info["start_date"]) if info.get("start_date") else today
    end = dt.date.fromisoformat(info["end_date"]) if info.get("end_date") else today
    weeks_elapsed = max((min(today, end) - start).days / 7.0, 0.0)
    current_week = int(info.get("current_week") or 1)
    if info.get("game_code") == "nfl":
        # NFL weeks are discrete: count completed weeks plus most of the
        # current one once Sunday has passed.
        weeks_elapsed = max(current_week - 1, 0) + (0.8 if today.weekday() in (0, 1) else 0.0)
    end_week = int(info.get("end_week") or current_week)
    return dict(
        league_key=info["league_key"], name=info.get("name", ""),
        game_code=info.get("game_code", ""), season=int(info.get("season") or today.year),
        scoring_type=info.get("scoring_type", "head"),
        num_teams=int(info.get("num_teams") or 0),
        current_week=current_week, end_week=end_week,
        playoff_start_week=int(settings.get("playoff_start_week") or end_week + 1)
        if str(settings.get("uses_playoff", "1")) == "1" else end_week + 1,
        num_playoff_teams=int(settings.get("num_playoff_teams") or 0),
        weeks_elapsed=weeks_elapsed, categories=cats, stat_modifiers=modifiers,
        roster_slots=slots,
    )


class DiskCache:
    """Tiny JSON cache so repeated commands do not hammer the API."""

    def __init__(self, directory: str | os.PathLike, ttl: float):
        self.dir = Path(directory)
        self.ttl = ttl

    def _path(self, key):
        return self.dir / (hashlib.sha1(key.encode()).hexdigest() + ".json")

    def get(self, key, ttl=None):
        path = self._path(key)
        ttl = self.ttl if ttl is None else ttl
        if ttl > 0 and path.exists() and time.time() - path.stat().st_mtime < ttl:
            return json.loads(path.read_text())
        return None

    def put(self, key, value):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(value))


class YahooSource:
    def __init__(self, oauth_file: str, league_key: str | None,
                 cache_dir: str = ".cache", cache_ttl: float = 1800):
        from yahoo_oauth import OAuth2
        import yahoo_fantasy_api as yfa

        if not os.path.exists(oauth_file):
            raise SystemExit(
                f"OAuth file {oauth_file!r} not found. Run `fantasy auth` first.")
        self.sc = OAuth2(None, None, from_file=oauth_file)
        if not self.sc.token_is_valid():
            self.sc.refresh_access_token()
        self.cache = DiskCache(cache_dir, cache_ttl)
        self._yfa = yfa
        self.league_key = league_key
        self._lg = None
        self._info = None

    # -- low level -------------------------------------------------------
    @property
    def lg(self):
        if self._lg is None:
            if not self.league_key:
                raise SystemExit("No league selected. Pass --league or set "
                                 "YAHOO_LEAGUE_KEY (see `fantasy leagues`).")
            self._lg = self._yfa.League(self.sc, self.league_key)
        return self._lg

    def get(self, uri: str, ttl: float | None = None):
        cached = self.cache.get(uri, ttl)
        if cached is not None:
            return cached
        handler = self._lg.yhandler if self._lg else self._yfa.yhandler.YHandler(self.sc)
        data = handler.get(uri)
        self.cache.put(uri, data)
        return data

    # -- discovery -------------------------------------------------------
    def list_leagues(self) -> list[dict]:
        page = self.get("users;use_login=1/games;is_available=1/leagues")
        out = []
        for league in _walk(page, "league"):
            info = _merge(league)
            if "league_key" in info:
                out.append({k: info.get(k) for k in
                            ("league_key", "name", "game_code", "season",
                             "scoring_type", "num_teams", "current_week")})
        return out

    # -- DataSource interface --------------------------------------------
    def league_info(self) -> LeagueInfo:
        if self._info is None:
            fields = parse_settings(self.get(f"league/{self.league_key}/settings"))
            self._info = LeagueInfo(my_team_key=self.lg.team_key(), **fields)
        return self._info

    def teams(self) -> dict[str, str]:
        return {k: v["name"] for k, v in self.lg.teams().items()}

    def standings(self) -> list[StandingsRow]:
        rows = []
        for t in self.lg.standings():
            ot = t.get("outcome_totals", {})
            rows.append(StandingsRow(
                t["team_key"], t.get("name", ""), float(ot.get("wins", 0) or 0),
                float(ot.get("losses", 0) or 0), float(ot.get("ties", 0) or 0),
                float(t.get("points_for", 0) or 0)))
        return rows

    def _span_weeks(self, timeframe):
        info = self.league_info()
        if timeframe == "season":
            return info.weeks_elapsed
        if timeframe == "lastmonth":
            return min(30 / 7.0, info.weeks_elapsed)
        return 1.0

    def _with_stats(self, players: list[Player]) -> list[Player]:
        """Attach season and last-month stat lines to ``players``."""
        prefix = self.league_key.split(".")[0]
        by_id = {p.player_id: p for p in players}
        ids = list(by_id)
        for tf in ("season", "lastmonth"):
            weeks = self._span_weeks(tf)
            for i in range(0, len(ids), PAGE):
                keys = ",".join(f"{prefix}.p.{pid}" for pid in ids[i:i + PAGE])
                try:
                    page = self.get(f"league/{self.league_key}/players;"
                                    f"player_keys={keys}/stats;type={tf}")
                except Exception:
                    if tf == "season":
                        raise
                    break  # some sports do not support lastmonth
                for entry in parse_players(page):
                    parsed = parse_player(entry, weeks, tf)
                    target = by_id.get(parsed.player_id)
                    if target is None:
                        continue
                    target.stat_lines.update(parsed.stat_lines)
                    for attr in ("bye_week", "team_abbr", "position_type"):
                        if not getattr(target, attr):
                            setattr(target, attr, getattr(parsed, attr))
                    if not target.positions:
                        target.positions = parsed.positions
        return players

    def _roster_players(self, team_key: str) -> list[Player]:
        team = self.lg.to_team(team_key)
        return [Player(
            player_id=r["player_id"], name=r["name"],
            team_abbr=r.get("editorial_team_abbr", ""),
            positions=r.get("eligible_positions", []),
            position_type=r.get("position_type", ""),
            status=r.get("status", ""),
            selected_position=r.get("selected_position"),
            owner_key=team_key) for r in team.roster()]

    def roster(self, team_key: str) -> list[Player]:
        return self._with_stats(self._roster_players(team_key))

    def all_rosters(self) -> dict[str, list[Player]]:
        rosters = {k: self._roster_players(k) for k in self.teams()}
        # One batched stats fetch for the whole league.
        self._with_stats([p for r in rosters.values() for p in r])
        return rosters

    def available_players(self, limit: int = 75, per_position: int = 10) -> list[Player]:
        """Best available players (free agents + waivers) by recent rank."""
        info = self.league_info()
        sort = "PTS" if info.is_points else "AR"
        found: dict[int, Player] = {}

        def fetch(position, count):
            for start in range(0, count, PAGE):
                n = min(PAGE, count - start)
                pos = f";position={position}" if position else ""
                base = (f"league/{self.league_key}/players;status=A;sort={sort}"
                        f"{pos};start={start};count={n}")
                try:
                    page = self.get(base + ";sort_type=lastmonth/percent_owned")
                except Exception:
                    page = self.get(base + ";sort_type=season/percent_owned")
                entries = parse_players(page)
                for e in entries:
                    p = parse_player(e)
                    if p.status != "NA":
                        found.setdefault(p.player_id, p)
                if len(entries) < n:
                    break

        fetch(None, limit)
        for slot in sorted(set(info.starting_slots())):
            if "/" in slot or slot in ("Util", "BN"):
                continue
            fetch(slot, per_position)
        return self._with_stats(list(found.values()))

    def scoreboard(self, week: int | None = None) -> list[Matchup]:
        info = self.league_info()
        week = week or info.current_week
        # Completed weeks never change, so cache them for a long time.
        ttl = 7 * 86400 if week < info.current_week else None
        return parse_scoreboard(self.get(
            f"league/{self.league_key}/scoreboard;week={week}", ttl))

    def recent_adds(self, count: int = 100) -> dict[int, int]:
        page = self.get(f"league/{self.league_key}/transactions;types=add;count={count}")
        adds: dict[int, int] = {}
        for entry in parse_players(page):
            raw = entry["player"]
            info = _merge(raw[0])
            td = _merge(raw[1:]).get("transaction_data")
            td = td[0] if isinstance(td, list) and td else td
            if isinstance(td, dict) and td.get("type") == "add":
                pid = int(info["player_id"])
                adds[pid] = adds.get(pid, 0) + 1
        return adds
