"""Web front end for the fantasy optimizer (Streamlit).

Run locally:   streamlit run streamlit_app.py
Host for free: Streamlit Community Cloud (see README).
"""
from __future__ import annotations

import hmac
import logging

import altair as alt
import pandas as pd
import streamlit as st

from fantasy_optimizer import webauth
from fantasy_optimizer.analysis import Analysis
from fantasy_optimizer.matchup import my_outlook
from fantasy_optimizer.playoffs import simulate_season
from fantasy_optimizer.report import lineup_advice
from fantasy_optimizer.waivers import drop_candidates, plan_moves, recommend, top_available

logging.getLogger("yahoo_oauth").setLevel(logging.WARNING)
st.set_page_config(page_title="Fantasy Optimizer", page_icon="🏈", layout="wide")

BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#a3a29b"
SOURCES = {"My Yahoo league": None, "Demo: NFL points league": "nfl",
           "Demo: NBA categories league": "nba"}


# -- secrets & access -----------------------------------------------------
def secrets() -> dict:
    try:
        return dict(st.secrets)
    except Exception:  # no secrets file at all (e.g. first local run)
        return {}


def password_ok(conf: dict) -> bool:
    expected = conf.get("app_password")
    if not expected or st.session_state.get("authed"):
        return True
    st.title("Fantasy Optimizer")
    pw = st.text_input("Password", type="password")
    if pw and hmac.compare_digest(pw, str(expected)):
        st.session_state.authed = True
        st.rerun()
    elif pw:
        st.error("Wrong password.")
    return False


def yahoo_oauth_file(conf: dict) -> str | None:
    """Return a ready yahoo_oauth file path, running the login flow if needed."""
    y = dict(conf.get("yahoo", {}))
    cid, secret = y.get("client_id"), y.get("client_secret")
    redirect = y.get("redirect_uri", "oob")
    if not (cid and secret):
        st.info("Yahoo isn't configured yet — use a demo league from the sidebar, "
                "or follow the README's *Host it for free* steps to add your Yahoo app keys.")
        return None
    if "oauth_file" in st.session_state:
        return st.session_state.oauth_file

    if y.get("refresh_token"):
        path = webauth.write_oauth_file(cid, secret, y["refresh_token"], redirect)
        st.session_state.oauth_file = path
        return path

    code = st.query_params.get("code")
    if code:
        try:
            tokens = webauth.exchange_code(cid, secret, redirect, code)
        except Exception as e:
            st.error(str(e))
            return None
        st.query_params.clear()
        st.session_state.oauth_file = webauth.oauth_file_from_tokens(cid, secret, redirect, tokens)
        st.session_state.new_refresh_token = tokens["refresh_token"]
        return st.session_state.oauth_file

    st.subheader("Connect your Yahoo account")
    st.write("You'll be sent to Yahoo to approve read access to your fantasy leagues, "
             "then brought back here.")
    st.link_button("Connect Yahoo", webauth.authorize_url(cid, redirect), type="primary")
    return None


def show_new_token_notice():
    token = st.session_state.get("new_refresh_token")
    if not token:
        return
    with st.expander("✅ Connected! Save this so you stay logged in", expanded=True):
        st.write("Add this line under `[yahoo]` in your app's **Secrets** "
                 "(Streamlit Cloud → your app → Settings → Secrets). Otherwise you'll "
                 "need to reconnect whenever the app restarts.")
        st.code(f'refresh_token = "{token}"', language="toml")


# -- data loading ---------------------------------------------------------
@st.cache_resource(ttl=1800, show_spinner=False)
def list_leagues(oauth_file: str):
    from fantasy_optimizer.yahoo_source import YahooSource
    return YahooSource(oauth_file, None).list_leagues()


@st.cache_resource(ttl=1800, show_spinner=False)
def load(demo: str | None, league_key: str | None, oauth_file: str | None,
         recent_weight: float, pool: int) -> Analysis:
    if demo:
        from fantasy_optimizer.demo import DemoSource
        source = DemoSource(demo)
    else:
        from fantasy_optimizer.yahoo_source import YahooSource
        source = YahooSource(oauth_file, league_key)
    return Analysis.load(source, recent_weight, pool)


def memo(key, fn):
    """Cache derived results for the current analysis across reruns."""
    store = st.session_state.setdefault("memo", {})
    if key not in store:
        store[key] = fn()
    return store[key]


# -- formatting -----------------------------------------------------------
def label(p) -> str:
    pos = "/".join(x for x in p.positions if x not in ("Util", "BN", "IR", "IL", "W/R/T"))
    return f"{p.name} ({pos}, {p.team_abbr})"


def pct(x) -> str:
    return f"{100 * x:.0f}%"


def playoff_chart(df: pd.DataFrame) -> alt.Chart:
    order = df.sort_values("Playoffs", ascending=False)["Team"].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y("Team:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X("Playoffs:Q", title="Chance to make playoffs",
                scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format="%", grid=True)),
        tooltip=[alt.Tooltip("Team:N"), alt.Tooltip("Record:N"),
                 alt.Tooltip("Playoffs:Q", format=".0%"),
                 alt.Tooltip("#1 seed:Q", format=".0%"),
                 alt.Tooltip("Avg seed:Q", format=".1f")])
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
        color=alt.condition(alt.datum.You, alt.value(BLUE), alt.value(GRAY)))
    text = base.mark_text(align="left", dx=4).encode(
        text=alt.Text("Playoffs:Q", format=".0%"))
    return (bars + text).properties(height=28 * len(df))


def category_chart(df: pd.DataFrame) -> alt.Chart:
    df = df.assign(mid=0.5, Leading=df["Win%"] >= 0.5)
    base = alt.Chart(df).encode(
        y=alt.Y("Category:N", sort=None, title=None),
        tooltip=["Category", alt.Tooltip("Win%:Q", format=".0%"), "You (proj)", "Opp (proj)"])
    x = alt.X("mid:Q", scale=alt.Scale(domain=[0, 1]), title="Chance to win category",
              axis=alt.Axis(format="%", values=[0, 0.25, 0.5, 0.75, 1]))
    bars = base.mark_bar(height={"band": 0.7}).encode(
        x=x, x2="Win%:Q",
        color=alt.condition(alt.datum.Leading, alt.value(BLUE), alt.value(ORANGE)))
    rule = alt.Chart(pd.DataFrame({"x": [0.5]})).mark_rule(strokeDash=[4, 4]).encode(x="x:Q")
    # Label each bar at its outer end.
    right = base.transform_filter(alt.datum.Leading).mark_text(align="left", dx=4).encode(
        x="Win%:Q", text=alt.Text("Win%:Q", format=".0%"))
    left = base.transform_filter(~alt.datum.Leading).mark_text(align="right", dx=-4).encode(
        x="Win%:Q", text=alt.Text("Win%:Q", format=".0%"))
    return (bars + rule + right + left).properties(height=30 * len(df))


# -- page sections --------------------------------------------------------
def overview(a: Analysis, outlook, odds, plan):
    lg = a.league
    cols = st.columns(4)
    cols[0].metric("Week", f"{lg.current_week} of {lg.end_week}")
    if outlook:
        cols[1].metric("Win chance this week", pct(outlook.win_prob))
    me = next((t for t in odds if t.team_key == a.my_key), None)
    if me:
        cols[2].metric("Playoff odds", pct(me.playoff_prob), help=f"Record {me.record}")
    if plan:
        cols[3].metric("Top pickup", plan[0].add.name, f"{plan[0].gain:+.1f}",
                       help="Gain to your best lineup")


def pickups_tab(a: Analysis, outlook, week_weight):
    unit = "pts/wk" if a.league.is_points else "z-score"
    plan = memo(("plan", week_weight), lambda: plan_moves(a, outlook, week_weight))
    if plan:
        st.subheader("Do this")
        for i, r in enumerate(plan, 1):
            drop = f"drop **{r.drop.name}**" if r.drop else "use your open roster spot"
            st.markdown(f"{i}. Add **{label(r.add)}**, {drop} — gain {r.gain:+.2f} {unit}")
    else:
        st.success("No available player improves your roster right now.")

    recs = memo(("recs", week_weight), lambda: recommend(a, outlook, week_weight, top=15))
    if recs:
        st.subheader("All good pickups")
        st.dataframe(pd.DataFrame([{
            "Add": label(r.add), "Status": r.add.status, "Drop": r.drop.name if r.drop else "—",
            "Gain": r.gain, "This week": r.week_gain, "Rest of season": r.season_gain,
            "Recent adds": r.recent_adds} for r in recs]),
            hide_index=True, width="stretch", column_config={
                "Gain": st.column_config.NumberColumn(format="%+.2f"),
                "This week": st.column_config.NumberColumn(format="%+.2f"),
                "Rest of season": st.column_config.NumberColumn(format="%+.2f"),
                "Recent adds": st.column_config.NumberColumn(
                    help="Times added league-wide recently — a sign of a breakout")})
        st.caption(f"Gain = improvement to your best lineup in {unit}, plus a little "
                   "credit for bench depth. Weighted "
                   f"{week_weight:.0%} this week / {1 - week_weight:.0%} rest of season.")
    weak = drop_candidates(a, 5)
    st.caption("Weakest on your roster: " + ", ".join(f"{p.name} ({v:.1f})" for p, v in weak))


def lineup_tab(a: Analysis):
    adv = lineup_advice(a)
    if adv.moves:
        st.warning("**Lineup changes to make:**\n\n" + "\n".join(f"- {m}" for m in adv.moves))
    else:
        st.success("Your current lineup is already optimal.")
    if adv.injured_active:
        st.error("Injured players taking an active spot (move to IR or drop): " +
                 ", ".join(f"{p.name} [{p.status}]" for p in adv.injured_active))
    if adv.on_bye:
        st.info("On bye this week: " + ", ".join(p.name for p in adv.on_bye))
    unit = "Proj pts/wk" if a.league.is_points else "Value (z)"
    rows = [{"Slot": s, "Player": label(p) if p else "(empty)", "Status": p.status if p else "",
             unit: v if p else None,
             "Now in": (adv.previous.get(p.player_id) or "") if p else ""}
            for s, p, v in adv.lineup.starters]
    rows += [{"Slot": "Bench", "Player": label(p), "Status": p.status, unit: v,
              "Now in": adv.previous.get(p.player_id) or ""} for p, v in adv.lineup.bench]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={unit: st.column_config.NumberColumn(format="%.1f")})


def matchup_tab(a: Analysis, outlook):
    if outlook is None:
        st.info("No head-to-head matchup this week.")
        return
    names = a.team_names
    st.subheader(f"{names.get(outlook.team_key)} vs {names.get(outlook.opp_key)}")
    st.progress(outlook.progress, text=f"{pct(outlook.progress)} of the week played")
    if outlook.points:
        me, opp = outlook.points
        c = st.columns(3)
        c[0].metric("Your projected score", f"{me.mean:.1f}", help=f"± {me.sd:.1f}")
        c[1].metric("Opponent projected", f"{opp.mean:.1f}", help=f"± {opp.sd:.1f}")
        c[2].metric("Win chance", pct(outlook.win_prob),
                    None if outlook.yahoo_win_prob is None
                    else f"Yahoo says {pct(outlook.yahoo_win_prob)}", delta_color="off")
        return
    ea, eb = outlook.expected_cats
    c = st.columns(2)
    c[0].metric("Win chance", pct(outlook.win_prob))
    c[1].metric("Expected category score", f"{ea:.1f} – {eb:.1f}")

    def fmt(v):
        return "—" if v is None else f"{v:.3f}" if abs(v) < 2 else f"{v:.0f}"
    df = pd.DataFrame([{
        "Category": c.name, "You (now)": fmt(c.current[0]), "Opp (now)": fmt(c.current[1]),
        "You (proj)": fmt(c.final[0].mean), "Opp (proj)": fmt(c.final[1].mean),
        "Win%": c.win_prob} for c in outlook.categories])
    st.altair_chart(category_chart(df), width="stretch")
    st.caption("Blue = you're favored, orange = you're behind. Categories near 50% are the "
               "ones worth chasing on the waiver wire this week.")
    st.dataframe(df.assign(**{"Win%": df["Win%"] * 100}), hide_index=True, width="stretch",
                 column_config={"Win%": st.column_config.NumberColumn(format="%.0f%%")})


def playoffs_tab(a: Analysis, odds, sims):
    lg = a.league
    if not lg.is_head_to_head:
        st.info("Not a head-to-head league.")
        return
    if not odds:
        st.info("The regular season is over.")
        return
    df = pd.DataFrame([{
        "Team": t.name + (" (you)" if t.team_key == a.my_key else ""),
        "You": t.team_key == a.my_key, "Record": t.record,
        "Proj. record": f"{t.proj_wins:.1f}–{t.proj_losses:.1f}",
        "Avg seed": t.avg_seed, "Playoffs": t.playoff_prob, "#1 seed": t.top_seed_prob}
        for t in odds])
    st.altair_chart(playoff_chart(df), width="stretch")
    table = df.drop(columns="You").assign(Playoffs=df["Playoffs"] * 100,
                                          **{"#1 seed": df["#1 seed"] * 100})
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "Playoffs": st.column_config.NumberColumn(format="%.0f%%"),
        "#1 seed": st.column_config.NumberColumn(format="%.0f%%"),
        "Avg seed": st.column_config.NumberColumn(format="%.1f")})
    st.caption(f"{sims:,} simulated seasons · {lg.num_playoff_teams} playoff spots · "
               f"playoffs start week {lg.playoff_start_week}")


def free_agents_tab(a: Analysis):
    rows = [{"Player": label(p), "Status": p.status, "This week": w, "Rest of season": s,
             "Owned": p.percent_owned}
            for p, w, s in top_available(a, 40)]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "This week": st.column_config.NumberColumn(format="%.1f"),
        "Rest of season": st.column_config.NumberColumn(format="%.1f"),
        "Owned": st.column_config.NumberColumn(format="%.0f%%")})


# -- main -----------------------------------------------------------------
def main():
    conf = secrets()
    if not password_ok(conf):
        return

    with st.sidebar:
        st.header("Fantasy Optimizer")
        configured = bool(conf.get("yahoo", {}).get("client_id"))
        choice = st.radio("League", list(SOURCES), index=0 if configured else 1)
        demo = SOURCES[choice]
        with st.expander("Settings"):
            recent = st.slider("Weight on recent form", 0.0, 1.0, 0.5, 0.05,
                               help="0 = full season only, 1 = last month only")
            week_weight = st.slider("Pickups: focus on this week", 0.0, 1.0, 0.35, 0.05,
                                    help="Raise for streaming, lower for long-term holds")
            pool = st.select_slider("Free agents to evaluate", [50, 75, 100, 150], 75)
            sims = st.select_slider("Season simulations", [1000, 3000, 10000], 3000)
        if st.button("Refresh data from Yahoo", width="stretch"):
            st.cache_resource.clear()
            st.session_state.pop("memo", None)

    oauth_file, league_key = None, None
    if demo is None:
        if configured and not conf.get("app_password"):
            st.error("Set `app_password` in your secrets before connecting Yahoo, so "
                     "strangers with the link can't see your league.")
            return
        oauth_file = yahoo_oauth_file(conf)
        if not oauth_file:
            return
        show_new_token_notice()
        try:
            leagues = list_leagues(oauth_file)
        except Exception as e:
            st.error(f"Couldn't reach Yahoo: {e}")
            st.session_state.pop("oauth_file", None)
            return
        if not leagues:
            st.warning("No leagues found on this Yahoo account for the current season.")
            return
        keys = [l["league_key"] for l in leagues]
        default = conf.get("yahoo", {}).get("league_key")
        with st.sidebar:
            league_key = st.selectbox(
                "Your league", keys, index=keys.index(default) if default in keys else 0,
                format_func=lambda k: next(f"{l['name']} ({l['game_code'].upper()})"
                                           for l in leagues if l["league_key"] == k))

    try:
        with st.spinner("Crunching your league (first load can take ~30s)…"):
            a = load(demo, league_key, oauth_file, recent, pool)
    except BaseException as e:  # YahooSource raises SystemExit for setup problems
        if isinstance(e, KeyboardInterrupt):
            raise
        st.error(f"Couldn't load the league: {e}")
        return

    st.session_state.setdefault("memo", {})
    if st.session_state.get("memo_owner") != id(a):
        st.session_state.memo, st.session_state.memo_owner = {}, id(a)

    lg = a.league
    st.title(lg.name)
    st.caption(f"{lg.game_code.upper()} {lg.season} · "
               f"{'points' if lg.is_points else 'categories'} · "
               f"Your team: **{a.team_names.get(a.my_key, a.my_key)}**")

    outlook = memo("outlook", lambda: my_outlook(a))
    odds = memo(("odds", sims), lambda: simulate_season(a, sims)
                if lg.is_head_to_head and lg.current_week < lg.playoff_start_week else [])
    plan = memo(("plan", week_weight), lambda: plan_moves(a, outlook, week_weight))
    overview(a, outlook, odds, plan)

    tabs = st.tabs(["Pickups", "Lineup", "Matchup", "Playoff odds", "Free agents"])
    with tabs[0]:
        pickups_tab(a, outlook, week_weight)
    with tabs[1]:
        lineup_tab(a)
    with tabs[2]:
        matchup_tab(a, outlook)
    with tabs[3]:
        playoffs_tab(a, odds, sims)
    with tabs[4]:
        free_agents_tab(a)


main()
