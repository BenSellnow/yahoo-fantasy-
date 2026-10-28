import pytest

from fantasy_optimizer.analysis import Analysis
from fantasy_optimizer.cli import COMMANDS, main
from fantasy_optimizer.demo import DemoSource
from fantasy_optimizer.matchup import my_outlook
from fantasy_optimizer.playoffs import simulate_season
from fantasy_optimizer.waivers import plan_moves, recommend


@pytest.mark.parametrize("sport", ["nfl", "nba"])
@pytest.mark.parametrize("command", COMMANDS)
def test_cli_commands_run(sport, command, capsys):
    main(["--demo", sport, command, "--sims", "200"])
    out = capsys.readouterr().out
    assert "Your team:" in out


@pytest.mark.parametrize("sport", ["nfl", "nba"])
def test_analysis_outputs_are_sane(sport):
    a = Analysis.load(DemoSource(sport))
    o = my_outlook(a)
    assert 0 <= o.win_prob <= 1

    odds = simulate_season(a, sims=300)
    assert len(odds) == a.league.num_teams
    assert abs(sum(t.playoff_prob for t in odds) - a.league.num_playoff_teams) < 1e-9
    assert abs(sum(t.top_seed_prob for t in odds) - 1) < 1e-9

    recs = recommend(a, o)
    assert all(r.gain > 0 for r in recs)
    assert recs == sorted(recs, key=lambda r: -r.gain)
    roster_ids = {p.player_id for p in a.my_roster}
    assert all(r.add.player_id not in roster_ids for r in recs)
    assert all(r.drop is None or r.drop.player_id in roster_ids for r in recs)

    plan = plan_moves(a, o)
    drops = [r.drop.player_id for r in plan if r.drop]
    assert len(drops) == len(set(drops))
    assert len({r.add.player_id for r in plan}) == len(plan)


def test_lineup_never_starts_out_or_bye_players():
    a = Analysis.load(DemoSource("nfl"))
    for key, roster in a.rosters.items():
        lu = a.best_lineup(roster, "week")
        for _, p, _ in lu.starters:
            if p:
                assert a.proj[p.player_id].week_factor > 0
