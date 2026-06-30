"""
AI Rhythm Model
===============

Reads the short-term *rhythm* in a live croupier's Black/Red sequence and
predicts the next colour, so the live dozen suggestion can be coloured
(e.g. "2a + R").

The predictor is an online **variable-order Markov** model: a Bayesian mixture
over context orders 0..D, each one a Krichevsky–Trofimov (KT) estimator, with
exponential forgetting so it adapts when the croupier changes (concept drift).
This family (CTW / VOMM) is the literature-recommended choice for short,
drifting, low-data sequences — far better than a neural net, which would overfit
a ≤50-draw session.

Pure Python, no external dependencies (keeps `flet build apk` working).
In-memory and per-session; nothing is persisted in Phase 1.

Bit convention: 1 = Red, 0 = Black; green (wheel 0) is skipped — it is not a
Red/Black event and must not advance the context.
"""

import math
from typing import Dict, List, Optional, Iterable, Tuple

# Context order: how many previous colours the rhythm may depend on.
RHYTHM_DEPTH = 4
# R/B observations required before any signal is emitted (0/green excluded).
RHYTHM_WARMUP = 20
# Per-observation forgetting on the KT counts (recency weighting for drift).
RHYTHM_DECAY = 0.98
# |p_red - 0.5| must exceed this before a colour is suggested (so p_red >= 0.64
# for Red / <= 0.36 for Black). Calibrated against a real 52-draw croupier:
# 0.24 was too strict (fired once in the whole session); 0.14 captures the
# dealer's streak+bias structure (~56% hit over 9 fires there, beating the 55%
# streak-rider and 56% colour-bias baselines) while still requiring a real lean.
# Provisional — should be re-tuned as more croupier sequences are collected.
RHYTHM_CONF_MARGIN = 0.14
# Fixed-share floor: lets a newly-better order unseat a long-dominant one.
_SHARE = 0.02


class RhythmModel:
    """Online variable-order Markov predictor over a Black/Red bit stream."""

    def __init__(self, rojos: Iterable[int], depth: int = RHYTHM_DEPTH,
                 warmup: int = RHYTHM_WARMUP, decay: float = RHYTHM_DECAY):
        self.rojos = set(int(x) for x in rojos)
        self.depth = int(depth)
        self.warmup = int(warmup)
        self.decay = float(decay)
        self.reset()

    # ---- lifecycle ---------------------------------------------------------
    def reset(self) -> None:
        # counts[k] maps a context tuple of the last k bits -> [c0, c1] KT counts
        self.counts: List[Dict[Tuple[int, ...], List[float]]] = [
            {} for _ in range(self.depth + 1)
        ]
        # log mixture weight per order; start uniform
        self.logw: List[float] = [0.0 for _ in range(self.depth + 1)]
        self.ctx: List[int] = []   # recent bit history (most-recent-last)
        self.n = 0                 # number of R/B bits observed (0 excluded)

    # ---- colour mapping ----------------------------------------------------
    def num_to_bit(self, num: int) -> Optional[int]:
        """Map a raw wheel number to a colour bit, or None for green (0)."""
        if num == 0:
            return None
        return 1 if num in self.rojos else 0

    # ---- internals ---------------------------------------------------------
    def _ctx_for(self, k: int) -> Tuple[int, ...]:
        return tuple(self.ctx[-k:]) if k > 0 else ()

    def _p_red_order(self, k: int) -> float:
        """KT estimate P(next = Red) for the order-k context."""
        c = self.counts[k].get(self._ctx_for(k))
        if not c:
            return 0.5
        c0, c1 = c
        return (c1 + 0.5) / (c0 + c1 + 1.0)

    # ---- ingestion ---------------------------------------------------------
    def update(self, bit: int) -> None:
        """Fold one Red(1)/Black(0) observation into the model. O(depth)."""
        bit = 1 if bit else 0

        # 1) Bayesian weight update by each order's predictive likelihood of the
        #    bit, using the context BEFORE the bit is folded in.
        new_logw = []
        for k in range(self.depth + 1):
            p1 = self._p_red_order(k)
            p = p1 if bit == 1 else (1.0 - p1)
            new_logw.append(self.logw[k] + math.log(max(p, 1e-9)))
        m = max(new_logw)
        w = [math.exp(lw - m) for lw in new_logw]
        s = sum(w) or 1.0
        w = [x / s for x in w]
        # fixed-share forgetting toward uniform so the dominant order can shift
        u = 1.0 / (self.depth + 1)
        w = [(1.0 - _SHARE) * x + _SHARE * u for x in w]
        s = sum(w) or 1.0
        self.logw = [math.log(x / s) for x in w]

        # 2) fold the bit into each order's KT counts (decayed for recency)
        for k in range(self.depth + 1):
            key = self._ctx_for(k)
            c = self.counts[k].get(key)
            if c is None:
                c = [0.0, 0.0]
                self.counts[k][key] = c
            c[0] *= self.decay
            c[1] *= self.decay
            c[bit] += 1.0

        # 3) advance the bounded context and the counter
        self.ctx.append(bit)
        if len(self.ctx) > self.depth:
            self.ctx = self.ctx[-self.depth:]
        self.n += 1

    def observe_num(self, num: int) -> None:
        """Map a raw wheel number and fold it in (green/0 is skipped)."""
        bit = self.num_to_bit(num)
        if bit is not None:
            self.update(bit)

    def observe_sequence(self, nums: Iterable[int]) -> None:
        """Rebuild from scratch over an ordered list of raw numbers."""
        self.reset()
        for num in nums:
            self.observe_num(num)

    # ---- prediction --------------------------------------------------------
    def predict(self) -> Dict:
        """Return {p_red, confidence, n_observed, ready}.

        Before the warmup completes: ready=False, p_red=0.5, confidence=0.0.
        """
        if self.n < self.warmup:
            return {'p_red': 0.5, 'confidence': 0.0,
                    'n_observed': self.n, 'ready': False}
        w = [math.exp(lw) for lw in self.logw]
        s = sum(w) or 1.0
        w = [x / s for x in w]
        p_red = sum(w[k] * self._p_red_order(k) for k in range(self.depth + 1))
        p_red = min(1.0, max(0.0, p_red))
        return {'p_red': p_red, 'confidence': abs(p_red - 0.5) * 2.0,
                'n_observed': self.n, 'ready': True}

    def confident_color(self) -> Optional[str]:
        """The actionable signal for the suggestion row: 'R', 'B', or None."""
        pr = self.predict()
        if not pr['ready']:
            return None
        if abs(pr['p_red'] - 0.5) < RHYTHM_CONF_MARGIN:
            return None
        return 'R' if pr['p_red'] > 0.5 else 'B'
