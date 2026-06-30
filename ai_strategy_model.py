"""
AI Strategy Model
=================

Learns **how the player chooses betting combinations** from the current board
setup, and how well those choices actually do — then scores the combination the
player is about to place and recommends the combination that has historically
worked best in similar situations.

This is *imitation learning weighted by outcome*: the model only ever proposes
combinations the player themselves has used, ranked by how often they won in
comparable board states. It does not invent "hot numbers".

Pure Python, no external dependencies (keeps `flet build apk` working).

Storage (same SQLite db as the rest of the app):
    strategy_combo_stats   — outcomes per (board signature, combination)
    strategy_feature_stats — outcomes per (board feature, combination)
                             used to generalise to never-seen-exactly states
"""

import sqlite3
import math
from datetime import datetime
from typing import List, Dict, Optional, Iterable

from ai_game_state import MIN_OBSERVE

# Z value for the Wilson lower-bound. 1.0 ~= 68% one-sided; intentionally soft so
# the model is usable after only a handful of games.
_Z = 1.0
# Below this many total observations the model is still "warming up".
MIN_TRAINED_OBS = 15
# Minimum support before a combination is allowed to be recommended/judged.
MIN_SUPPORT = 3
# Minimum acted+skipped observations before judging whether a board is a
# "line-up" the player enters on.
MIN_SETUP_SUPPORT = 4


def wilson_lower_bound(wins: int, total: int, z: float = _Z) -> float:
    """Lower bound of a binomial proportion — rewards both rate AND sample size."""
    if total <= 0:
        return 0.0
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


class StrategyModel:
    """Player combination-choice model: record outcomes, score, recommend."""

    def __init__(self, db_path: str, extractor):
        self.db_path = db_path
        self.extractor = extractor
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS strategy_combo_stats ("
                " signature TEXT, combo TEXT,"
                " wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,"
                " profit REAL DEFAULT 0, last_seen TEXT,"
                " PRIMARY KEY (signature, combo))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS strategy_feature_stats ("
                " feature TEXT, combo TEXT,"
                " wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,"
                " PRIMARY KEY (feature, combo))"
            )
            # "Line-up" stats: per board signature, how often the player ENTERS
            # (places a combo bet) vs WAITS (spins past it). This is the core
            # Linup idea — waiting for the right entry / wave.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS strategy_setup_stats ("
                " signature TEXT PRIMARY KEY,"
                " acted INTEGER DEFAULT 0, skipped INTEGER DEFAULT 0,"
                " last_seen TEXT)"
            )
            # Adaptive wait: running total of how many spins the player lets pass
            # before entering, so we learn their typical line-up length.
            conn.execute(
                "CREATE TABLE IF NOT EXISTS strategy_wait ("
                " id INTEGER PRIMARY KEY CHECK (id = 1),"
                " entries INTEGER DEFAULT 0, total_wait INTEGER DEFAULT 0)"
            )
            conn.execute(
                "INSERT OR IGNORE INTO strategy_wait (id, entries, total_wait)"
                " VALUES (1, 0, 0)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"StrategyModel init warning: {e}")

    # ──────────────────────────────────────────────────────────────────
    # CAPTURE
    # ──────────────────────────────────────────────────────────────────
    def capture_choice(self, recent_numbers: List[int],
                       combo_groups: Iterable[str]) -> Dict:
        """Snapshot the board + the chosen combination at bet time.

        Returns an opaque dict to be passed back to ``record_outcome`` once the
        spin result is known.
        """
        feats = self.extractor.extract(recent_numbers)
        return {
            'signature': self.extractor.signature(feats),
            'combo': self.extractor.normalize_combo(combo_groups),
            'features': feats,
            'feature_items': self.extractor.feature_items(feats),
        }

    def record_outcome(self, choice: Dict, won: bool,
                       profit: float = 0.0) -> bool:
        """Persist the result of a previously captured choice (incremental train)."""
        if not choice:
            return False
        try:
            w = 1 if won else 0
            l = 0 if won else 1
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            # Exact (signature, combo) bucket.
            cur.execute(
                "INSERT INTO strategy_combo_stats"
                " (signature, combo, wins, losses, profit, last_seen)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(signature, combo) DO UPDATE SET"
                "   wins = wins + ?, losses = losses + ?,"
                "   profit = profit + ?, last_seen = ?",
                (choice['signature'], choice['combo'], w, l, profit,
                 datetime.now().isoformat(), w, l, profit,
                 datetime.now().isoformat()),
            )
            # Per-feature buckets (generalisation layer).
            for feat in choice.get('feature_items', []):
                cur.execute(
                    "INSERT INTO strategy_feature_stats"
                    " (feature, combo, wins, losses) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(feature, combo) DO UPDATE SET"
                    "   wins = wins + ?, losses = losses + ?",
                    (feat, choice['combo'], w, l, w, l),
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            try:
                with open("/tmp/linup_strategy_error.log", "a") as f:
                    f.write(f"[record_outcome] {type(e).__name__}: {e}\n")
            except Exception:
                pass
            return False

    # ──────────────────────────────────────────────────────────────────
    # LINE-UP / WAIT MODEL  (when does the player enter vs keep waiting?)
    # ──────────────────────────────────────────────────────────────────
    def record_observation(self, recent_numbers: List[int], acted: bool) -> bool:
        """Record that the player ENTERED (acted) or WAITED (skipped) on a board.

        Called on every spin: ``acted=True`` when a combination bet was placed,
        ``acted=False`` when the player spun past the board waiting for a better
        line-up. Teaches the model which setups are real entries for this player.
        """
        if len(list(recent_numbers)) < MIN_OBSERVE:
            return False
        try:
            feats = self.extractor.extract(recent_numbers)
            sig = self.extractor.setup_signature(feats)
            a = 1 if acted else 0
            s = 0 if acted else 1
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO strategy_setup_stats"
                " (signature, acted, skipped, last_seen) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(signature) DO UPDATE SET"
                "   acted = acted + ?, skipped = skipped + ?, last_seen = ?",
                (sig, a, s, datetime.now().isoformat(), a, s,
                 datetime.now().isoformat()),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def setup_readiness(self, recent_numbers: List[int]) -> Dict:
        """Is the current board a line-up the player usually enters on?

        Returns act_rate (how often you bet here vs wait), a support count and a
        short human label.
        """
        if len(list(recent_numbers)) < MIN_OBSERVE:
            return {'status': 'observing', 'support': 0}
        try:
            feats = self.extractor.extract(recent_numbers)
            sig = self.extractor.setup_signature(feats)
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT acted, skipped FROM strategy_setup_stats"
                " WHERE signature = ?", (sig,)).fetchone()
            conn.close()
        except Exception:
            return {'status': 'error', 'support': 0}

        acted, skipped = (row[0], row[1]) if row else (0, 0)
        total = acted + skipped
        if total < MIN_SETUP_SUPPORT:
            return {'status': 'learning', 'support': total,
                    'acted': acted, 'skipped': skipped}
        act_rate = acted / total
        if act_rate >= 0.6:
            label = 'ENTER — your kind of line-up'
        elif act_rate <= 0.3:
            label = 'WAIT — you usually pass this'
        else:
            label = 'MIXED — you go both ways here'
        return {'status': 'ok', 'support': total, 'acted': acted,
                'skipped': skipped, 'act_rate': act_rate, 'label': label}

    def record_entry_wait(self, spins_waited: int) -> bool:
        """Record how many spins the player let pass before this entry."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE strategy_wait SET entries = entries + 1,"
                " total_wait = total_wait + ? WHERE id = 1",
                (max(0, int(spins_waited)),))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def typical_wait(self) -> Optional[float]:
        """Average spins the player waits before entering (None until learned)."""
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT entries, total_wait FROM strategy_wait WHERE id = 1"
            ).fetchone()
            conn.close()
            if row and row[0] >= 3:
                return row[1] / row[0]
            return None
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────────
    # SCORING
    # ──────────────────────────────────────────────────────────────────
    def score(self, recent_numbers: List[int],
              combo_groups: Iterable[str]) -> Dict:
        """Estimate the win probability of a combination in the current state.

        Blends three signals:
          1. exact (signature, combo) outcomes  — most specific
          2. combo outcomes across all states   — the combo's baseline for you
          3. per-feature outcomes for the combo — generalises to new states
        """
        feats = self.extractor.extract(recent_numbers)
        signature = self.extractor.signature(feats)
        combo = self.extractor.normalize_combo(combo_groups)
        feature_items = self.extractor.feature_items(feats)

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            # 1) exact match
            cur.execute(
                "SELECT wins, losses FROM strategy_combo_stats"
                " WHERE signature = ? AND combo = ?", (signature, combo))
            row = cur.fetchone()
            e_w, e_l = (row[0], row[1]) if row else (0, 0)

            # 2) combo baseline (this combo anywhere)
            cur.execute(
                "SELECT SUM(wins), SUM(losses) FROM strategy_combo_stats"
                " WHERE combo = ?", (combo,))
            row = cur.fetchone()
            c_w, c_l = (row[0] or 0, row[1] or 0) if row else (0, 0)

            # 3) feature layer for this combo
            f_num = 0.0   # support-weighted sum of win rates
            f_den = 0.0   # total support
            if feature_items:
                placeholders = ",".join("?" * len(feature_items))
                cur.execute(
                    f"SELECT wins, losses FROM strategy_feature_stats"
                    f" WHERE combo = ? AND feature IN ({placeholders})",
                    (combo, *feature_items))
                for fw, fl in cur.fetchall():
                    tot = fw + fl
                    if tot > 0:
                        f_num += (fw / tot) * tot
                        f_den += tot
            conn.close()
        except Exception:
            return {'win_prob': None, 'confidence': 0.0, 'support': 0,
                    'verdict': 'UNKNOWN', 'combo': combo}

        # Weighted blend of whatever signals we have.
        signals = []  # (probability, weight)
        e_n = e_w + e_l
        if e_n > 0:
            signals.append((wilson_lower_bound(e_w, e_n), min(e_n, 20) * 1.0))
        c_n = c_w + c_l
        if c_n > 0:
            signals.append((wilson_lower_bound(c_w, c_n), min(c_n, 20) * 0.4))
        if f_den > 0:
            signals.append((f_num / f_den, min(f_den, 40) * 0.2))

        if not signals:
            return {'win_prob': None, 'confidence': 0.0, 'support': 0,
                    'verdict': 'UNKNOWN', 'combo': combo,
                    'reason': 'No history for this combination yet'}

        wsum = sum(w for _, w in signals)
        win_prob = sum(p * w for p, w in signals) / wsum
        support = e_n  # exact-state support drives our confidence wording
        confidence = min(1.0, (e_n * 1.5 + c_n * 0.5) / 12.0)

        return {
            'win_prob': win_prob,
            'confidence': confidence,
            'support': support,
            'combo_support': c_n,
            'verdict': self._verdict(win_prob),
            'combo': combo,
            'reason': (f"{e_w}W/{e_l}L here, "
                       f"{c_w}W/{c_l}L overall for {combo}"),
        }

    @staticmethod
    def _verdict(p: Optional[float]) -> str:
        if p is None:
            return 'UNKNOWN'
        if p >= 0.60:
            return 'LIKELY WIN'
        if p >= 0.53:
            return 'EDGE'
        if p >= 0.47:
            return 'COIN FLIP'
        if p >= 0.40:
            return 'RISKY'
        return 'AVOID'

    # ──────────────────────────────────────────────────────────────────
    # RECOMMENDATION
    # ──────────────────────────────────────────────────────────────────
    def recommend(self, recent_numbers: List[int],
                  candidate_combos: Optional[List[Iterable[str]]] = None) -> Optional[Dict]:
        """Recommend the best-performing combination for the current board.

        Considers the supplied candidate combinations (e.g. the live suggestion
        pairs) *plus* every combination the player has actually used in this
        exact board signature. Returns the highest-scoring option with enough
        support, or ``None`` while still learning.
        """
        feats = self.extractor.extract(recent_numbers)
        signature = self.extractor.signature(feats)

        combos = set()
        for c in (candidate_combos or []):
            key = self.extractor.normalize_combo(c)
            if key:
                combos.add(key)

        # Add the player's own historical choices for this exact state.
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT combo FROM strategy_combo_stats"
                " WHERE signature = ? AND (wins + losses) > 0", (signature,))
            for (combo,) in cur.fetchall():
                combos.add(combo)
            conn.close()
        except Exception:
            pass

        best = None
        for combo in combos:
            res = self.score(recent_numbers, combo.split('+'))
            if res.get('win_prob') is None:
                continue
            # Need at least some real support to recommend.
            if res.get('support', 0) + res.get('combo_support', 0) < MIN_SUPPORT:
                continue
            if best is None or res['win_prob'] > best['win_prob']:
                best = res
        return best

    # ──────────────────────────────────────────────────────────────────
    # ANALYSIS  (successes & errors)
    # ──────────────────────────────────────────────────────────────────
    def total_observations(self) -> int:
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT SUM(wins + losses) FROM strategy_combo_stats").fetchone()
            conn.close()
            return int(row[0]) if row and row[0] else 0
        except Exception:
            return 0

    def is_trained(self) -> bool:
        return self.total_observations() >= MIN_TRAINED_OBS

    def analyze(self) -> Dict:
        """Summarise the player's winning patterns (successes) and leaks (errors)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            # Aggregate by combination across all states.
            cur.execute(
                "SELECT combo, SUM(wins), SUM(losses), SUM(profit)"
                " FROM strategy_combo_stats GROUP BY combo")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

        combos = []
        total_w = total_l = 0
        for combo, w, l, profit in rows:
            w, l = w or 0, l or 0
            total_w += w
            total_l += l
            n = w + l
            if n == 0:
                continue
            combos.append({
                'combo': combo,
                'wins': w,
                'losses': l,
                'total': n,
                'win_rate': w / n,
                'wilson': wilson_lower_bound(w, n),
                'profit': profit or 0.0,
            })

        total_n = total_w + total_l
        if total_n == 0:
            return {'status': 'insufficient_data', 'total': 0}

        rated = [c for c in combos if c['total'] >= MIN_SUPPORT]
        successes = sorted(rated, key=lambda c: c['wilson'], reverse=True)[:5]
        errors = sorted(rated, key=lambda c: c['wilson'])[:5]

        return {
            'status': 'ok',
            'total': total_n,
            'overall_win_rate': total_w / total_n,
            'distinct_combos': len(combos),
            'successes': successes,           # combinations that work for you
            'errors': [c for c in errors if c['win_rate'] < 0.5],  # leaks
            'most_used': sorted(combos, key=lambda c: c['total'],
                                reverse=True)[:5],
        }

    def improvement_tips(self) -> List[str]:
        """Plain-language coaching derived from analyze()."""
        a = self.analyze()
        if a.get('status') != 'ok':
            return [f"Keep playing — need {MIN_TRAINED_OBS} graded bets to learn "
                    f"your style ({a.get('total', 0)} so far)."]
        tips = []
        if a['successes']:
            s = a['successes'][0]
            tips.append(f"Your strongest play: {s['combo']} "
                        f"({s['win_rate']:.0%} over {s['total']} bets).")
        for e in a['errors'][:2]:
            tips.append(f"Leak: {e['combo']} only wins {e['win_rate']:.0%} "
                        f"({e['losses']}L/{e['total']}) — rethink it.")
        tips.append(f"Overall combination win rate: {a['overall_win_rate']:.0%} "
                    f"across {a['total']} graded bets.")
        return tips
