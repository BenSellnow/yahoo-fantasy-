# Yahoo Fantasy Optimizer

A web app and command-line assistant for Yahoo Fantasy Sports leagues (NFL, NBA, NHL, MLB), built on
[`yahoo_fantasy_api`](https://yahoo-fantasy-api.readthedocs.io/en/latest/introduction.html).
Every week it tells you:

| Command | What you get |
| --- | --- |
| `fantasy report` | Everything below, in one weekly report |
| `fantasy waivers` | The best add/drop moves, ranked by how much they improve your **optimal lineup**, plus a multi-move plan that works together |
| `fantasy lineup` | Optimal start/sit for this week (accounts for injuries and NFL byes) with the exact moves to make |
| `fantasy matchup` | Win probability for this week's head-to-head matchup (points or per-category) |
| `fantasy playoffs` | Playoff odds, #1-seed odds and projected final records from a season simulation |
| `fantasy available` | Top available players for this week and rest of season |

Works for head-to-head **points** leagues, head-to-head **categories** leagues, and (for
lineup/waivers) rotisserie leagues.

## Web app

There's a web front end (`streamlit_app.py`) with a dashboard showing your win chance,
playoff odds and top pickup, plus tabs for **Pickups**, **Lineup**, **Matchup**,
**Playoff odds** and **Free agents**. Settings sliders control recent form, this week vs.
rest of season, and so on.

```bash
pip install -e ".[web]"
streamlit run streamlit_app.py      # opens http://localhost:8501 — demo leagues work right away
```

### Host it for free (Streamlit Community Cloud)

1. **Deploy**: sign in at <https://share.streamlit.io> with GitHub → *Create app* → pick this
   repo, branch `master`, main file `streamlit_app.py`. Under *Advanced settings*, choose
   Python 3.12. You get a URL like `https://your-app-name.streamlit.app`. The demo leagues
   work immediately.
2. **Create a Yahoo app** at <https://developer.yahoo.com/apps/create/>:
   - Redirect URI: your exact app URL, e.g. `https://your-app-name.streamlit.app`
   - API permissions: **Fantasy Sports → Read**
3. **Add secrets**: in Streamlit Cloud open your app → *Settings* → *Secrets* and paste
   (template in `.streamlit/secrets.toml.example`):
   ```toml
   app_password = "pick-something-long"   # required: keeps strangers out of your league

   [yahoo]
   client_id = "..."
   client_secret = "..."
   redirect_uri = "https://your-app-name.streamlit.app"
   ```
4. **Connect**: open the app, enter your password, choose *My Yahoo league*, click
   **Connect Yahoo** and approve. The app then shows a `refresh_token = "..."` line. Add it
   under `[yahoo]` in Secrets so you stay logged in when the app restarts. (Already ran
   `fantasy auth` locally? You can instead copy `refresh_token` from your `oauth2.json`.)
   Optionally add `league_key = "..."` to pick your default league.

Free-tier notes: the app goes to sleep after a few days without visitors and wakes up on
the next visit (about 30 seconds). Data is cached for 30 minutes; use **Refresh data from
Yahoo** in the sidebar to pull fresh data. You can also make the app private and invite
specific viewers under *Settings → Sharing*.

## Try it right now (no Yahoo account needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
fantasy --demo nfl report     # H2H points football league
fantasy --demo nba report     # H2H 9-category basketball league
```

## Connect your Yahoo league

1. **Create a Yahoo app** at <https://developer.yahoo.com/apps/create/>
   - Application type: *Installed Application*
   - Redirect URI: `oob` (or `https://localhost:8080`)
   - API permissions: **Fantasy Sports → Read** (Read/Write is only needed if you later want to
     automate transactions)
2. **Authenticate** (opens a browser; paste the verifier code back into the terminal):
   ```bash
   fantasy auth
   ```
   This writes `oauth2.json` (git-ignored, keep it private). Tokens refresh automatically.
3. **Find your league key**:
   ```bash
   fantasy leagues
   export YAHOO_LEAGUE_KEY=461.l.123456   # use your key from the list
   ```
4. **Run the weekly report**:
   ```bash
   fantasy report
   ```

### Useful options

```
fantasy --league 461.l.123456 waivers --top 15
fantasy --recent-weight 0.7 waivers        # trust last month's form more than the full season
fantasy waivers --week-weight 0.8          # streaming mode: care mostly about THIS week
fantasy --pool 150 waivers                 # evaluate more free agents (more API calls)
fantasy playoffs --sims 10000
fantasy --cache-ttl 0 report               # bypass the 30-minute API cache
```

Run it every week, for example from cron on Tuesday after waivers clear:
`0 9 * * 2 cd ~/yahoo-fantasy- && .venv/bin/fantasy report > report.txt`.

## How it works

**Projections** (`projections.py`): each player's weekly rate is a 50/50 blend of their full
season and their last month (`--recent-weight`), pulled straight from Yahoo with your league's
own fantasy-point scoring. Injury status scales expected playing time (Out/IR = 0 this week, Q ≈
80%); NFL bye weeks zero out the current week.

**Player value** (`valuation.py`):
- *Points leagues*: projected fantasy points per week.
- *Category leagues*: sum of per-category z-scores against every rostered player in the league
  at the same position type (hitters vs pitchers, skaters vs goalies). Negative categories (TO,
  ERA, WHIP, GAA) are flipped, and ratio categories (FG%, AVG…) are scaled by playing time so a
  low-minute player's hot shooting doesn't look elite.

**Lineup optimizer** (`lineup.py`): an exact assignment (Hungarian algorithm) of players to
roster slots, so flex spots (W/R/T, Util, G/F, etc.) are always filled optimally.

**Waiver recommendations** (`waivers.py`): for each top available player, try dropping each
player on your roster, re-optimize your lineup, and measure the gain. The score blends this
week (35%) with the rest of the season (65%). In category leagues, this week's value is tilted
toward categories that are still contested in your current matchup — the ones you can actually
swing. Recent league-wide adds are flagged 🔥.

**Matchup odds** (`matchup.py`): what has already happened this week plus each lineup's
projected output for the rest of the week, modeled as normal distributions. Points leagues use
Yahoo's own live projected totals when available (Yahoo's win probability is shown alongside
for comparison). Category leagues are Monte Carlo simulated across all categories together.

**Playoff odds** (`playoffs.py`): each team's weekly output blends its actual results so far
with what its *current* roster projects to (history dominates after a few weeks), adds
season-long strength uncertainty, then simulates the remaining schedule thousands of times.
Correctly handles both per-category records and one-win-per-matchup category leagues.

## Limitations

- Projections come from past production, not from Yahoo's or experts' forward-looking
  projections, so they won't anticipate role changes (a backup becoming a starter) until they
  show up in the stats. The 🔥 trend flag helps catch those early.
- NBA/NHL/MLB lineups are optimized for the week as a whole, not day by day, and the number of
  games each pro team plays in a given week isn't modeled.
- Free agents vs. players on waivers are not distinguished, and FAAB bids aren't suggested.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

The `DemoSource` in `fantasy_optimizer/demo.py` implements the same interface as the live
`YahooSource`, so every feature can be exercised offline.
