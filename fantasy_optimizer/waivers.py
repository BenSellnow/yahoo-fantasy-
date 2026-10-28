"""Waiver-wire / free-agent recommendations.

For every promising available player we try swapping him in for each player
you could drop, re-optimise the lineup, and measure how much better the
roster gets. Gains blend this week (bye weeks, injuries, matchup needs) with
the rest of the season.
"""
from __future__ import annotations

from dataclasses import dataclass

from .matchup import category_focus_weights
from .models import Player
from .valuation import Valuator

WEEK_WEIGHT = 0.35


@dataclass
class Recommendation:
    add: Player
    drop: Player | None
    gain: float
    week_gain: float
    season_gain: float
    add_value: float
    recent_adds: int = 0


def recommend(analysis, outlook=None, week_weight: float = WEEK_WEIGHT,
              top: int = 10, candidates: int = 40, roster=None,
              pool=None) -> list[Recommendation]:
    league = analysis.league
    roster = [p for p in (roster or analysis.my_roster) if not p.on_injury_slot]
    open_spots = max(league.active_roster_size() - len(roster), 0)

    # In category leagues, tilt this week's values toward contested categories.
    week_val = analysis.valuator
    weights = category_focus_weights(outlook)
    if weights:
        week_val = Valuator(league, analysis.valuator.baselines, weights)

    def score(players):
        return (analysis.best_lineup(players, "week", week_val).score,
                analysis.best_lineup(players, "season").score)

    base_week, base_season = score(roster)
    try:
        trending = analysis.source.recent_adds()
    except Exception:
        trending = {}

    def blended(p):
        return week_weight * analysis.value(p, "week", week_val) + \
            (1 - week_weight) * analysis.value(p, "season")

    pool = sorted(pool or analysis.available, key=lambda p: -blended(p))[:candidates]
    recs = []
    for cand in pool:
        options = [(p, [q for q in roster if q is not p] + [cand]) for p in roster]
        if open_spots:
            options.append((None, roster + [cand]))
        best = None
        for drop, new_roster in options:
            w, s = score(new_roster)
            dw, ds = w - base_week, s - base_season
            gain = week_weight * dw + (1 - week_weight) * ds
            if best is None or gain > best.gain:
                best = Recommendation(cand, drop, gain, dw, ds, blended(cand),
                                      trending.get(cand.player_id, 0))
        if best and best.gain > 1e-6:
            recs.append(best)
    recs.sort(key=lambda r: -r.gain)
    return recs[:top]


def plan_moves(analysis, outlook=None, week_weight: float = WEEK_WEIGHT,
               max_moves: int = 3) -> list[Recommendation]:
    """A sequence of add/drops that work together, chosen greedily.

    After each move the roster is updated and everything is re-evaluated, so
    you never get two moves that drop the same player or fill the same need.
    """
    roster = list(analysis.my_roster)
    pool = list(analysis.available)
    moves = []
    for _ in range(max_moves):
        recs = recommend(analysis, outlook, week_weight, top=1, roster=roster, pool=pool)
        if not recs or recs[0].gain < 0.05:
            break
        move = recs[0]
        moves.append(move)
        roster = [p for p in roster if p is not move.drop] + [move.add]
        pool = [p for p in pool if p is not move.add]
    return moves


def drop_candidates(analysis, n: int = 3) -> list[tuple[Player, float]]:
    roster = [p for p in analysis.my_roster if not p.on_injury_slot]
    vals = [(p, analysis.value(p, "season")) for p in roster]
    return sorted(vals, key=lambda t: t[1])[:n]


def top_available(analysis, n: int = 15) -> list[tuple[Player, float, float]]:
    rows = [(p, analysis.value(p, "week"), analysis.value(p, "season"))
            for p in analysis.available]
    return sorted(rows, key=lambda r: -r[2])[:n]
