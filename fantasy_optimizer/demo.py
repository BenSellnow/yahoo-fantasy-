"""A synthetic league so the tool can be tried (and tested) without Yahoo.

``DemoSource`` implements the same interface as ``YahooSource``. Two flavours
are available: an NFL head-to-head points league and an NBA head-to-head
categories league.
"""
from __future__ import annotations

import random

from .lineup import optimize_lineup
from .models import (Category, LeagueInfo, Matchup, Player, StandingsRow,
                     StatLine, TeamWeek)

TEAM_NAMES = [
    "Gridiron Gurus", "Waiver Wire Warriors", "The Replacements",
    "Bench Mob", "Sleeper Cell", "Fourth & Long", "Trade Bait",
    "Couch Commish", "Punt Intended", "Monday Night Miracle",
]
PRO_TEAMS = ["ATL", "BOS", "CHI", "DAL", "DEN", "DET", "GB", "HOU", "KC",
             "LA", "MIA", "MIN", "NY", "PHI", "SEA", "SF"]
FIRST = ["Alex", "Jordan", "Chris", "Marcus", "Tyler", "Devon", "Jalen",
         "Cam", "Isaiah", "Malik", "Trey", "Nico", "Andre", "Luka", "Zion"]
LAST = ["Johnson", "Williams", "Brown", "Davis", "Miller", "Moore", "Jackson",
        "White", "Harris", "Martin", "Thompson", "Allen", "Young", "King"]

NBA_CATS = [
    Category(5, "FG%", "P", True, True), Category(8, "FT%", "P", True, True),
    Category(10, "3PTM", "P"), Category(12, "PTS", "P"), Category(15, "REB", "P"),
    Category(16, "AST", "P"), Category(17, "ST", "P"), Category(18, "BLK", "P"),
    Category(19, "TO", "P", False),
]
NFL_POS = {"QB": (17, 4, 32), "RB": (10, 4.5, 70), "WR": (10, 4.5, 90),
           "TE": (6.5, 3, 35), "K": (8, 1.5, 32), "DEF": (7, 2.5, 32)}
NBA_POS = ["PG", "SG", "SF", "PF", "C"]


def round_robin(team_keys: list[str], weeks: int) -> list[list[tuple[str, str]]]:
    """Circle-method schedule, repeating once every team has met."""
    keys = list(team_keys) + ([None] if len(team_keys) % 2 else [])
    n = len(keys)
    sched = []
    for w in range(weeks):
        r = w % (n - 1)
        rot = [keys[0]] + (keys[1:][-r:] + keys[1:][:-r] if r else keys[1:])
        sched.append([(rot[i], rot[n - 1 - i]) for i in range(n // 2)
                      if rot[i] and rot[n - 1 - i]])
    return sched


class DemoSource:
    def __init__(self, sport: str = "nfl", seed: int = 7):
        self.sport = sport
        self.rng = random.Random(seed)
        self.n_teams = 10
        self.team_keys = [f"demo.l.1.t.{i + 1}" for i in range(self.n_teams)]
        self.names = dict(zip(self.team_keys, TEAM_NAMES))
        if sport == "nfl":
            self.info = LeagueInfo(
                league_key="demo.l.1", name="Demo Points League", game_code="nfl",
                season=2026, scoring_type="headpoint", num_teams=self.n_teams,
                current_week=8, end_week=17, playoff_start_week=15,
                num_playoff_teams=6, weeks_elapsed=7.0, categories=[],
                stat_modifiers={}, my_team_key=self.team_keys[0],
                roster_slots={"QB": 1, "WR": 2, "RB": 2, "TE": 1, "W/R/T": 1,
                              "K": 1, "DEF": 1, "BN": 6, "IR": 1})
        elif sport == "nba":
            self.info = LeagueInfo(
                league_key="demo.l.2", name="Demo Categories League", game_code="nba",
                season=2026, scoring_type="head", num_teams=self.n_teams,
                current_week=2, end_week=20, playoff_start_week=18,
                num_playoff_teams=4, weeks_elapsed=1.2, categories=NBA_CATS,
                stat_modifiers={}, my_team_key=self.team_keys[0],
                roster_slots={"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1,
                              "C": 2, "Util": 2, "BN": 3, "IL": 2})
        else:
            raise ValueError("demo sport must be 'nfl' or 'nba'")
        self.schedule = round_robin(self.team_keys, self.info.playoff_start_week - 1)
        self._players: list[Player] = []
        self._talent: dict[int, dict] = {}
        self._make_players()
        self._draft()
        self._history = self._simulate_history()

    # -- generation ------------------------------------------------------
    def _name(self):
        return f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"

    def _status(self):
        r = self.rng.random()
        return "O" if r < 0.02 else "IR" if r < 0.03 else "Q" if r < 0.09 else ""

    def _make_players(self):
        pid = 1000
        if self.sport == "nfl":
            for pos, (mean, sd, n) in NFL_POS.items():
                for i in range(n):
                    pid += 1
                    talent = max(1.0, mean + sd * 1.8 - (i / n) * sd * 3.2 +
                                 self.rng.gauss(0, sd * 0.4))
                    elig = [pos] + (["W/R/T"] if pos in ("RB", "WR", "TE") else [])
                    name = f"{self.rng.choice(PRO_TEAMS)} D/ST" if pos == "DEF" else self._name()
                    p = Player(pid, name, self.rng.choice(PRO_TEAMS), elig,
                               "DT" if pos == "DEF" else "K" if pos == "K" else "O",
                               self._status(), bye_week=self.rng.randint(5, 14))
                    self._talent[pid] = {"points": talent,
                                         "form": self.rng.gauss(0, 0.15)}
                    self._players.append(p)
        else:
            for i in range(220):
                pid += 1
                t = 2.2 - (i / 220) * 3.5 + self.rng.gauss(0, 0.4)
                main = self.rng.choice(NBA_POS)
                idx = NBA_POS.index(main)
                elig = {main}
                if self.rng.random() < 0.5 and idx < 4:
                    elig.add(NBA_POS[idx + 1])
                if elig & {"PG", "SG"}:
                    elig.add("G")
                if elig & {"SF", "PF"}:
                    elig.add("F")
                elig.add("Util")
                big = idx / 4  # 0 for PG, 1 for C
                gpw = 3.4
                rates = {
                    12: max(4, 13 + 5.5 * t), 15: max(1.5, 3 + 6 * big + 1.6 * t),
                    16: max(0.5, 1 + 5 * (1 - big) + 1.3 * t), 17: max(0.2, 0.8 + 0.25 * t),
                    18: max(0.05, 0.2 + 1.2 * big + 0.3 * t), 10: max(0, 1.6 * (1 - big) + 0.5 * t),
                    19: max(0.5, 1.4 + 0.5 * t), "fg": 0.44 + 0.07 * big + self.rng.gauss(0, 0.025),
                    "ft": 0.80 - 0.1 * big + self.rng.gauss(0, 0.05),
                }
                p = Player(pid, self._name(), self.rng.choice(PRO_TEAMS),
                           sorted(elig), "P", self._status())
                self._talent[pid] = {"rates": rates, "gpw": gpw,
                                     "form": self.rng.gauss(0, 0.12)}
                self._players.append(p)
        for p in self._players:
            p.stat_lines = self._stat_lines(p)

    def _week_line(self, p, weeks, form):
        t = self._talent[p.player_id]
        noise = lambda: max(0.0, self.rng.gauss(1 + form, 0.12 / max(weeks, 0.3) ** 0.5))
        if self.sport == "nfl":
            return StatLine({}, round(t["points"] * weeks * noise(), 1), weeks)
        r, games = t["rates"], t["gpw"] * weeks
        stats = {sid: round(r[sid] * games * noise(), 0) for sid in (10, 12, 15, 16, 17, 18, 19)}
        stats[5] = round(min(0.7, max(0.3, r["fg"] + self.rng.gauss(0, 0.03 / weeks ** 0.5))), 3)
        stats[8] = round(min(1.0, max(0.4, r["ft"] + self.rng.gauss(0, 0.06 / weeks ** 0.5))), 3)
        return StatLine(stats, None, weeks)

    def _stat_lines(self, p):
        w = self.info.weeks_elapsed
        form = self._talent[p.player_id]["form"]
        return {"season": self._week_line(p, w, form / 2),
                "lastmonth": self._week_line(p, min(30 / 7, w), form)}

    def _rough_value(self, p):
        t = self._talent[p.player_id]
        if self.sport == "nfl":
            return t["points"] * (1.4 if p.positions[0] in ("QB", "RB", "WR") else 0.9)
        r = t["rates"]
        return r[12] + r[15] + r[16] * 1.5 + (r[17] + r[18]) * 3 + r[10]

    def _draft(self):
        slots = self.info.starting_slots()
        bench = self.info.roster_slots.get("BN", 0)
        size = len(slots) + bench
        pool = sorted(self._players, key=lambda p: -self._rough_value(p))
        rosters = {k: [] for k in self.team_keys}
        order = self.team_keys
        rnd = 0
        while any(len(r) < size for r in rosters.values()):
            for k in (order if rnd % 2 == 0 else list(reversed(order))):
                roster = rosters[k]
                if len(roster) >= size:
                    continue
                # Fill each starting slot once, then take best available.
                open_slots = list(slots)
                for p in roster:
                    for s in open_slots:
                        if p.can_fill(s):
                            open_slots.remove(s)
                            break
                pick = None
                for p in pool:
                    if len(roster) < len(slots) and not any(p.can_fill(s) for s in open_slots):
                        continue
                    if self.sport == "nfl" and p.positions[0] in ("K", "DEF") and \
                            sum(q.positions[0] == p.positions[0] for q in roster) >= 1:
                        continue
                    pick = p
                    break
                pick = pick or pool[0]
                pool.remove(pick)
                pick.owner_key = k
                roster.append(pick)
            rnd += 1
        self._rosters = rosters
        for k, roster in rosters.items():
            vals = {p.player_id: self._rough_value(p) for p in roster}
            lu = optimize_lineup(roster, slots, vals)
            for slot, p, _ in lu.starters:
                if p:
                    p.selected_position = slot
            for p, _ in lu.bench:
                p.selected_position = "BN"
        self._free = pool

    def _team_week(self, key, week, scale=1.0):
        roster = [p for p in self._rosters[key] if p.selected_position not in ("BN", None)]
        if self.sport == "nfl":
            mean = sum(self._talent[p.player_id]["points"] for p in roster)
            return TeamWeek(key, week, {}, round(max(0, self.rng.gauss(mean, mean * 0.17)) * scale, 2))
        stats = {}
        for sid in (10, 12, 15, 16, 17, 18, 19):
            mean = sum(self._talent[p.player_id]["rates"][sid] * 3.4 for p in roster)
            stats[sid] = round(max(0, self.rng.gauss(mean, mean * 0.15 + 1)) * scale)
        for sid, k in ((5, "fg"), (8, "ft")):
            mean = sum(self._talent[p.player_id]["rates"][k] for p in roster) / len(roster)
            stats[sid] = round(self.rng.gauss(mean, 0.02), 3)
        return TeamWeek(key, week, stats)

    def _simulate_history(self):
        hist = {}
        for week in range(1, self.info.current_week + 1):
            live = week == self.info.current_week
            ms = []
            for a, b in self.schedule[week - 1]:
                ta, tb = self._team_week(a, week, 0.55 if live else 1), \
                    self._team_week(b, week, 0.55 if live else 1)
                if live and self.sport == "nfl":
                    for t in (ta, tb):
                        t.projected_points = round(t.points / 0.55 * self.rng.uniform(0.92, 1.08), 2)
                ms.append(Matchup(week, "midevent" if live else "postevent",
                                  None, None, (ta, tb)))
            hist[week] = ms
        for week in range(self.info.current_week + 1, len(self.schedule) + 1):
            hist[week] = [Matchup(week, "preevent", None, None,
                                  (TeamWeek(a, week, {}), TeamWeek(b, week, {})))
                          for a, b in self.schedule[week - 1]]
        return hist

    # -- DataSource interface --------------------------------------------
    def league_info(self) -> LeagueInfo:
        return self.info

    def teams(self):
        return dict(self.names)

    def roster(self, team_key):
        return list(self._rosters[team_key])

    def all_rosters(self):
        return {k: list(v) for k, v in self._rosters.items()}

    def available_players(self, limit=75, per_position=10):
        return list(self._free)

    def scoreboard(self, week=None):
        return self._history.get(week or self.info.current_week, [])

    def standings(self):
        rows = {k: StandingsRow(k, self.names[k], 0, 0, 0, 0.0) for k in self.team_keys}
        for week in range(1, self.info.current_week):
            for m in self._history[week]:
                a, b = m.teams
                if self.sport == "nfl":
                    rows[a.team_key].points_for += a.points
                    rows[b.team_key].points_for += b.points
                    res = [(a, b)] if a.points > b.points else [(b, a)]
                else:
                    res = []
                    for c in NBA_CATS:
                        va, vb = a.stats[c.stat_id], b.stats[c.stat_id]
                        if va == vb:
                            rows[a.team_key].ties += 1
                            rows[b.team_key].ties += 1
                        elif (va > vb) == c.higher_is_better:
                            res.append((a, b))
                        else:
                            res.append((b, a))
                for w, l in res:
                    rows[w.team_key].wins += 1
                    rows[l.team_key].losses += 1
        return sorted(rows.values(), key=lambda r: (-r.wins, -r.points_for))

    def recent_adds(self, count=100):
        hot = sorted(self._free, key=lambda p: -self._talent[p.player_id]["form"])[:8]
        return {p.player_id: self.rng.randint(1, 4) for p in hot}
