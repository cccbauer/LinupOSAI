"""
AI Game-State Extractor
=======================

Turns the *current game setup* (the recent spin history the player is reading)
into a compact, discretized "state signature" plus a feature dictionary.

The whole point of the revamped AI is to learn **the way the player chooses
combinations from the board** — not to predict the next number. So the features
here describe exactly what the player looks at before deciding:

    * The leading group of every suggestion category (cols / docs / secs /
      thirds / wave) over the observation window — i.e. the buttons the app is
      offering.
    * The dominant pair in each category (what the suggestion row shows).
    * Coarse colour / parity / range balance of the recent spins.
    * The current colour streak.

Everything is pure-Python (no numpy / sklearn) so `flet build apk` keeps working.
"""

from typing import List, Dict, Optional, Iterable

# Standard European-wheel reds (kept local so this module has no dependency on
# main.py). Matches ROJOS in main.py.
ROJOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

# Suggestion categories — these mirror the buttons in actualizar_sugerencias().
CATEGORIES: Dict[str, List[str]] = {
    'cols':   ['34', '35', '36'],
    'docs':   ['1a', '2a', '3a'],
    'secs':   ['Z0', 'ZG', 'ZP', 'H'],
    'thirds': ['T1', 'T2', 'T3'],
    'wave':   ['W1', 'W2', 'W3'],
}

# Suffixes used by live / filter modes; stripped to get the base mixer key.
_SUFFIXES = ('_LR', '_LB', '_L', '_R', '_B')

# How many recent spins define the "board the player is reading".
WINDOW = 9
# Minimum spins before any state is meaningful (player watches 6-10 first).
MIN_OBSERVE = 6


def to_display_name(group: str) -> str:
    """Strip live/filter suffixes to get the base group key (mirror main.py)."""
    for sfx in _SUFFIXES:
        if group.endswith(sfx):
            return group[: -len(sfx)]
    return group


class GameStateExtractor:
    """Builds feature dicts + signatures from the recent spin history."""

    def __init__(self, grupos_maestros: Dict[str, Iterable[int]],
                 wheel_neighbors: Optional[Dict] = None,
                 window: int = WINDOW):
        # Store group members as sets for fast lookups.
        self.gm = {k: set(v) for k, v in grupos_maestros.items()}
        self.wn = wheel_neighbors or {}
        self.window = window

    # ──────────────────────────────────────────────────────────────────
    # FEATURE EXTRACTION
    # ──────────────────────────────────────────────────────────────────
    def extract(self, recent_numbers: List[int]) -> Dict:
        """Return a feature dict describing the current board setup.

        Args:
            recent_numbers: spin history, most-recent value LAST.
        """
        window = [int(n) for n in list(recent_numbers)[-self.window:]]
        n = len(window)
        feats: Dict = {'window_size': n}

        if n == 0:
            return feats

        # Leading group + dominant pair for each suggestion category.
        for cat, groups in CATEGORIES.items():
            freq = {g: sum(1 for x in window if x in self.gm.get(g, set()))
                    for g in groups}
            ranked = sorted(groups, key=lambda g: (freq[g], g), reverse=True)
            top = ranked[0]
            second = ranked[1] if len(ranked) > 1 else None
            feats[f'{cat}_top'] = top
            # The app only surfaces a pair when there is a clear #1/#2 over #3.
            has_pair = (second is not None and
                        (len(ranked) < 3 or freq[second] > freq[ranked[2]]))
            feats[f'{cat}_pair'] = self.normalize_combo([top, second]) \
                if (has_pair and second) else None

        # Colour / parity / range balance over the window.
        reds = sum(1 for x in window if x in ROJOS)
        zeros = sum(1 for x in window if x == 0)
        non_zero = n - zeros
        feats['color'] = self._balance_bucket(reds, non_zero)
        evens = sum(1 for x in window if x != 0 and x % 2 == 0)
        feats['parity'] = self._balance_bucket(evens, non_zero, 'EVEN', 'ODD')
        lows = sum(1 for x in window if 1 <= x <= 18)
        feats['range'] = self._balance_bucket(lows, non_zero, 'LOW', 'HIGH')

        # Current colour streak length (how many same-colour in a row at the end).
        feats['streak'] = self._streak_bucket(window)

        # Most-recent number's coarse zone (helps separate similar windows).
        feats['last_zone'] = self._zone(window[-1])
        return feats

    @staticmethod
    def _balance_bucket(count: int, total: int,
                        hi: str = 'R', lo: str = 'B') -> str:
        """Bucket a count/total split into hi-heavy / lo-heavy / balanced."""
        if total <= 0:
            return 'NA'
        frac = count / total
        if frac >= 0.62:
            return hi
        if frac <= 0.38:
            return lo
        return 'BAL'

    def _streak_bucket(self, window: List[int]) -> str:
        """Length bucket of the trailing same-colour run."""
        streak = 0
        last_color = None
        for x in reversed(window):
            if x == 0:
                break
            color = 'R' if x in ROJOS else 'B'
            if last_color is None:
                last_color = color
                streak = 1
            elif color == last_color:
                streak += 1
            else:
                break
        if streak >= 4:
            return 'STREAK4+'
        if streak == 3:
            return 'STREAK3'
        return 'NONE'

    @staticmethod
    def _zone(num: int) -> str:
        if num == 0:
            return 'Z'
        if num <= 12:
            return 'D1'
        if num <= 24:
            return 'D2'
        return 'D3'

    # ──────────────────────────────────────────────────────────────────
    # SIGNATURE  (exact-match key for the state)
    # ──────────────────────────────────────────────────────────────────
    def signature(self, feats: Dict) -> str:
        """Compact string identifying the board setup for exact matching.

        Uses the category leaders + colour balance — the things that actually
        drive which suggestion the player picks.
        """
        parts = [feats.get(f'{cat}_top', '?') for cat in CATEGORIES]
        parts.append('c' + str(feats.get('color', 'NA')))
        return '|'.join(parts)

    # Sector categories the player treats as the "anchor" of a combination
    # (W / T / Z) and the line/dozen categories they pair it with.
    SECTOR_CATS = ('wave', 'thirds', 'secs')   # W / T / Z
    LINE_CATS = ('cols', 'docs')               # lines / dozens

    def setup_signature(self, feats: Dict) -> str:
        """Key for the *line-up / wait* model.

        "Linup" is about waiting until a combination sets up. The player waits
        until *any* combination lines up — usually one sector (W/T/Z) paired with
        a line or dozen. So the entry condition is keyed on **which categories
        currently show a clear pair** (i.e. which combinations have set up), not
        on one fixed group. This recurs often enough to learn from quickly and
        captures the player's real "is something set up yet?" judgement.
        """
        sectors = [c for c in self.SECTOR_CATS if feats.get(f'{c}_pair')]
        lines = [c for c in self.LINE_CATS if feats.get(f'{c}_pair')]
        return 'S:' + ('+'.join(sectors) or '-') + '|L:' + ('+'.join(lines) or '-')

    def setups_ready(self, feats: Dict) -> int:
        """How many categories currently have a clear pair (combinations set up)."""
        return sum(1 for c in CATEGORIES if feats.get(f'{c}_pair'))

    def feature_items(self, feats: Dict) -> List[str]:
        """Flat list of feature=value tokens used by the Naive-Bayes layer."""
        items = []
        for k, v in feats.items():
            if k == 'window_size' or v is None:
                continue
            items.append(f'{k}={v}')
        return items

    # ──────────────────────────────────────────────────────────────────
    # COMBO NORMALIZATION
    # ──────────────────────────────────────────────────────────────────
    def normalize_combo(self, groups: Iterable[str]) -> str:
        """Canonical key for a chosen combination (order-independent).

        e.g. ['35_L', '34'] -> '34+35'
        """
        names = sorted({to_display_name(g) for g in groups if g})
        return '+'.join(names)

    def is_ready(self, recent_numbers) -> bool:
        """True once enough spins are on the board to read a pattern."""
        return len(list(recent_numbers)) >= MIN_OBSERVE
