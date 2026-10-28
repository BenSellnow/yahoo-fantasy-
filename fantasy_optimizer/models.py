"""Plain data containers shared by every part of the optimizer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Yahoo statuses that mean the player will not play at all.
OUT_STATUSES = {
    "O", "OUT", "IR", "IR-R", "IR-LT", "IL", "IL7", "IL10", "IL15", "IL60",
    "PUP", "PUP-R", "PUP-P", "NFI", "NFI-R", "SUSP", "NA", "INJ", "COVID-19",
}
# Statuses that mean the player might miss time, with the share of games we
# expect them to play.
PARTIAL_STATUSES = {"Q": 0.8, "GTD": 0.75, "DTD": 0.8, "D": 0.3, "P": 0.95}

# Roster slots that never count toward the starting lineup.
INACTIVE_SLOTS = {"BN", "IR", "IR+", "IL", "IL+", "NA", "DL"}
INJURY_SLOTS = INACTIVE_SLOTS - {"BN"}

# Composite slots, used when a player's eligible_positions list does not
# already spell them out.
COMPOSITE_SLOTS = {
    "W/R/T": {"WR", "RB", "TE"},
    "W/R": {"WR", "RB"},
    "W/T": {"WR", "TE"},
    "R/T": {"RB", "TE"},
    "Q/W/R/T": {"QB", "WR", "RB", "TE"},
    "D": {"DE", "DT", "LB", "CB", "S", "DB", "DL"},
    "DB": {"CB", "S"},
    "DL": {"DE", "DT"},
    "G": {"PG", "SG"},
    "F": {"SF", "PF"},
    "IF": {"1B", "2B", "3B", "SS"},
    "CI": {"1B", "3B"},
    "MI": {"2B", "SS"},
    "OF": {"LF", "CF", "RF"},
    "P": {"SP", "RP"},
}


def availability(status: str) -> float:
    """Expected share of games played given a Yahoo injury status."""
    status = (status or "").upper()
    if status in OUT_STATUSES:
        return 0.0
    return PARTIAL_STATUSES.get(status, 1.0)


@dataclass
class Category:
    stat_id: int
    name: str
    position_type: str = ""
    higher_is_better: bool = True
    is_ratio: bool = False


@dataclass
class LeagueInfo:
    league_key: str
    name: str
    game_code: str
    season: int
    scoring_type: str
    num_teams: int
    current_week: int
    end_week: int
    playoff_start_week: int
    num_playoff_teams: int
    weeks_elapsed: float
    categories: list[Category]
    stat_modifiers: dict[int, float]
    roster_slots: dict[str, int]
    my_team_key: str

    @property
    def is_points(self) -> bool:
        # Only points leagues define stat modifiers (points per stat).
        return self.scoring_type in ("headpoint", "point") or (
            bool(self.stat_modifiers) and self.scoring_type != "roto")

    @property
    def is_head_to_head(self) -> bool:
        return self.scoring_type.startswith("head")

    def starting_slots(self) -> list[str]:
        slots = []
        for pos, count in self.roster_slots.items():
            if pos not in INACTIVE_SLOTS:
                slots += [pos] * count
        return slots

    def active_roster_size(self) -> int:
        return sum(c for p, c in self.roster_slots.items() if p not in INJURY_SLOTS)


@dataclass
class StatLine:
    """Totals over a span of time, plus how many weeks that span covers."""
    stats: dict[int, float]
    points: Optional[float]
    weeks: float


@dataclass
class Player:
    player_id: int
    name: str
    team_abbr: str = ""
    positions: list[str] = field(default_factory=list)
    position_type: str = ""
    status: str = ""
    selected_position: Optional[str] = None
    bye_week: Optional[int] = None
    owner_key: Optional[str] = None
    percent_owned: Optional[float] = None
    stat_lines: dict[str, StatLine] = field(default_factory=dict)

    def can_fill(self, slot: str) -> bool:
        if slot in self.positions:
            return True
        if slot == "Util":
            # Yahoo normally lists Util explicitly; otherwise it covers
            # everyone except pitchers and goalies.
            return not ({"SP", "RP", "P", "G"} & set(self.positions)) or \
                {"PG", "SG"} & set(self.positions) != set()
        return bool(COMPOSITE_SLOTS.get(slot, set()) & set(self.positions))

    @property
    def on_injury_slot(self) -> bool:
        return (self.selected_position or "") in INJURY_SLOTS


@dataclass
class TeamWeek:
    team_key: str
    week: int
    stats: dict[int, float]
    points: Optional[float] = None
    projected_points: Optional[float] = None
    win_probability: Optional[float] = None


@dataclass
class Matchup:
    week: int
    status: str  # preevent | midevent | postevent
    week_start: Optional[str]
    week_end: Optional[str]
    teams: tuple[TeamWeek, TeamWeek]

    def opponent_of(self, team_key: str) -> Optional[TeamWeek]:
        a, b = self.teams
        if a.team_key == team_key:
            return b
        if b.team_key == team_key:
            return a
        return None

    def side(self, team_key: str) -> Optional[TeamWeek]:
        for t in self.teams:
            if t.team_key == team_key:
                return t
        return None


@dataclass
class StandingsRow:
    team_key: str
    name: str
    wins: float
    losses: float
    ties: float
    points_for: float = 0.0
