import random

from fantasy_optimizer.matchup import Dist, pairwise, simulate_categories
from fantasy_optimizer.models import LeagueInfo, Player, StatLine
from fantasy_optimizer.projections import project_player


def league(**kw):
    base = dict(league_key="x", name="x", game_code="nfl", season=2026,
                scoring_type="headpoint", num_teams=10, current_week=8, end_week=17,
                playoff_start_week=15, num_playoff_teams=6, weeks_elapsed=7.0,
                categories=[], stat_modifiers={}, roster_slots={"QB": 1},
                my_team_key="t1")
    base.update(kw)
    return LeagueInfo(**base)


def test_projection_blends_recent_form_and_handles_byes():
    p = Player(1, "x", stat_lines={"season": StatLine({}, 70.0, 7.0),
                                   "lastmonth": StatLine({}, 60.0, 4.0)})
    pr = project_player(p, league())
    assert pr.points == 0.5 * 10 + 0.5 * 15
    assert pr.week_factor == 1.0
    p.bye_week = 8
    assert project_player(p, league()).week_factor == 0.0
    p.bye_week, p.status = None, "O"
    pr = project_player(p, league())
    assert pr.week_factor == 0.0 and pr.season_factor == 0.5


def test_points_from_modifiers_when_yahoo_omits_totals():
    p = Player(1, "x", stat_lines={"season": StatLine({4: 2000, 18: 5}, None, 5.0)})
    pr = project_player(p, league(stat_modifiers={4: 0.04, 18: -2}))
    assert abs(pr.points - (80 - 10) / 5) < 1e-9


def test_league_type_detection():
    assert league().is_points
    assert league(scoring_type="head", stat_modifiers={4: 0.04}).is_points
    assert not league(scoring_type="head").is_points
    assert not league(scoring_type="roto").is_head_to_head


def test_pairwise_probability():
    assert abs(pairwise(Dist(100, 10), Dist(100, 10)) - 0.5) < 1e-12
    assert pairwise(Dist(110, 10), Dist(100, 10)) > 0.7
    assert pairwise(Dist(3.0, 0.2), Dist(4.0, 0.2), higher_is_better=False) > 0.99


def test_simulated_category_matchup():
    strong = [(Dist(10, 1), Dist(5, 1), True)] * 5
    p, a, b = simulate_categories(strong, 2000, random.Random(1))
    assert p > 0.99 and a > 4.9 and b < 0.1
    even = [(Dist(5, 1), Dist(5, 1), True)] * 9
    p, _, _ = simulate_categories(even, 4000, random.Random(2))
    assert 0.45 < p < 0.55
