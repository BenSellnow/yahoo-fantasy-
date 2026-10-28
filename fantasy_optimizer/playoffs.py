"""Season simulation: playoff odds and projected final standings.

Each team's weekly output is a normal distribution whose mean blends its
actual weekly results so far with what its current roster projects to
(rosters change, so history alone is stale). The remaining regular-season
schedule is then simulated many times.
"""
from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from .matchup import POINTS_CV, COUNT_CV, RATIO_CV, Dist, outlook_for

HISTORY_PRIOR = 3  # weeks of history needed before it outweighs the roster
# Uncertainty in each team's true strength for the rest of the season
# (injuries, trades, slumps), as a share of its mean. Drawn once per
# simulated season, on top of week-to-week noise.
STRENGTH_CV = {"points": 0.06, "count": 0.05, "ratio": 0.01}


@dataclass
class TeamOdds:
    team_key: str
    name: str
    record: str
    playoff_prob: float
    top_seed_prob: float
    avg_seed: float
    proj_wins: float
    proj_losses: float


def _blend(hist: list[float], roster: float, cv: float) -> Dist:
    n = len(hist)
    w = n / (n + HISTORY_PRIOR)
    mean = w * statistics.fmean(hist) + (1 - w) * roster if hist else roster
    sd = statistics.stdev(hist) if n >= 3 else 0.0
    sd_prior = cv * abs(mean)
    sd = w * sd + (1 - w) * sd_prior if n >= 3 else sd_prior
    return Dist(mean, max(sd, 1e-4))


def team_distributions(analysis) -> dict[str, dict]:
    """Per team, {'points': Dist} or {stat_id: Dist} for a typical week."""
    league = analysis.league
    history: dict[str, list] = {k: [] for k in analysis.rosters}
    for week in range(1, league.current_week):
        for m in analysis.scoreboard(week):
            for t in m.teams:
                if t.team_key in history:
                    history[t.team_key].append(t)
    out = {}
    for key in analysis.rosters:
        starters = [p for _, p, _ in analysis.best_lineup(analysis.rosters[key], "season").starters if p]
        roster_proj = analysis.team_week_projection(starters, "season")
        if league.is_points:
            hist = [t.points for t in history[key] if t.points is not None]
            out[key] = {"points": _blend(hist, roster_proj["points"], POINTS_CV)}
        else:
            out[key] = {}
            for cat in league.categories:
                hist = [t.stats[cat.stat_id] for t in history[key] if cat.stat_id in t.stats]
                cv = RATIO_CV if cat.is_ratio else COUNT_CV
                out[key][cat.stat_id] = _blend(hist, roster_proj.get(cat.stat_id, 0.0), cv)
    return out


def _counts_categories(standings, completed_weeks) -> bool:
    """True if standings record one W/L/T per category rather than per matchup."""
    if completed_weeks <= 0 or not standings:
        return False
    games = statistics.fmean(r.wins + r.losses + r.ties for r in standings)
    return games > completed_weeks * 1.5


def simulate_season(analysis, sims: int = 3000, seed: int = 0) -> list[TeamOdds]:
    league = analysis.league
    if not league.is_head_to_head:
        return []
    rng = random.Random(seed)
    standings = analysis.source.standings()
    by_cat = (not league.is_points) and (
        league.scoring_type != "headone") and _counts_categories(standings, league.current_week - 1)
    dists = team_distributions(analysis)
    cats = league.categories

    # This week's matchups use the live in-week outlook; later weeks use the
    # generic weekly distributions.
    current = {}
    if league.current_week < league.playoff_start_week:
        for m in analysis.scoreboard(league.current_week):
            a = m.teams[0].team_key
            o = outlook_for(analysis, m, a, sims=1)
            current[(a, m.teams[1].team_key)] = o
    future = []
    for week in range(league.current_week + 1, league.playoff_start_week):
        try:
            board = analysis.scoreboard(week)
        except Exception:
            break  # schedule not published that far ahead
        future.append([(m.teams[0].team_key, m.teams[1].team_key) for m in board])

    keys = [r.team_key for r in standings]
    names = {r.team_key: r.name for r in standings}
    made = {k: 0 for k in keys}
    top = {k: 0 for k in keys}
    seed_sum = {k: 0.0 for k in keys}
    win_sum = {k: 0.0 for k in keys}
    loss_sum = {k: 0.0 for k in keys}
    n_playoff = league.num_playoff_teams or max(len(keys) // 2, 1)

    def play(a, b, da, db, rec, pf):
        if league.is_points:
            sa, sb = rng.gauss(da["points"].mean, da["points"].sd), \
                rng.gauss(db["points"].mean, db["points"].sd)
            pf[a] += sa
            pf[b] += sb
            results = [(a, b) if sa > sb else (b, a)]
        else:
            results, wa, wb = [], 0, 0
            for cat in cats:
                x, y = da[cat.stat_id], db[cat.stat_id]
                va, vb = rng.gauss(x.mean, x.sd), rng.gauss(y.mean, y.sd)
                if (va > vb) == cat.higher_is_better:
                    wa += 1
                else:
                    wb += 1
            if by_cat:
                results = [(a, b)] * wa + [(b, a)] * wb
            elif wa != wb:
                results = [(a, b) if wa > wb else (b, a)]
            else:
                rec[a][2] += 1
                rec[b][2] += 1
        for w, l in results:
            rec[w][0] += 1
            rec[l][1] += 1

    def shifted(d):
        out = {}
        for k, dist in d.items():
            cat = cat_by_id.get(k)
            cv = STRENGTH_CV["points" if k == "points" else
                             "ratio" if cat and cat.is_ratio else "count"]
            out[k] = Dist(dist.mean * (1 + rng.gauss(0, cv)), dist.sd)
        return out

    cat_by_id = {c.stat_id: c for c in cats}
    for _ in range(sims):
        season = {k: shifted(d) for k, d in dists.items()}
        rec = {r.team_key: [r.wins, r.losses, r.ties] for r in standings}
        pf = {r.team_key: r.points_for for r in standings}
        for (a, b), o in current.items():
            if o.points:
                da, db = {"points": o.points[0]}, {"points": o.points[1]}
            else:
                da = {c.stat_id: c.final[0] for c in o.categories}
                db = {c.stat_id: c.final[1] for c in o.categories}
            play(a, b, da, db, rec, pf)
        for week in future:
            for a, b in week:
                if a in season and b in season:
                    play(a, b, season[a], season[b], rec, pf)

        def pct(k):
            w, l, t = rec[k]
            g = w + l + t
            return (w + 0.5 * t) / g if g else 0.0
        order = sorted(keys, key=lambda k: (-pct(k), -pf[k], rng.random()))
        for i, k in enumerate(order):
            seed_sum[k] += i + 1
            win_sum[k] += rec[k][0]
            loss_sum[k] += rec[k][1]
            if i < n_playoff:
                made[k] += 1
            if i == 0:
                top[k] += 1

    out = []
    for r in standings:
        k = r.team_key
        record = f"{r.wins:g}-{r.losses:g}" + (f"-{r.ties:g}" if r.ties else "")
        out.append(TeamOdds(k, names[k], record, made[k] / sims, top[k] / sims,
                            seed_sum[k] / sims, win_sum[k] / sims, loss_sum[k] / sims))
    out.sort(key=lambda t: t.avg_seed)
    return out
