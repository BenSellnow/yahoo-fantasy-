"""Drive YahooSource end to end with canned API responses (no network)."""
import copy
import re

from fantasy_optimizer.analysis import Analysis
from fantasy_optimizer.yahoo_source import YahooSource

from test_yahoo_parsing import SCOREBOARD, SETTINGS


def player_entry(pid, pos, points=None):
    info = [{"player_key": f"461.p.{pid}"}, {"player_id": str(pid)},
            {"name": {"full": f"Player {pid}"}}, {"editorial_team_abbr": "KC"},
            {"position_type": "O"}, {"eligible_positions": [{"position": pos}]}]
    extra = {"percent_owned": [{"coverage_type": "week"}, {"value": "40"}]}
    if points is not None:
        extra = {"player_stats": {"stats": [{"stat": {"stat_id": "4", "value": "100"}}]},
                 "player_points": {"total": str(points)}}
    return {"player": [info, extra]}


def players_page(entries):
    coll = {str(i): e for i, e in enumerate(entries)}
    coll["count"] = len(entries)
    return {"fantasy_content": {"league": [{}, {"players": coll}]}}


class FakeTeam:
    def __init__(self, ids):
        self.ids = ids

    def roster(self):
        return [{"player_id": pid, "name": f"Player {pid}", "position_type": "O",
                 "eligible_positions": [pos], "selected_position": pos if i < 3 else "BN",
                 "status": "", "editorial_team_abbr": "KC"}
                for i, (pid, pos) in enumerate(self.ids)]


class FakeLeague:
    rosters = {"461.l.99.t.1": [(1, "QB"), (2, "WR"), (3, "WR"), (4, "WR")],
               "461.l.99.t.2": [(5, "QB"), (6, "WR"), (7, "WR"), (8, "QB")]}

    def team_key(self):
        return "461.l.99.t.1"

    def teams(self):
        return {k: {"name": k[-3:]} for k in self.rosters}

    def to_team(self, key):
        return FakeTeam(self.rosters[key])

    def standings(self):
        return [{"team_key": k, "name": k[-3:], "points_for": "500",
                 "outcome_totals": {"wins": "4", "losses": "3", "ties": 0}}
                for k in self.rosters]


def make_source():
    src = YahooSource.__new__(YahooSource)
    src.league_key = "461.l.99"
    src._lg = FakeLeague()
    src._info = None
    calls = []

    def get(uri, ttl=None):
        calls.append(uri)
        if uri.endswith("/settings"):
            return SETTINGS
        if "/scoreboard" in uri:
            return copy.deepcopy(SCOREBOARD)
        if "transactions" in uri:
            return players_page([])
        m = re.search(r"player_keys=([^/]+)/stats;type=(\w+)", uri)
        if m:
            ids = [int(k.split(".")[-1]) for k in m.group(1).split(",")]
            return players_page([player_entry(i, "WR", 10.0 * i) for i in ids])
        if "status=A" in uri:
            start = int(re.search(r"start=(\d+)", uri).group(1))
            return players_page([player_entry(100 + start + i, "WR") for i in range(3)]
                                if start == 0 else [])
        raise AssertionError(uri)

    src.get = get
    return src, calls


def test_yahoo_source_feeds_the_analysis():
    src, calls = make_source()
    a = Analysis.load(src)
    assert a.league.is_points and a.league.my_team_key == "461.l.99.t.1"
    assert set(a.rosters) == set(FakeLeague.rosters)
    # Every rostered and available player got season stats.
    for p in [p for r in a.rosters.values() for p in r] + a.available:
        assert "season" in p.stat_lines
    assert a.available[0].percent_owned == 40.0
    # Rostered players' stats were fetched in one batch per timeframe.
    batched = [c for c in calls if "player_keys=" in c and "461.p.1," in c]
    assert len(batched) == 2
    lu = a.best_lineup(a.my_roster)
    assert lu.starters[0][1].player_id == 1
