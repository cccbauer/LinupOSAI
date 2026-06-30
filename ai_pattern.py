"""
AI Pattern Detector
===================

Watches the first ~20 colours of a croupier's Black/Red sequence, classifies the
opening into ONE committed pattern, then bets that pattern for the rest of the
session:

    BIAS-R / BIAS-B  — one colour clearly dominates  -> always bet that colour
    STREAK           — colours tend to repeat         -> bet the last colour
    ALTERNATE        — colours tend to flip           -> bet the opposite colour
    none             — no clear opening pattern        -> sit the session out

This is the "observe then commit" idea: the decision is locked on the opening
window and held. The player has ~4 chances to hit per entry, so the pattern only
has to *hold* through the session, not predict every single spin.

Pure Python, in-memory, per session. bit convention: 1 = Red, 0 = Black; green
(wheel 0) is skipped — it is not a Red/Black event.
"""

PATTERN_WARMUP = 20          # colours observed before the pattern is locked
PATTERN_BIAS_MARGIN = 0.20   # |frac_red - 0.5| >= this -> colour bias (>=70% one colour)
PATTERN_REP_LO = 0.35        # P(repeat) <= this -> alternating
PATTERN_REP_HI = 0.65        # P(repeat) >= this -> streaky


class PatternDetector:
    def __init__(self, rojos, warmup=PATTERN_WARMUP, bias_margin=PATTERN_BIAS_MARGIN,
                 rep_lo=PATTERN_REP_LO, rep_hi=PATTERN_REP_HI):
        self.rojos = set(int(x) for x in rojos)
        self.warmup = int(warmup)
        self.bias_margin = bias_margin
        self.rep_lo = rep_lo
        self.rep_hi = rep_hi
        self.reset()

    # ---- lifecycle ---------------------------------------------------------
    def reset(self):
        self.colors = []      # observed 1/0 colours (greens skipped)
        self.kind = None      # 'BIAS-R'/'BIAS-B'/'STREAK'/'ALTERNATE'/'none'
        self.rule = None      # ('const',1/0) / ('streak',None) / ('alt',None) / None
        self.locked = False

    # ---- colour mapping ----------------------------------------------------
    def num_to_bit(self, num):
        if num == 0:
            return None
        return 1 if num in self.rojos else 0

    # ---- classification ----------------------------------------------------
    @staticmethod
    def _prep(seq):
        if len(seq) < 2:
            return 0.5
        return sum(seq[i + 1] == seq[i] for i in range(len(seq) - 1)) / (len(seq) - 1)

    def _classify(self, seq):
        bias_r = sum(seq) / len(seq)
        pr = self._prep(seq)
        if abs(bias_r - 0.5) >= self.bias_margin:
            dom = 1 if bias_r > 0.5 else 0
            return ("BIAS-%s" % ("R" if dom else "B"), ("const", dom))
        if pr <= self.rep_lo:
            return ("ALTERNATE", ("alt", None))
        if pr >= self.rep_hi:
            return ("STREAK", ("streak", None))
        return ("none", None)

    # ---- ingestion ---------------------------------------------------------
    def observe_num(self, num):
        b = self.num_to_bit(num)
        if b is None:
            return
        self.colors.append(b)
        if not self.locked and len(self.colors) >= self.warmup:
            self.kind, self.rule = self._classify(self.colors[:self.warmup])
            self.locked = True

    def observe_sequence(self, nums):
        self.reset()
        for n in nums:
            self.observe_num(n)

    # ---- prediction --------------------------------------------------------
    def predict_color(self):
        """'R' / 'B' / None — the committed bet for the next spin."""
        if not self.locked or self.rule is None:
            return None
        kind = self.rule[0]
        if kind == "const":
            return "R" if self.rule[1] == 1 else "B"
        if not self.colors:
            return None
        last = self.colors[-1]
        if kind == "streak":
            return "R" if last == 1 else "B"
        if kind == "alt":
            return "R" if last == 0 else "B"
        return None

    # ---- status (for the AI info bar) --------------------------------------
    def status(self):
        return {"phase": "locked" if self.locked else "observing",
                "n": len(self.colors), "warmup": self.warmup,
                "kind": self.kind, "predict": self.predict_color()}

    def status_text(self):
        if not self.locked:
            return f"PATTERN: observing {len(self.colors)}/{self.warmup}"
        if self.kind == "none":
            return "PATTERN: none — sit out"
        return f"PATTERN: {self.kind} → bet {self.predict_color()}"
