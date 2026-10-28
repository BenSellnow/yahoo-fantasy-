"""Loads league data once and exposes the shared building blocks."""
from __future__ import annotations

from dataclasses import dataclass, field

from .lineup import Lineup, optimize_lineup
from .models import INACTIVE_SLOTS, LeagueInfo, Player
from .projections import RECENT_WEIGHT, Projection, project_all
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

    @classmethod
    def load(cls, source, recent_weight: float = RECENT_WEIGHT,
             pool_size: int = 75) -> "Analysis":
        league = source.league_info()
        rosters = source.all_rosters()
        available = source.available_players(limit=pool_size)
        rostered = [p for r in rosters.values() for p in r]
        proj = project_all(rostered + available, league, recent_weight)
        valuator = Valuator.build(league, rostered, proj)
        return cls(source, league, source.teams(), rosters, available, proj, valuator)

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
        attr = "week_factor" if horizon == "week" else "season_factor"
        return {p.player_id: getattr(self.proj[p.player_id], attr) > 0 for p in players}

    def best_lineup(self, players: list[Player], horizon: str = "week",
                    valuator: Valuator | None = None) -> Lineup:
        players = [p for p in players if not p.on_injury_slot]
        values = {p.player_id: self.value(p, horizon, valuator) for p in players}
        return optimize_lineup(players, self.league.starting_slots(), values,
                               self.startable(players, horizon))

    def current_starters(self, team_key: str) -> list[Player]:
        roster = self.rosters[team_key]
        starters = [p for p in roster
                    if p.selected_position and p.selected_position not in INACTIVE_SLOTS]
        if not starters:
            starters = [p for _, p, _ in self.best_lineup(roster).starters if p]
        return starters

    # -- team aggregates -------------------------------------------------
    def team_week_projection(self, starters: list[Player]) -> dict:
        """Projected weekly output of a lineup: {'points': x} or {stat_id: x}."""
        if self.league.is_points:
            return {"points": sum(self.proj[p.player_id].points *
                                  self.proj[p.player_id].week_factor for p in starters)}
        out = {}
        for cat in self.league.categories:
            vals, weights = [], []
            for p in starters:
                if cat.position_type and p.position_type and cat.position_type != p.position_type:
                    continue
                pr = self.proj[p.player_id]
                vals.append(pr.stats.get(cat.stat_id, 0.0) * (1 if cat.is_ratio else pr.week_factor))
                weights.append(pr.week_factor)
            if cat.is_ratio:
                tw = sum(weights)
                out[cat.stat_id] = sum(v * w for v, w in zip(vals, weights)) / tw if tw else 0.0
            else:
                out[cat.stat_id] = sum(vals)
        return out
