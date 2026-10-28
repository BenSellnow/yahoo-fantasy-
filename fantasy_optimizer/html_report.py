"""Self-contained HTML version of the weekly report (no server needed).

Used by ``fantasy html`` to make a page you can open, share or host as a
static file, and as a clickable preview of the web app.
"""
from __future__ import annotations

from html import escape

from .matchup import my_outlook
from .playoffs import simulate_season
from .report import lineup_advice
from .waivers import drop_candidates, plan_moves, recommend, top_available

CSS = """
/* Layout: a scoreboard header over tabbed, box-score style tables. */
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #14181f; --muted: #5b6472;
  --line: #e1e4ea; --fav: #2a78d6; --behind: #d9622b; --neutral: #a9aeb8;
  --chip: #eef3fb; --warn-bg: #fff6e0; --warn-ink: #7a5300; --bad-bg: #fdeceb;
  --bad-ink: #9b2a22;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "IBM Plex Sans", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #12151a; --panel: #1b1f26; --ink: #eef0f3; --muted: #a2a9b5; --line: #2d333d;
  --fav: #3987e5; --behind: #e0703a; --neutral: #5d6470; --chip: #1f2b3d;
  --warn-bg: #3a2f12; --warn-ink: #f2cf7a; --bad-bg: #3d1c1a; --bad-ink: #f3a49d;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #12151a; --panel: #1b1f26; --ink: #eef0f3; --muted: #a2a9b5; --line: #2d333d;
  --fav: #3987e5; --behind: #e0703a; --neutral: #5d6470; --chip: #1f2b3d;
  --warn-bg: #3a2f12; --warn-ink: #f2cf7a; --bad-bg: #3d1c1a; --bad-ink: #f3a49d;
  color-scheme: dark; }
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { background: var(--bg); color: var(--ink); font: 15px/1.5 var(--body); }
.wrap { max-width: 1080px; margin: 0 auto; padding-block: 24px 48px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 20px; }
.note { font-size: 13px; color: var(--muted); border: 1px dashed var(--line);
  border-radius: 6px; padding: 8px 12px; }
header h1 { font: 600 clamp(32px, 6vw, 48px)/1 var(--display); margin: 0;
  letter-spacing: 0.01em; text-wrap: balance; }
header p { margin: 6px 0 0; color: var(--muted); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 12px 14px; min-width: 0; }
.tile .k { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }
.tile .v { font: 600 34px/1.1 var(--display); font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere; }
.tile .s { font-size: 13px; color: var(--muted); }
nav { display: flex; gap: 4px; flex-wrap: wrap; border-bottom: 1px solid var(--line); }
nav button { font: 500 15px var(--body); color: var(--muted); background: none; border: 0;
  border-bottom: 3px solid transparent; padding: 8px 12px; cursor: pointer; }
nav button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--fav); }
nav button:focus-visible { outline: 2px solid var(--fav); outline-offset: 2px; }
section { display: grid; gap: 16px; min-width: 0; }
h2 { font: 600 26px/1.1 var(--display); margin: 0; letter-spacing: 0.01em; }
h3 { font: 600 19px/1.2 var(--display); margin: 0; letter-spacing: 0.02em; }
.plan { margin: 0; padding-left: 22px; display: grid; gap: 6px; }
.callout { border-radius: 8px; padding: 10px 14px; }
.callout.warn { background: var(--warn-bg); color: var(--warn-ink); }
.callout.bad { background: var(--bad-bg); color: var(--bad-ink); }
.callout.info { background: var(--chip); }
.callout ul { margin: 4px 0 0; padding-left: 20px; }
.tbl { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 7px 12px; text-align: left; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 500; }
tr:last-child td { border-bottom: 0; }
td.n, th.n { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
tr.you td { background: var(--chip); font-weight: 600; }
.status { font: 600 11px var(--mono); padding: 1px 5px; border-radius: 4px;
  background: var(--bad-bg); color: var(--bad-ink); margin-left: 6px; }
.pips { font-family: var(--mono); letter-spacing: 1px; color: var(--fav); }
.pips .off { color: var(--neutral); }
.caption { font-size: 13px; color: var(--muted); margin: 0; }
.bars { display: grid; grid-template-columns: minmax(70px, max-content) 1fr; gap: 6px 12px;
  align-items: center; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 14px; }
.bars .lab { font-size: 13px; color: var(--muted); text-align: right; overflow-wrap: anywhere; }
.bars .lab.you { color: var(--ink); font-weight: 600; }
.track { position: relative; height: 20px; }
.track .bar { position: absolute; top: 3px; height: 14px; border-radius: 3px; }
.track .mid { position: absolute; left: 50%; top: 0; bottom: 0; border-left: 1px dashed var(--muted); }
.track .val { position: absolute; top: 0; font: 12px/20px var(--mono); color: var(--ink); white-space: nowrap; }
.axis { grid-column: 2; display: flex; justify-content: space-between; font: 11px var(--mono); color: var(--muted); }
.duel { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
@media (prefers-reduced-motion: no-preference) { nav button { transition: color .15s, border-color .15s; } }
"""

JS = """
(function () {
  var tabs = document.querySelectorAll('nav button');
  function show(id) {
    tabs.forEach(function (b) {
      var on = b.dataset.tab === id;
      b.setAttribute('aria-selected', on);
      document.getElementById(b.dataset.tab).hidden = !on;
    });
  }
  tabs.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.tab); history.replaceState(null, '', '#' + b.dataset.tab); });
  });
  function fromHash() {
    var id = location.hash.slice(1);
    if (document.querySelector('nav button[data-tab="' + id + '"]')) show(id);
  }
  window.addEventListener('hashchange', fromHash);
  fromHash();
})();
"""

FONTS = ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600"
         "&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap")


def e(x) -> str:
    return escape(str(x))


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def stat(v, name="") -> str:
    """Box-score formatting: shooting percentages as .483, counts as integers."""
    if v is None:
        return "–"
    if abs(v) < 2 and ("%" in name or v != int(v)):
        return f"{v:.3f}".lstrip("0") if v >= 0 else f"{v:.3f}"
    return f"{v:.0f}"


def label(p) -> str:
    pos = "/".join(x for x in p.positions if x not in ("Util", "BN", "IR", "IL", "W/R/T"))
    status = f'<span class="status">{e(p.status)}</span>' if p.status else ""
    return f"{e(p.name)} <span class=\"caption\">{e(pos)} · {e(p.team_abbr)}</span>{status}"


def pips(n) -> str:
    if n is None:
        return ""
    on = min(n, 4)
    return (f'<span class="pips" title="{n} games left this week">{"●" * on}'
            f'<span class="off">{"○" * max(4 - on, 0)}</span></span> {n}')


def table(headers, rows, numeric=()) -> str:
    th = "".join(f'<th class="{"n" if i in numeric else ""}">{e(h)}</th>'
                 for i, h in enumerate(headers))
    body = []
    for row in rows:
        cls = ' class="you"' if getattr(row, "you", False) else ""
        cells = row.cells if hasattr(row, "cells") else row
        body.append(f"<tr{cls}>" + "".join(
            f'<td class="{"n" if i in numeric else ""}">{c}</td>' for i, c in enumerate(cells)) + "</tr>")
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


class Row:
    def __init__(self, cells, you=False):
        self.cells, self.you = cells, you


def pickups_html(a, outlook, week_weight) -> str:
    unit = "pts/wk" if a.league.is_points else "z"
    plan = plan_moves(a, outlook, week_weight)
    out = ["<h2>Do this</h2>"]
    if plan:
        items = "".join(
            f"<li>Add <b>{e(r.add.name)}</b>, "
            + (f"drop <b>{e(r.drop.name)}</b>" if r.drop else "use your open roster spot")
            + f" <span class=\"caption\">gain {r.gain:+.2f} {unit}</span></li>" for r in plan)
        out.append(f'<ol class="plan">{items}</ol>')
    else:
        out.append('<p class="callout info">No available player improves your roster right now.</p>')
    recs = recommend(a, outlook, week_weight, top=15)
    games = a.games_based
    headers = ["Add"] + (["Games left"] if games else []) + \
        ["Drop", "Gain", "This week", "Rest of season", "Recent adds"]
    n0 = 3 if games else 2
    rows = [[label(r.add)] + ([pips(a.proj[r.add.player_id].games_left)] if games else []) +
            [e(r.drop.name) if r.drop else "–", f"{r.gain:+.2f}", f"{r.week_gain:+.2f}",
             f"{r.season_gain:+.2f}", r.recent_adds or ""] for r in recs]
    out += ["<h3>All good pickups</h3>", table(headers, rows, range(n0, n0 + 4)),
            f'<p class="caption">Gain = improvement to your best lineup ({unit}), weighted '
            f"{week_weight:.0%} this week and {1 - week_weight:.0%} rest of season.</p>"]
    weak = ", ".join(f"{e(p.name)} ({v:.1f})" for p, v in drop_candidates(a, 5))
    out.append(f'<p class="caption">Weakest on your roster: {weak}</p>')
    return "".join(out)


def lineup_html(a) -> str:
    adv = lineup_advice(a)
    title = (f"Today's lineup · {a.today:%A, %b %d}" if adv.horizon == "today"
             else f"Week {a.league.current_week} lineup")
    out = [f"<h2>{e(title)}</h2>"]
    if adv.horizon == "today":
        out.append('<p class="caption">Lineups lock daily, so anyone without a game today '
                   "sits for a teammate who is playing.</p>")
    if adv.moves:
        out.append('<div class="callout warn"><b>Lineup changes to make</b><ul>' +
                   "".join(f"<li>{e(m.replace('   ', ' '))}</li>" for m in adv.moves) + "</ul></div>")
    else:
        out.append('<p class="callout info">Your current lineup is already optimal.</p>')
    if adv.injured_active:
        out.append('<p class="callout bad">Injured players taking an active spot: ' +
                   ", ".join(f"{e(p.name)} [{e(p.status)}]" for p in adv.injured_active) + "</p>")
    if adv.idle_today:
        out.append('<p class="callout info">No game today: ' +
                   ", ".join(e(p.name) for p in adv.idle_today) + "</p>")
    games = a.games_based
    unit = "Proj pts/wk" if a.league.is_points else "Value (z)"
    empty = "nobody with a game today" if adv.horizon == "today" else "empty"
    rows = []
    for slot, p, v in adv.lineup.starters:
        if p is None:
            rows.append([e(slot), f'<span class="caption">{empty}</span>'] +
                        ([""] if games else []) + ["", ""])
        else:
            rows.append([e(slot), label(p)] + ([pips(a.proj[p.player_id].games_left)] if games else []) +
                        [f"{v:.1f}", e(adv.previous.get(p.player_id) or "")])
    for p, v in adv.lineup.bench:
        rows.append(["Bench", label(p)] + ([pips(a.proj[p.player_id].games_left)] if games else []) +
                    [f"{v:.1f}", e(adv.previous.get(p.player_id) or "")])
    headers = ["Slot", "Player"] + (["Games left"] if games else []) + [unit, "Now in"]
    out.append(table(headers, rows, {len(headers) - 2}))
    return "".join(out)


def category_bars(cats) -> str:
    rows = []
    for c in cats:
        p = c.win_prob
        left, width = (50, (p - 0.5) * 100) if p >= 0.5 else (p * 100, (0.5 - p) * 100)
        color = "var(--fav)" if p >= 0.5 else "var(--behind)"
        val_pos = (f"left: calc({p * 100:.1f}% + 6px)" if p >= 0.5
                   else f"right: calc({(1 - p) * 100:.1f}% + 6px)")
        rows.append(
            f'<div class="lab">{e(c.name)}</div>'
            f'<div class="track" title="{e(c.name)}: {pct(p)} chance to win">'
            f'<div class="mid"></div><div class="bar" style="left:{left:.1f}%;width:{max(width, 0.6):.1f}%;'
            f'background:{color}"></div><div class="val" style="{val_pos}">{pct(p)}</div></div>')
    axis = '<div class="axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>'
    return f'<div class="bars">{"".join(rows)}{axis}</div>'


def matchup_html(a, outlook) -> str:
    if outlook is None:
        return '<p class="callout info">No head-to-head matchup this week.</p>'
    names = a.team_names
    out = [f"<h2>{e(names.get(outlook.team_key))} vs {e(names.get(outlook.opp_key))}</h2>",
           f'<p class="caption">{pct(outlook.progress)} of the week played</p>']
    if outlook.points:
        me, opp = outlook.points
        out.append('<div class="duel">' + "".join(
            f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in [
                ("Your projected score", f"{me.mean:.1f}"), ("Opponent projected", f"{opp.mean:.1f}"),
                ("Win chance", pct(outlook.win_prob))]) + "</div>")
        return "".join(out)
    ea, eb = outlook.expected_cats
    out.append('<div class="duel">' + "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>' for k, v in [
            ("Win chance", pct(outlook.win_prob)), ("Expected category score", f"{ea:.1f}–{eb:.1f}")])
        + "</div>")
    out += ["<h3>Chance to win each category</h3>", category_bars(outlook.categories),
            '<p class="caption">Blue: you are favored. Orange: you are behind. Categories near '
            "50% are the ones worth chasing on the waiver wire this week.</p>"]
    rows = [[e(c.name), stat(c.current[0], c.name), stat(c.current[1], c.name),
             stat(c.final[0].mean, c.name), stat(c.final[1].mean, c.name), pct(c.win_prob)]
            for c in outlook.categories]
    out.append(table(["Category", "You now", "Opp now", "You proj", "Opp proj", "Win"], rows,
                     range(1, 6)))
    return "".join(out)


def playoffs_html(a, odds, sims) -> str:
    lg = a.league
    if not lg.is_head_to_head:
        return '<p class="callout info">Not a head-to-head league.</p>'
    if not odds:
        return '<p class="callout info">The regular season is over.</p>'
    bars = []
    for t in sorted(odds, key=lambda t: -t.playoff_prob):
        you = t.team_key == a.my_key
        color = "var(--fav)" if you else "var(--neutral)"
        pos = (f"right: calc({(1 - t.playoff_prob) * 100:.1f}% + 6px); color: var(--panel)"
               if t.playoff_prob > 0.85 else f"left: calc({t.playoff_prob * 100:.1f}% + 6px)")
        bars.append(
            f'<div class="lab{" you" if you else ""}">{e(t.name)}{" (you)" if you else ""}</div>'
            f'<div class="track" title="{e(t.name)}: {pct(t.playoff_prob)} playoff chance">'
            f'<div class="bar" style="left:0;width:{max(t.playoff_prob * 100, 0.6):.1f}%;background:{color}"></div>'
            f'<div class="val" style="{pos}">{pct(t.playoff_prob)}</div></div>')
    axis = '<div class="axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>'
    rows = [Row([e(t.name), e(t.record), f"{t.proj_wins:.1f}–{t.proj_losses:.1f}", f"{t.avg_seed:.1f}",
                 pct(t.playoff_prob), pct(t.top_seed_prob)], t.team_key == a.my_key) for t in odds]
    return "".join([
        "<h2>Playoff odds</h2>", f'<div class="bars">{"".join(bars)}{axis}</div>',
        table(["Team", "Record", "Proj. record", "Avg seed", "Playoffs", "#1 seed"], rows, range(2, 6)),
        f'<p class="caption">{sims:,} simulated seasons · {lg.num_playoff_teams} playoff spots · '
        f"playoffs start week {lg.playoff_start_week}</p>"])


def free_agents_html(a) -> str:
    games = a.games_based
    rows = [[label(p)] + ([pips(a.proj[p.player_id].games_left)] if games else []) +
            [f"{w:.1f}", f"{s:.1f}", "" if p.percent_owned is None else f"{p.percent_owned:.0f}%"]
            for p, w, s in top_available(a, 30)]
    headers = ["Player"] + (["Games left"] if games else []) + ["This week", "Rest of season", "Owned"]
    n0 = 2 if games else 1
    return "<h2>Best available players</h2>" + table(headers, rows, range(n0, n0 + 3))


def render_html(a, sims: int = 3000, week_weight: float = 0.35, note: str = "") -> str:
    lg = a.league
    outlook = my_outlook(a)
    odds = simulate_season(a, sims) if lg.is_head_to_head and lg.current_week < lg.playoff_start_week else []
    plan = plan_moves(a, outlook, week_weight)
    me = next((t for t in odds if t.team_key == a.my_key), None)
    tiles = [("Week", f"{lg.current_week} of {lg.end_week}", "")]
    if outlook:
        tiles.append(("Win chance this week", pct(outlook.win_prob), ""))
    if me:
        tiles.append(("Playoff odds", pct(me.playoff_prob), f"Record {me.record}"))
    if plan:
        tiles.append(("Top pickup", plan[0].add.name, f"gain {plan[0].gain:+.1f}"))
    tiles_html = "".join(
        f'<div class="tile"><div class="k">{e(k)}</div><div class="v">{e(v)}</div>'
        f'<div class="s">{e(s)}</div></div>' for k, v, s in tiles)
    sections = [("pickups", "Pickups", pickups_html(a, outlook, week_weight)),
                ("lineup", "Lineup", lineup_html(a)),
                ("matchup", "Matchup", matchup_html(a, outlook)),
                ("playoffs", "Playoff odds", playoffs_html(a, odds, sims)),
                ("free-agents", "Free agents", free_agents_html(a))]
    nav = "".join(f'<button type="button" role="tab" data-tab="{i}" aria-selected="{str(n == 0).lower()}">'
                  f"{e(t)}</button>" for n, (i, t, _) in enumerate(sections))
    body = "".join(f'<section id="{i}" role="tabpanel"{"" if n == 0 else " hidden"}>{h}</section>'
                   for n, (i, _, h) in enumerate(sections))
    kind = "points" if lg.is_points else "categories"
    note_html = f'<p class="note">{e(note)}</p>' if note else ""
    return f"""<meta charset="utf-8">
<title>{e(lg.name)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
<div class="wrap">
{note_html}
<header><h1>{e(lg.name)}</h1>
<p>{e(lg.game_code.upper())} {lg.season} · {kind} · Your team: <b>{e(a.team_names.get(a.my_key, a.my_key))}</b></p></header>
<div class="tiles">{tiles_html}</div>
<nav role="tablist">{nav}</nav>
{body}
</div>
<script>{JS}</script>
"""
