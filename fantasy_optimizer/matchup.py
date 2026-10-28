"""Head-to-head win probability for a weekly matchup.

Final totals for each side are modelled as normal distributions: what has
already happened this week plus the projected output of the remaining
lineup. Points leagues compare one number; category leagues simulate every
category together and count who wins more of them.
"""
from __future__ import annotations

import datetime as dt
import math
import random
from dataclasses import dataclass

from .models import Matchup, TeamWeek

POINTS_CV = 0.20    # week-to-week spread of a team's fantasy points
COUNT_CV = 0.15     # same for counting categories
RATIO_CV = 0.04     # and for ratio categories (FG%, ERA, ...)


def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class Dist:
    mean: float
    sd: float


@dataclass
class CategoryOutlook:
    stat_id: int
    name: str
    current: tuple[float | None, float | None]
    final: tuple[Dist, Dist]
    win_prob: float


@dataclass
class MatchupOutlook:
    week: int
    team_key: str
    opp_key: str
    progress: float
    win_prob: float
    points: tuple[Dist, Dist] | None = None
    categories: list[CategoryOutlook] | None = None
    expected_cats: tuple[float, float] | None = None
    yahoo_win_prob: float | None = None


def week_progress(m: Matchup, today: dt.date | None = None) -> float:
    if m.status == "postevent":
        return 1.0
    if m.status == "preevent":
        return 0.0
    if m.week_start and m.week_end:
        today = today or dt.date.today()
        start = dt.date.fromisoformat(m.week_start)
        end = dt.date.fromisoformat(m.week_end)
        total = (end - start).days + 1
        return min(max((today - start).days / total, 0.0), 1.0)
    return 0.5


def _points_dist(tw: TeamWeek, weekly: float, f: float) -> Dist:
    current = tw.points or 0.0
    if tw.projected_points:
        # Yahoo's live projection already accounts for games remaining.
        total = tw.projected_points
        left = 1 - min(current / total, 1.0) if total > 0 else 1 - f
        return Dist(total, max(POINTS_CV * total * math.sqrt(left), 0.01))
    rest = weekly * (1 - f)
    return Dist(current + rest, max(POINTS_CV * weekly * math.sqrt(1 - f), 0.01))


def _cat_dist(cat, current, weekly, f) -> Dist:
    if cat.is_ratio:
        mean = weekly if current is None or f == 0 else f * current + (1 - f) * weekly
        return Dist(mean, max(RATIO_CV * abs(weekly) * math.sqrt(1 - f), 1e-4))
    rest = weekly * (1 - f)
    var = (COUNT_CV * weekly) ** 2 * (1 - f) + rest
    return Dist((current or 0.0) + rest, max(math.sqrt(var), 1e-4))


def pairwise(a: Dist, b: Dist, higher_is_better: bool = True) -> float:
    sd = math.sqrt(a.sd ** 2 + b.sd ** 2)
    p = norm_cdf((a.mean - b.mean) / sd)
    return p if higher_is_better else 1 - p


def outlook_for(analysis, m: Matchup, team_key: str, sims: int = 10000,
                rng: random.Random | None = None) -> MatchupOutlook:
    league = analysis.league
    me, opp = m.side(team_key), m.opponent_of(team_key)
    f = week_progress(m)
    weekly_me = analysis.team_week_projection(analysis.current_starters(me.team_key))
    weekly_opp = analysis.team_week_projection(analysis.current_starters(opp.team_key))

    if league.is_points:
        a = _points_dist(me, weekly_me["points"], f)
        b = _points_dist(opp, weekly_opp["points"], f)
        return MatchupOutlook(m.week, me.team_key, opp.team_key, f, pairwise(a, b),
                              points=(a, b), yahoo_win_prob=me.win_probability)

    cats = []
    for cat in league.categories:
        cur_a, cur_b = me.stats.get(cat.stat_id), opp.stats.get(cat.stat_id)
        a = _cat_dist(cat, cur_a, weekly_me.get(cat.stat_id, 0.0), f)
        b = _cat_dist(cat, cur_b, weekly_opp.get(cat.stat_id, 0.0), f)
        cats.append(CategoryOutlook(cat.stat_id, cat.name, (cur_a, cur_b), (a, b),
                                    pairwise(a, b, cat.higher_is_better)))
    win, exp_a, exp_b = simulate_categories(
        [(c.final[0], c.final[1], cat.higher_is_better)
         for c, cat in zip(cats, league.categories)], sims, rng)
    return MatchupOutlook(m.week, me.team_key, opp.team_key, f, win,
                          categories=cats, expected_cats=(exp_a, exp_b))


def simulate_categories(cats, sims=10000, rng=None):
    """Monte Carlo a category matchup. Returns (P(win), E[cats A], E[cats B])."""
    rng = rng or random.Random(0)
    wins = ties = 0
    tot_a = tot_b = 0
    for _ in range(sims):
        a_w = b_w = 0
        for da, db, hib in cats:
            va, vb = rng.gauss(da.mean, da.sd), rng.gauss(db.mean, db.sd)
            if va == vb:
                continue
            if (va > vb) == hib:
                a_w += 1
            else:
                b_w += 1
        tot_a += a_w
        tot_b += b_w
        wins += a_w > b_w
        ties += a_w == b_w
    return (wins + 0.5 * ties) / sims, tot_a / sims, tot_b / sims


def my_outlook(analysis, week: int | None = None, sims: int = 10000) -> MatchupOutlook | None:
    if not analysis.league.is_head_to_head:
        return None
    week = week or analysis.league.current_week
    for m in analysis.scoreboard(week):
        if m.side(analysis.my_key):
            return outlook_for(analysis, m, analysis.my_key, sims)
    return None


def category_focus_weights(outlook: MatchupOutlook | None) -> dict[int, float]:
    """Weight categories by how contested they are this week.

    A 50/50 category gets the most weight; a locked-up or lost-cause one gets
    little, which is how experienced managers stream for a matchup.
    """
    if not outlook or not outlook.categories:
        return {}
    raw = {c.stat_id: 0.3 + 0.7 * 4 * c.win_prob * (1 - c.win_prob) for c in outlook.categories}
    mean = sum(raw.values()) / len(raw)
    return {k: v / mean for k, v in raw.items()}
