"""Turn a player's historical stat lines into per-week projections.

The model is deliberately simple and transparent: a weighted blend of the
player's season-long weekly rate and their last-month weekly rate (recent
form), scaled by their injury status and, for the current week, bye weeks.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import LeagueInfo, Player, availability

# How much weight recent form gets versus the full season.
RECENT_WEIGHT = 0.5
# Points per week assumed for players with no stats at all (rookies, call-ups).
NO_DATA_WEEKS = 0.5


@dataclass
class Projection:
    """Expected production for one week, for the rest of the season and now."""
    stats: dict[int, float]
    points: float
    week_factor: float      # share of a normal week the player plays this week
    season_factor: float    # share of games expected over the rest of the season
    games_left: int | None = None  # games left this week, when the schedule is known

    def week_stats(self) -> dict[int, float]:
        return {k: v * self.week_factor for k, v in self.stats.items()}


def _rate(line, sid, ratio):
    if line is None or sid not in line.stats:
        return None
    if ratio:
        return line.stats[sid]
    return line.stats[sid] / max(line.weeks, 1e-9)


def _points_from_modifiers(stats: dict[int, float], modifiers: dict[int, float]):
    return sum(stats.get(sid, 0.0) * mult for sid, mult in modifiers.items())


def project_player(player: Player, league: LeagueInfo,
                   recent_weight: float = RECENT_WEIGHT) -> Projection:
    season = player.stat_lines.get("season")
    recent = player.stat_lines.get("lastmonth")
    if recent is not None and recent.weeks <= 0:
        recent = None
    if season is not None and season.weeks <= 0:
        season = None

    ratio_ids = {c.stat_id for c in league.categories if c.is_ratio}
    stat_ids = set()
    for line in (season, recent):
        if line is not None:
            stat_ids |= set(line.stats)

    stats = {}
    for sid in stat_ids:
        is_ratio = sid in ratio_ids
        s, r = _rate(season, sid, is_ratio), _rate(recent, sid, is_ratio)
        if s is not None and r is not None:
            stats[sid] = (1 - recent_weight) * s + recent_weight * r
        else:
            stats[sid] = s if s is not None else (r or 0.0)

    def points_rate(line):
        if line is None:
            return None
        if line.points is not None:
            return line.points / max(line.weeks, 1e-9)
        if league.stat_modifiers:
            return _points_from_modifiers(line.stats, league.stat_modifiers) / \
                max(line.weeks, 1e-9)
        return None

    ps, pr = points_rate(season), points_rate(recent)
    if ps is not None and pr is not None:
        points = (1 - recent_weight) * ps + recent_weight * pr
    else:
        points = ps if ps is not None else (pr or 0.0)

    avail = availability(player.status)
    week_factor = avail
    if player.bye_week and player.bye_week == league.current_week:
        week_factor = 0.0
    # Injured players usually come back; assume they miss about half of the
    # remaining season when currently out, which keeps stashes on the radar.
    season_factor = avail if avail > 0 else 0.5
    if league.game_code == "nfl" and player.bye_week and \
            player.bye_week >= league.current_week:
        remaining = max(league.end_week - league.current_week + 1, 1)
        season_factor *= (remaining - 1) / remaining

    return Projection(stats=stats, points=points,
                      week_factor=week_factor, season_factor=season_factor)


def project_all(players, league, recent_weight=RECENT_WEIGHT):
    return {p.player_id: project_player(p, league, recent_weight) for p in players}
