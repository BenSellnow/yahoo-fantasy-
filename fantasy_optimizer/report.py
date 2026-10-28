"""Plain-text rendering of every analysis."""
from __future__ import annotations

from .matchup import MatchupOutlook, my_outlook
from .models import availability
from .playoffs import simulate_season
from .waivers import drop_candidates, plan_moves, recommend, top_available


def table(rows, headers, align=None) -> str:
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    align = align or ["<"] + [">"] * (len(headers) - 1)
    def line(cells):
        return "  ".join(f"{c:{a}{w}}" for c, a, w in zip(cells, align, widths)).rstrip()
    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


def section(title: str) -> str:
    return f"\n{title}\n{'=' * len(title)}"


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def unit(analysis) -> str:
    return "pts/wk" if analysis.league.is_points else "z-value"


def player_label(p) -> str:
    tag = f" [{p.status}]" if p.status else ""
    pos = ",".join(x for x in p.positions if x not in ("Util", "BN", "IR", "IL"))
    return f"{p.name} ({pos}, {p.team_abbr}){tag}"


def render_header(analysis) -> str:
    lg = analysis.league
    kind = "points" if lg.is_points else "categories"
    return (f"{lg.name} — {lg.game_code.upper()} {lg.season}, "
            f"{lg.scoring_type} ({kind}), week {lg.current_week}/{lg.end_week}\n"
            f"Your team: {analysis.team_names.get(analysis.my_key, analysis.my_key)}")


def render_lineup(analysis) -> str:
    out = [section(f"Optimal lineup — week {analysis.league.current_week}")]
    lu = analysis.best_lineup(analysis.my_roster, "week")
    current = {p.player_id: p.selected_position for p in analysis.my_roster}
    rows, moves = [], []
    for slot, p, v in lu.starters:
        if p is None:
            rows.append([slot, "(empty — add someone!)", "", ""])
            continue
        was = current.get(p.player_id) or "?"
        rows.append([slot, player_label(p), f"{v:.1f}", "" if was == slot else f"was {was}"])
        if was in ("BN", None, "?"):
            moves.append(f"START {p.name} at {slot}")
    out.append(table(rows, ["Slot", "Player", unit(analysis), "Change"],
                     ["<", "<", ">", "<"]))
    bench = [[player_label(p), f"{v:.1f}"] for p, v in lu.bench]
    if bench:
        out.append("\nBench:\n" + table(bench, ["Player", unit(analysis)]))
    starters = {p.player_id for _, p, _ in lu.starters if p}
    for p in analysis.my_roster:
        sel = current.get(p.player_id)
        if sel and sel not in ("BN", "IR", "IL", "IL+", "IR+", "NA") and p.player_id not in starters:
            moves.append(f"SIT   {p.name} (currently {sel})")
    alerts = [p for p in analysis.my_roster
              if availability(p.status) == 0 and not p.on_injury_slot]
    if moves:
        out.append("\nSuggested moves:\n  " + "\n  ".join(moves))
    else:
        out.append("\nYour current lineup is already optimal.")
    if alerts:
        out.append("\nInjured players using an active roster spot (consider IR):\n  " +
                   "\n  ".join(player_label(p) for p in alerts))
    byes = [p for p in analysis.my_roster if p.bye_week == analysis.league.current_week]
    if byes:
        out.append("\nOn bye this week: " + ", ".join(p.name for p in byes))
    return "\n".join(out)


def render_matchup(analysis, outlook: MatchupOutlook | None) -> str:
    out = [section("Matchup outlook")]
    if outlook is None:
        out.append("No head-to-head matchup this week.")
        return "\n".join(out)
    names = analysis.team_names
    out.append(f"Week {outlook.week}: {names.get(outlook.team_key)} vs "
               f"{names.get(outlook.opp_key)} ({pct(outlook.progress)} of week played)")
    if outlook.points:
        a, b = outlook.points
        out.append(table([["You", f"{a.mean:.1f}", f"±{a.sd:.1f}"],
                          ["Opponent", f"{b.mean:.1f}", f"±{b.sd:.1f}"]],
                         ["Team", "Proj. final", "Spread"]))
    else:
        rows = []
        for c in outlook.categories:
            cur = lambda v: "-" if v is None else (f"{v:.3f}" if abs(v) < 2 and v != int(v) else f"{v:g}")
            fmt = (lambda d: f"{d.mean:.3f}") if abs(c.final[0].mean) < 2 else (lambda d: f"{d.mean:.0f}")
            rows.append([c.name, cur(c.current[0]), cur(c.current[1]),
                         fmt(c.final[0]), fmt(c.final[1]), pct(c.win_prob),
                         "contested" if 0.3 < c.win_prob < 0.7 else ""])
        out.append(table(rows, ["Cat", "You now", "Opp now", "You proj", "Opp proj",
                                "Win%", ""], ["<", ">", ">", ">", ">", ">", "<"]))
        ea, eb = outlook.expected_cats
        out.append(f"Expected category score: {ea:.1f} - {eb:.1f}")
    line = f"\nWin probability: {pct(outlook.win_prob)}"
    if outlook.yahoo_win_prob is not None:
        line += f"  (Yahoo says {pct(outlook.yahoo_win_prob)})"
    out.append(line)
    return "\n".join(out)


def render_waivers(analysis, outlook=None, top=10, week_weight=0.35) -> str:
    out = [section("Best pickups")]
    recs = recommend(analysis, outlook, week_weight=week_weight, top=top)
    if not recs:
        out.append("No available player improves your roster right now.")
    else:
        rows = []
        for r in recs:
            rows.append([player_label(r.add), r.drop.name if r.drop else "(open spot)",
                         f"{r.gain:+.2f}", f"{r.week_gain:+.2f}", f"{r.season_gain:+.2f}",
                         "🔥" * min(r.recent_adds, 3)])
        out.append(table(rows, ["Add", "Drop", "Gain", "This wk", "Season", "Trend"],
                         ["<", "<", ">", ">", ">", "<"]))
        out.append(f"Gain = improvement in your best lineup ({unit(analysis)}), "
                   "plus a little credit for bench depth.")
        if not analysis.league.is_points and outlook and outlook.categories:
            out.append("(This-week gains are weighted toward this week's contested categories.)")
    plan = plan_moves(analysis, outlook, week_weight)
    if len(plan) > 1:
        out.append("\nSuggested plan (moves that work together):")
        for i, r in enumerate(plan, 1):
            drop = f"drop {r.drop.name}" if r.drop else "use open spot"
            out.append(f"  {i}. Add {r.add.name}, {drop}  ({r.gain:+.2f})")
    drops = drop_candidates(analysis)
    out.append("\nWeakest players on your roster: " +
               ", ".join(f"{p.name} ({v:.1f})" for p, v in drops))
    return "\n".join(out)


def render_available(analysis, n=15) -> str:
    out = [section("Top available players (rest of season)")]
    rows = [[player_label(p), f"{w:.1f}", f"{s:.1f}",
             "" if p.percent_owned is None else f"{p.percent_owned:.0f}%"]
            for p, w, s in top_available(analysis, n)]
    out.append(table(rows, ["Player", "This wk", "Season", "Owned"]))
    return "\n".join(out)


def render_playoffs(analysis, sims=3000) -> str:
    out = [section("Playoff odds (season simulation)")]
    lg = analysis.league
    if not lg.is_head_to_head:
        out.append("Not a head-to-head league.")
        return "\n".join(out)
    if lg.current_week >= lg.playoff_start_week:
        out.append("The regular season is over.")
        return "\n".join(out)
    odds = simulate_season(analysis, sims)
    rows = []
    for t in odds:
        me = " ◀ you" if t.team_key == analysis.my_key else ""
        rows.append([t.name + me, t.record, f"{t.proj_wins:.1f}-{t.proj_losses:.1f}",
                     f"{t.avg_seed:.1f}", pct(t.playoff_prob), pct(t.top_seed_prob)])
    out.append(table(rows, ["Team", "Record", "Proj. final", "Avg seed",
                            "Playoffs", "#1 seed"]))
    out.append(f"({sims} simulations, {lg.num_playoff_teams} playoff spots, "
               f"playoffs start week {lg.playoff_start_week})")
    return "\n".join(out)


def render_report(analysis, top=10, sims=3000, week_weight=0.35) -> str:
    outlook = my_outlook(analysis)
    parts = [render_header(analysis), render_matchup(analysis, outlook),
             render_lineup(analysis), render_waivers(analysis, outlook, top, week_weight),
             render_playoffs(analysis, sims)]
    return "\n".join(parts)
