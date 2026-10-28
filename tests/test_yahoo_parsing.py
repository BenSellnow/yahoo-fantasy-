"""Parsers against hand-built payloads shaped like Yahoo's JSON responses."""
import datetime as dt

from fantasy_optimizer.yahoo_source import (parse_player, parse_players,
                                            parse_scoreboard, parse_settings)

SETTINGS = {"fantasy_content": {"league": [
    {"league_key": "461.l.99", "league_id": "99", "name": "Office League",
     "current_week": 8, "start_date": "2026-09-08", "end_date": "2026-12-28",
     "end_week": "17", "game_code": "nfl", "season": "2026",
     "scoring_type": "head", "num_teams": 10},
    {"settings": [{
        "playoff_start_week": "15", "num_playoff_teams": "6", "uses_playoff": "1",
        "roster_positions": [
            {"roster_position": {"position": "QB", "position_type": "O", "count": 1}},
            {"roster_position": {"position": "WR", "position_type": "O", "count": "2"}},
            {"roster_position": {"position": "BN", "count": 5}},
        ],
        "stat_categories": {"stats": [
            {"stat": {"stat_id": 4, "enabled": "1", "display_name": "Pass Yds",
                      "sort_order": "1", "position_type": "O"}},
            {"stat": {"stat_id": 18, "enabled": "1", "display_name": "Int",
                      "sort_order": "0", "position_type": "O"}},
            {"stat": {"stat_id": 99, "enabled": "1", "display_name": "Shown",
                      "sort_order": "1", "is_only_display_stat": "1"}},
        ]},
        "stat_modifiers": {"stats": [
            {"stat": {"stat_id": 4, "value": "0.04"}},
            {"stat": {"stat_id": 18, "value": "-2"}},
        ]},
    }]},
]}}


def test_parse_settings():
    s = parse_settings(SETTINGS, today=dt.date(2026, 10, 27))
    assert s["league_key"] == "461.l.99"
    assert s["roster_slots"] == {"QB": 1, "WR": 2, "BN": 5}
    assert [c.name for c in s["categories"]] == ["Pass Yds", "Int"]
    assert s["categories"][1].higher_is_better is False
    assert s["stat_modifiers"] == {4: 0.04, 18: -2.0}
    assert s["playoff_start_week"] == 15
    assert s["weeks_elapsed"] == 7.8  # Tuesday: week 8's games are mostly done


PLAYERS = {"fantasy_content": {"league": [{"league_key": "461.l.99"}, {"players": {
    "0": {"player": [
        [{"player_key": "461.p.33"}, {"player_id": "33"},
         {"name": {"full": "Some Receiver"}}, [], {"status": "Q"},
         {"editorial_team_abbr": "KC"}, {"bye_weeks": {"week": "10"}},
         {"position_type": "O"},
         {"eligible_positions": [{"position": "WR"}, {"position": "W/R/T"}]}],
        {"player_stats": {"0": {"coverage_type": "season"}, "stats": [
            {"stat": {"stat_id": "0", "value": "7"}},
            {"stat": {"stat_id": "12", "value": "612"}},
            {"stat": {"stat_id": "13", "value": "-"}}]},
         "player_points": {"coverage_type": "season", "total": "98.4"}},
    ]},
    "count": 1}}]}}


def test_parse_player_with_stats():
    entries = parse_players(PLAYERS)
    assert len(entries) == 1
    p = parse_player(entries[0], weeks=7.0)
    assert (p.player_id, p.name, p.status, p.team_abbr, p.bye_week) == \
        (33, "Some Receiver", "Q", "KC", 10)
    assert p.positions == ["WR", "W/R/T"]
    line = p.stat_lines["season"]
    assert line.stats == {0: 7.0, 12: 612.0}
    assert line.points == 98.4 and line.weeks == 7.0


def _team(key, points, proj, stats):
    return {"team": [
        [{"team_key": key}, {"team_id": key[-1]}, {"name": key}],
        {"team_points": {"coverage_type": "week", "total": points},
         "team_projected_points": {"total": proj},
         "win_probability": 0.61,
         "team_stats": {"stats": [{"stat": {"stat_id": sid, "value": v}}
                                  for sid, v in stats.items()]}},
    ]}


SCOREBOARD = {"fantasy_content": {"league": [{"league_key": "461.l.99"}, {"scoreboard": {
    "week": 8, "0": {"matchups": {
        "0": {"matchup": {"week": "8", "week_start": "2026-10-22",
                          "week_end": "2026-10-26", "status": "midevent",
                          "0": {"teams": {"0": _team("461.l.99.t.1", "77.5", "120.2", {"5": ".455"}),
                                          "1": _team("461.l.99.t.2", "60.1", "110.0", {"5": "-"}),
                                          "count": 2}}}},
        "count": 1}}}}]}}


def test_parse_scoreboard():
    [m] = parse_scoreboard(SCOREBOARD)
    assert m.week == 8 and m.status == "midevent"
    a, b = m.teams
    assert a.team_key == "461.l.99.t.1" and a.points == 77.5
    assert a.projected_points == 120.2 and a.win_probability == 0.61
    assert a.stats == {5: 0.455} and b.stats == {}
    assert m.opponent_of("461.l.99.t.2") is a
