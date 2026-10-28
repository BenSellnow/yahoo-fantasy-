"""Optimal lineup assignment (players to roster slots).

This is a weighted bipartite matching problem, solved exactly with the
Hungarian algorithm. Rosters are small, so a pure-Python O(n^3) solver is
instant.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Player

BENCH_WEIGHT = 0.15
_FORBIDDEN = -1e9


def hungarian_max(weights: list[list[float]]) -> list[int]:
    """Return assignment[row] = column maximising the total weight.

    ``weights`` must be square.
    """
    n = len(weights)
    if n == 0:
        return []
    big = max(max(r) for r in weights)
    cost = [[big - w for w in row] for row in weights]
    INF = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = [0] * n
    for j in range(1, n + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment


@dataclass
class Lineup:
    starters: list[tuple[str, Player | None, float]]  # (slot, player, value)
    bench: list[tuple[Player, float]]

    @property
    def starter_value(self) -> float:
        return sum(v for _, p, v in self.starters if p is not None)

    @property
    def score(self) -> float:
        """Starter value plus a little credit for bench depth."""
        return self.starter_value + BENCH_WEIGHT * sum(max(v, 0) for _, v in self.bench)


def optimize_lineup(players: list[Player], slots: list[str],
                    values: dict[int, float],
                    startable: dict[int, bool] | None = None) -> Lineup:
    """Pick the best starter for each slot.

    ``startable`` marks players who can actually play (not out or on bye);
    those that cannot are only placed in a slot if nobody else fits, which
    never adds value.
    """
    startable = startable or {}
    n = max(len(players), len(slots))
    weights = []
    for p in players:
        row = []
        v = values.get(p.player_id, 0.0)
        can_play = startable.get(p.player_id, True)
        for s in slots:
            if not p.can_fill(s):
                row.append(_FORBIDDEN)
            elif not can_play:
                row.append(0.0)
            else:
                # Shift so a starter always beats an empty slot.
                row.append(v + 1000.0)
        row += [0.0] * (n - len(slots))  # bench columns
        weights.append(row)
    for _ in range(n - len(players)):
        weights.append([0.0] * n)

    assignment = hungarian_max(weights)
    starters: list[tuple[str, Player | None, float]] = [(s, None, 0.0) for s in slots]
    bench = []
    for i, p in enumerate(players):
        col = assignment[i]
        v = values.get(p.player_id, 0.0)
        if col < len(slots) and weights[i][col] > 0 and startable.get(p.player_id, True):
            starters[col] = (slots[col], p, v)
        else:
            bench.append((p, v))
    bench.sort(key=lambda t: -t[1])
    return Lineup(starters, bench)
