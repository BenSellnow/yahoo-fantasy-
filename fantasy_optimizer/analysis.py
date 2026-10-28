"""Loads league data once and exposes the shared building blocks."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .lineup import Lineup, optimize_lineup
from .models import INACTIVE_SLOTS, LeagueInfo, Player, availability
from .projections import RECENT_WEIGHT, Projection, project_all
from .schedule import Schedule
from .valuation import Valuator


@dataclass
class Analysis:
    source: object
    league: LeagueInfo
    team_names: dict[str, str]
    rosters: dict[str, list[Player]]
    available: list[Player]
    proj: dict[int, Projection]
    valuator: Valuator
    _scoreboards: dict[int, list] = field(default_factory=dict)
    today: dt.date = field(default_factory=dt.date.today)
    schedule: Schedule | None = None
    week_dates: tuple[dt.date, dt.date] | None = None

    @classmethod
    def load(cls, source, recent_weight: float = RECENT_WEIGHT,
             pool_size: int = 75, today: dt.date | None = None) -> "Analysis":
        league = source.league_info()
        rosters = source.all_rosters()
        available = source.available_players(limit=pool_size)
        rostered = [p for r in rosters.values() for p in r]
        proj = project_all(rostered + available, league, recent_weight)
        valuator = Valuator.build(league, rostered, proj)
        a = cls(source, league, source.teams(), rosters, available, proj, valuator,
                today=today or dt.date.today())
        a._apply_schedule(rostered + available)
        return a

    def _apply_schedule(self, players):
        """Scale this week's projections by the games each team has left."""
        get = getattr(self.source, "schedule", None)
        schedule = get() if get else None
        if not schedule or not schedule.avg_games_per_week:
            return
        board = self.scoreboard(self.league.current_week)
        m = next((m for m in board if m.week_start and m.week_end), None)
        if m is None:
            return
        start, end = dt.date.fromisoformat(m.week_start), dt.date.fromisoformat(m.week_end)
        self.schedule, self.week_dates = schedule, (start, end)
        first = max(self.today, start)
        full_week = schedule.avg_games_per_week
        share_left = max((end - first).days + 1, 0) / ((end - start).days + 1)
        for p in players:
            pr = self.proj[p.player_id]
            if schedule.knows(p.team_abbr):
                pr.games_left = schedule.games_between(p.team_abbr, first, end)
                pr.week_factor *= pr.games_left / full_week
            else:
                pr.week_factor *= share_left

    @property
    def games_based(self) -> bool:
        """True when this week's projections already count remaining games."""
        return self.schedule is not None

    @property
    def lineup_horizon(self) -> str:
        """Basketball lineups are set daily, so optimise for today's games."""
        return "today" if self.schedule is not None else "week"

    @property
    def my_key(self) -> str:
        return self.league.my_team_key

    @property
    def my_roster(self) -> list[Player]:
        return self.rosters[self.my_key]

    def scoreboard(self, week: int):
        if week not in self._scoreboards:
            self._scoreboards[week] = self.source.scoreboard(week)
        return self._scoreboards[week]

    # -- values ----------------------------------------------------------
    def value(self, p: Player, horizon: str = "season", valuator: Valuator | None = None):
        return (valuator or self.valuator).value(p, self.proj[p.player_id], horizon)

    def startable(self, players, horizon):
        if horizon == "today":
            return {p.player_id: availability(p.status) > 0 and
                    self.schedule.plays_on(p.team_abbr, self.today) for p in players}
        attr = "week_factor" if horizon == "week" else "season_factor"
        return {p.player_id: getattr(self.proj[p.player_id], attr) > 0 for p in players}

    def best_lineup(self, players: list[Player], horizon: str = "week",
                    valuator: Valuator | None = None) -> Lineup:
        players = [p for p in players if not p.on_injury_slot]
        value_horizon = "season" if horizon == "today" else horizon
        values = {p.player_id: self.value(p, value_horizon, valuator) for p in players}
        return optimize_lineup(players, self.league.starting_slots(), values,
                               self.startable(players, horizon),
                               self.empty_value(value_horizon, valuator))

    def empty_value(self, horizon: str, valuator: Valuator | None = None) -> float:
        """Below the worst player anywhere, so an empty slot never looks good."""
        weights = (valuator or self.valuator).category_weights
        key = (horizon, tuple(sorted(weights.items())))
        cache = self.__dict__.setdefault("_empty", {})
        if key not in cache:
            players = [p for r in self.rosters.values() for p in r] + self.available
            cache[key] = min([0.0] + [self.value(p, horizon, valuator) for p in players]) - 1
        return cache[key]

    def current_starters(self, team_key: str) -> list[Player]:
        roster = self.rosters[team_key]
        starters = [p for p in roster
                    if p.selected_position and p.selected_position not in INACTIVE_SLOTS]
        if not starters:
            starters = [p for _, p, _ in self.best_lineup(roster).starters if p]
        return starters

    # -- team aggregates -------------------------------------------------
    def team_remaining_output(self, team_key: str) -> dict:
        """What a team will produce over the rest of this week.

        With a game schedule (basketball) each remaining day is played out:
        the best lineup from that day's available players, each contributing
        one game. Otherwise the current starters' weekly projection is used.
        """
        if not self.games_based:
            return self.team_week_projection(self.current_starters(team_key))
        return self.remaining_output(self.rosters[team_key])

    def remaining_output(self, roster: list[Player], with_games: bool = False):
        """Day-by-day output of ``roster`` over the rest of the week (needs a schedule)."""
        roster = [p for p in roster if not p.on_injury_slot]
        slots = self.league.starting_slots()
        values = {p.player_id: self.value(p, "season") for p in roster}
        per_week = self.schedule.avg_games_per_week
        start, end = self.week_dates
        day = max(self.today, start)
        games: dict[int, float] = {}
        while day <= end:
            playing = {}
            for p in roster:
                if availability(p.status) <= 0:
                    continue
                if self.schedule.knows(p.team_abbr):
                    if self.schedule.plays_on(p.team_abbr, day):
                        playing[p.player_id] = 1.0
                else:  # unknown team: assume an average schedule
                    playing[p.player_id] = per_week / 7
            lu = optimize_lineup([p for p in roster if p.player_id in playing], slots, values)
            for _, p, _ in lu.starters:
                if p:
                    games[p.player_id] = games.get(p.player_id, 0) + \
                        playing[p.player_id] * availability(p.status)
            day += dt.timedelta(days=1)
        out = self._aggregate({p.player_id: g / per_week for p in roster
                               if (g := games.get(p.player_id))}, roster)
        return (out, sum(games.values())) if with_games else out

    def streaming_score(self, roster: list[Player], valuator: Valuator | None = None) -> float:
        """This week's remaining output as one number (pts, or z-units for categories)."""
        out, games = self.remaining_output(roster, with_games=True)
        if self.league.is_points:
            return out["points"]
        val = valuator or self.valuator
        per_week = self.schedule.avg_games_per_week
        score = 0.0
        for cat in self.league.categories:
            base = next((b for (_, sid), b in val.baselines.items() if sid == cat.stat_id), None)
            if base is None:
                continue
            if cat.is_ratio:
                z = (out[cat.stat_id] - base.mean) / base.sd * games / per_week
            else:
                z = out[cat.stat_id] / base.sd
            score += (z if cat.higher_is_better else -z) * val.category_weights.get(cat.stat_id, 1.0)
        return score

    def _aggregate(self, weights: dict[int, float], players: list[Player]) -> dict:
        """Sum projections, each player scaled by ``weights`` (share of a week)."""
        players = [p for p in players if weights.get(p.player_id)]
        if self.league.is_points:
            return {"points": sum(self.proj[p.player_id].points * weights[p.player_id]
                                  for p in players)}
        out = {}
        for cat in self.league.categories:
            num = den = 0.0
            for p in players:
                if cat.position_type and p.position_type and cat.position_type != p.position_type:
                    continue
                w = weights[p.player_id]
                val = self.proj[p.player_id].stats.get(cat.stat_id, 0.0)
                num += val * w
                den += w
            out[cat.stat_id] = (num / den if den else 0.0) if cat.is_ratio else num
        return out

    def team_week_projection(self, starters: list[Player], horizon: str = "week") -> dict:
        """Projected weekly output of a lineup: {'points': x} or {stat_id: x}.

        ``horizon="season"`` gives a typical future week instead of this one.
        """
        attr = "week_factor" if horizon == "week" else "season_factor"
        return self._aggregate({p.player_id: getattr(self.proj[p.player_id], attr)
                                for p in starters}, starters)
