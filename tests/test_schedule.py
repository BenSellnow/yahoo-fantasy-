import datetime as dt

from fantasy_optimizer.analysis import Analysis
from fantasy_optimizer.demo import DemoSource
from fantasy_optimizer.lineup import optimize_lineup
from fantasy_optimizer.models import Player
from fantasy_optimizer.schedule import Schedule, normalize, parse_nba_schedule

# Shaped like https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json
NBA_JSON = {"leagueSchedule": {"seasonYear": "2026-27", "gameDates": [
    {"gameDate": "10/10/2026 00:00:00", "games": [  # preseason, ignored
        {"gameId": "0012600001", "homeTeam": {"teamTricode": "LAL"},
         "awayTeam": {"teamTricode": "GSW"}}]},
    {"gameDate": "10/27/2026 00:00:00", "games": [
        {"gameId": "0022600001", "homeTeam": {"teamTricode": "LAL"},
         "awayTeam": {"teamTricode": "GSW"}},
        {"gameId": "0022600002", "homeTeam": {"teamTricode": "BOS"},
         "awayTeam": {"teamTricode": "NYK"}}]},
    {"gameDate": "10/29/2026 00:00:00", "games": [
        {"gameId": "0022600003", "homeTeam": {"teamTricode": "GSW"},
         "awayTeam": {"teamTricode": "PHX"}}]},
]}}


def test_parse_nba_schedule_and_yahoo_abbreviations():
    s = parse_nba_schedule(NBA_JSON)
    assert s.teams == {"LAL", "GSW", "BOS", "NYK", "PHX"}
    assert normalize("GS") == "GSW" and normalize("pho") == "PHX"
    # Yahoo's "GS" and "NY" resolve to NBA tricodes.
    assert s.games_between("GS", dt.date(2026, 10, 26), dt.date(2026, 11, 1)) == 2
    assert s.plays_on("NY", dt.date(2026, 10, 27))
    assert not s.plays_on("NY", dt.date(2026, 10, 29))
    assert not s.plays_on("LAL", dt.date(2026, 10, 10))  # preseason skipped


def test_empty_slot_never_beats_a_real_player():
    bad = Player(1, "bad", positions=["C"])
    with_him = optimize_lineup([bad], ["C", "PG"], {1: -4.0})
    assert with_him.starters[0][1] is bad
    without = optimize_lineup([], ["C", "PG"], {}, empty_value=with_him.empty_value)
    assert with_him.starter_value > without.starter_value


def demo_on(day):
    return Analysis.load(DemoSource("nba", today=day), today=day)


def test_daily_lineup_only_starts_players_with_a_game_today():
    day = dt.date(2026, 10, 28)
    a = demo_on(day)
    assert a.lineup_horizon == "today"
    for _, p, _ in a.best_lineup(a.my_roster, "today").starters:
        if p:
            assert a.schedule.plays_on(p.team_abbr, day)


def test_remaining_output_shrinks_as_the_week_goes_on():
    monday, sunday = dt.date(2026, 10, 26), dt.date(2026, 11, 1)
    early = demo_on(monday)
    late = demo_on(sunday)
    key = early.my_key
    pts = 12  # PTS stat id
    assert early.team_remaining_output(key)[pts] > late.team_remaining_output(key)[pts]
    for p in early.my_roster:
        g = early.proj[p.player_id].games_left
        assert g == early.schedule.games_between(p.team_abbr, monday, sunday)
