import itertools
import random

from fantasy_optimizer.lineup import hungarian_max, optimize_lineup
from fantasy_optimizer.models import Player


def test_hungarian_matches_brute_force():
    rng = random.Random(1)
    for n in range(1, 7):
        for _ in range(20):
            w = [[rng.uniform(-5, 10) for _ in range(n)] for _ in range(n)]
            best = max(sum(w[i][p[i]] for i in range(n))
                       for p in itertools.permutations(range(n)))
            a = hungarian_max(w)
            assert sorted(a) == list(range(n))
            assert abs(sum(w[i][a[i]] for i in range(n)) - best) < 1e-9


def P(pid, *pos):
    return Player(pid, f"p{pid}", positions=list(pos))


def test_flex_goes_to_best_leftover():
    players = [P(1, "RB", "W/R/T"), P(2, "RB", "W/R/T"), P(3, "WR", "W/R/T"),
               P(4, "TE", "W/R/T"), P(5, "QB")]
    values = {1: 15, 2: 12, 3: 10, 4: 9, 5: 20}
    lu = optimize_lineup(players, ["QB", "RB", "WR", "W/R/T"], values)
    got = {slot: p.player_id for slot, p, _ in lu.starters}
    assert got == {"QB": 5, "RB": 1, "WR": 3, "W/R/T": 2}
    assert [p.player_id for p, _ in lu.bench] == [4]


def test_unstartable_player_is_benched_and_slot_left_empty():
    players = [P(1, "QB"), P(2, "WR")]
    lu = optimize_lineup(players, ["QB", "WR"], {1: 30, 2: 5}, startable={1: False})
    assert lu.starters[0][1] is None
    assert lu.starters[1][1].player_id == 2
    assert lu.bench[0][0].player_id == 1


def test_composite_slots_without_explicit_eligibility():
    assert P(1, "PG").can_fill("G")
    assert P(1, "PF").can_fill("F")
    assert not P(1, "C").can_fill("G")
    assert P(1, "SS").can_fill("Util")
    assert not P(1, "SP").can_fill("Util")
