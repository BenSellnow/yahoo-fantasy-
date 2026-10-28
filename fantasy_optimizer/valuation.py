"""Collapse a projection into a single comparable value per player.

* Points leagues: projected fantasy points per week.
* Category leagues: the sum of per-category z-scores, measured against the
  pool of rostered players at the same position type, so a value of 0 is a
  typical rostered player and positive numbers are better than that.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .models import LeagueInfo, Player
from .projections import Projection

Z_CAP = 3.0


@dataclass
class CategoryBaseline:
    mean: float
    sd: float


@dataclass
class Valuator:
    league: LeagueInfo
    baselines: dict[tuple[str, int], CategoryBaseline]
    category_weights: dict[int, float]

    @classmethod
    def build(cls, league: LeagueInfo, pool: list[Player],
              projections: dict[int, Projection],
              category_weights: dict[int, float] | None = None) -> "Valuator":
        baselines = {}
        if not league.is_points:
            by_type: dict[str, list[Player]] = {}
            for p in pool:
                by_type.setdefault(p.position_type, []).append(p)
            for cat in league.categories:
                for ptype, players in by_type.items():
                    if cat.position_type and cat.position_type != ptype:
                        continue
                    vals = [projections[p.player_id].stats.get(cat.stat_id, 0.0)
                            for p in players if p.player_id in projections]
                    if len(vals) < 2:
                        continue
                    sd = statistics.pstdev(vals) or 1.0
                    baselines[(ptype, cat.stat_id)] = CategoryBaseline(
                        statistics.fmean(vals), sd)
        return cls(league, baselines, category_weights or {})

    def category_z(self, player: Player, proj: Projection) -> dict[int, float]:
        """Per-category z-scores (sign flipped so higher is always better)."""
        out = {}
        counting = []
        for cat in self.league.categories:
            base = self.baselines.get((player.position_type, cat.stat_id))
            if base is None:
                continue
            z = (proj.stats.get(cat.stat_id, 0.0) - base.mean) / base.sd
            if not cat.higher_is_better:
                z = -z
            out[cat.stat_id] = max(-Z_CAP, min(Z_CAP, z))
            if not cat.is_ratio and base.mean > 0:
                counting.append(proj.stats.get(cat.stat_id, 0.0) / base.mean)
        # Ratio stats matter in proportion to playing time: a bench guy who
        # shot 3-for-3 should not look like an elite FG% asset.
        volume = min(1.0, statistics.fmean(counting)) if counting else 1.0
        for cat in self.league.categories:
            if cat.is_ratio and cat.stat_id in out:
                out[cat.stat_id] *= max(volume, 0.0)
        return out

    def value(self, player: Player, proj: Projection, horizon: str = "season") -> float:
        factor = proj.week_factor if horizon == "week" else proj.season_factor
        if self.league.is_points:
            return proj.points * factor
        z = self.category_z(player, proj)
        total = sum(v * self.category_weights.get(sid, 1.0) for sid, v in z.items())
        # Scale toward "replacement" (z of about -1 for a freely available
        # player) so injured players are not valued above healthy ones.
        return (total + len(z) * 0.5) * factor - len(z) * 0.5
