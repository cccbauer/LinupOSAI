#!/usr/bin/env python3
"""
Rhythm-model evaluation harness
===============================

Scores the B/R rhythm predictor (`ai_rhythm.RhythmModel`) against real croupier
draw sequences so we can tell whether dealers genuinely leak exploitable colour
structure — and tune the confidence margin on real data instead of one sample.

Two metrics are reported:

  1. ACTIONABLE (confident fires): exactly what the live app would bet — only the
     predictions where the model is confident enough to colour the dozen
     (warmup=RHYTHM_WARMUP, margin=RHYTHM_CONF_MARGIN, the deployed gates).
     Pooled across dealers with a binomial significance test, and against the
     51.4% even-money break-even (the green 0 tax).

  2. SKILL (all transitions): the model's raw probability at EVERY draw, scored
     by Brier skill + directional hit-rate. Uses ~25 predictions per 30-draw
     dealer (vs ~4 confident fires), so it gives a statistical read with far
     fewer dealers. Warmup is bypassed here on purpose.

Two simple baselines are shown for context: streak-rider P(repeat) and the
always-majority-colour bias.

Usage:  python3 ai_rhythm_eval.py [datafile]   (default: croupier_data.txt)
Pure stdlib; imports only ai_rhythm.
"""

import sys
import os
import re
import math

from ai_rhythm import RhythmModel, RHYTHM_WARMUP, RHYTHM_CONF_MARGIN

# Standard European red numbers — matches ROJOS in main.py.
ROJOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BREAK_EVEN = 18.0 / 37.0   # even-money win prob with a single zero ≈ 0.486 loss → 0.514 needed


def color(n):
    """1 = Red, 0 = Black, None = green (0)."""
    if n == 0:
        return None
    return 1 if n in ROJOS else 0


# ── data file parsing ────────────────────────────────────────────────────────
def parse_file(path):
    """Return list of (label, [numbers]) blocks. Forgiving of separators."""
    dealers = []
    label, nums = None, []
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@") or (line.startswith("[") and line.endswith("]")):
            if nums:
                dealers.append((label or f"dealer-{len(dealers)+1}", nums))
            label = line.lstrip("@[").rstrip("]").strip() or None
            nums = []
        else:
            nums.extend(int(x) for x in re.findall(r"\d+", line) if 0 <= int(x) <= 36)
    if nums:
        dealers.append((label or f"dealer-{len(dealers)+1}", nums))
    return dealers


# ── statistics helpers ───────────────────────────────────────────────────────
def _log_pmf(k, n, p):
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log(1 - p))


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value (normal approx for very large n)."""
    if n == 0:
        return 1.0
    if n > 4000:
        mu, sd = n * p, math.sqrt(n * p * (1 - p))
        z = (abs(k - mu) - 0.5) / sd
        return min(1.0, math.erfc(z / math.sqrt(2)))
    lpk = _log_pmf(k, n, p)
    return min(1.0, sum(math.exp(_log_pmf(i, n, p))
                        for i in range(n + 1) if _log_pmf(i, n, p) <= lpk + 1e-9))


def binom_ge(k, n, p):
    """One-sided P(X >= k) under Binomial(n, p)."""
    if n == 0:
        return 1.0
    if n > 4000:
        mu, sd = n * p, math.sqrt(n * p * (1 - p))
        z = (k - 0.5 - mu) / sd
        return min(1.0, 0.5 * math.erfc(z / math.sqrt(2)))
    return min(1.0, sum(math.exp(_log_pmf(i, n, p)) for i in range(k, n + 1)))


# ── per-dealer evaluation (predict-before-observe, no leakage) ────────────────
def eval_dealer(nums):
    cseq = [c for c in (color(n) for n in nums) if c is not None]
    out = {"n_total": len(nums), "n_color": len(cseq),
           "R": cseq.count(1), "B": cseq.count(0)}

    # baselines
    rep = sum(1 for i in range(len(cseq) - 1) if cseq[i + 1] == cseq[i])
    out["p_repeat"] = rep / (len(cseq) - 1) if len(cseq) > 1 else None
    maj = 1 if out["R"] >= out["B"] else 0
    out["bias"] = max(out["R"], out["B"]) / len(cseq) if cseq else None

    # ACTIONABLE — live gates (warmup + margin)
    live = RhythmModel(ROJOS)
    fires = 0
    fire_hits = 0
    for n in nums:
        a = color(n)
        if a is not None:
            pc = live.confident_color()        # prediction for THIS draw
            if pc is not None:
                fires += 1
                fire_hits += int((1 if pc == "R" else 0) == a)
        live.observe_num(n)
    out["fires"], out["fire_hits"] = fires, fire_hits

    # SKILL — every transition, warmup bypassed
    skill = RhythmModel(ROJOS, warmup=0)
    brier_sum = 0.0
    dir_hits = dir_tot = 0
    for n in nums:
        a = color(n)
        if a is not None:
            p = skill.predict()["p_red"]       # P(Red) for THIS draw
            brier_sum += (p - a) ** 2
            if p != 0.5:
                dir_tot += 1
                dir_hits += int((1 if p > 0.5 else 0) == a)
        skill.observe_num(n)
    out["brier_n"] = len(cseq)
    out["brier"] = brier_sum / len(cseq) if cseq else None
    out["dir_hits"], out["dir_tot"] = dir_hits, dir_tot
    return out


# ── report ───────────────────────────────────────────────────────────────────
def pct(x):
    return "  --" if x is None else f"{100*x:4.0f}%"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "croupier_data.txt")
    if not os.path.exists(path):
        print(f"data file not found: {path}")
        return
    dealers = parse_file(path)
    if not dealers:
        print("no croupier data found — add some under an '@ label' header.")
        return

    print(f"\nRhythm eval — {len(dealers)} croupier(s) from {os.path.basename(path)}")
    print(f"live gates: warmup={RHYTHM_WARMUP}  margin={RHYTHM_CONF_MARGIN} "
          f"(fire when p_red>={0.5+RHYTHM_CONF_MARGIN:.2f} or <={0.5-RHYTHM_CONF_MARGIN:.2f})")
    print("=" * 78)
    print(f"{'dealer':<16} {'draws':>5} {'R/B':>7} | {'P(rep)':>6} {'bias':>5} | "
          f"{'fires':>5} {'fireHit':>7} | {'allHit':>6} {'brierSk':>7}")
    print("-" * 78)

    tot_fires = tot_fire_hits = 0
    tot_dir_hits = tot_dir_tot = 0
    tot_brier_sum = tot_brier_n = 0.0
    rep_hits = rep_tot = bias_hits = bias_tot = 0

    for label, nums in dealers:
        r = eval_dealer(nums)
        tot_fires += r["fires"]; tot_fire_hits += r["fire_hits"]
        tot_dir_hits += r["dir_hits"]; tot_dir_tot += r["dir_tot"]
        if r["brier"] is not None:
            tot_brier_sum += r["brier"] * r["brier_n"]; tot_brier_n += r["brier_n"]
        # accumulate baselines (weighted by transitions / draws)
        nc = r["n_color"]
        if nc > 1:
            rep_hits += round(r["p_repeat"] * (nc - 1)); rep_tot += (nc - 1)
            bias_hits += round(r["bias"] * nc); bias_tot += nc
        fireHit = (f"{100*r['fire_hits']/r['fires']:3.0f}%" if r["fires"] else "  --")
        allHit = (f"{100*r['dir_hits']/r['dir_tot']:3.0f}%" if r["dir_tot"] else "  --")
        briersk = (f"{1 - r['brier']/0.25:+.2f}" if r["brier"] is not None else "  --")
        print(f"{label:<16} {r['n_total']:>5} {r['R']:>3}/{r['B']:<3} | "
              f"{pct(r['p_repeat'])} {pct(r['bias'])} | "
              f"{r['fires']:>5} {fireHit:>7} | {allHit:>6} {briersk:>7}")

    print("=" * 78)
    print("POOLED")
    # baselines
    if rep_tot:
        print(f"  streak-rider P(repeat) : {100*rep_hits/rep_tot:.1f}%  "
              f"({rep_hits}/{rep_tot})")
    if bias_tot:
        print(f"  colour-bias (majority) : {100*bias_hits/bias_tot:.1f}%  "
              f"({bias_hits}/{bias_tot})")

    # skill metric (all transitions)
    if tot_dir_tot:
        hr = tot_dir_hits / tot_dir_tot
        p2 = binom_two_sided(tot_dir_hits, tot_dir_tot, 0.5)
        sk = 1 - (tot_brier_sum / tot_brier_n) / 0.25 if tot_brier_n else 0
        print(f"  SKILL all-transitions  : {100*hr:.1f}%  ({tot_dir_hits}/{tot_dir_tot})"
              f"  brier-skill {sk:+.3f}  p={p2:.3f}")

    # actionable metric (confident fires)
    if tot_fires:
        hr = tot_fire_hits / tot_fires
        p2 = binom_two_sided(tot_fire_hits, tot_fires, 0.5)
        pbe = binom_ge(tot_fire_hits, tot_fires, BREAK_EVEN)
        print(f"  ACTIONABLE fires       : {100*hr:.1f}%  ({tot_fire_hits}/{tot_fires})"
              f"  p(vs50%)={p2:.3f}  p(<=breakeven {100*BREAK_EVEN:.1f}%)={pbe:.3f}")
    else:
        print("  ACTIONABLE fires       : none (model never reached the confidence margin)")

    print("-" * 78)
    # plain-language verdict
    need_more = tot_fires < 100
    print("READ:")
    if tot_fires:
        hr = tot_fire_hits / tot_fires
        if binom_two_sided(tot_fire_hits, tot_fires, 0.5) < 0.05 and hr > BREAK_EVEN:
            print("  • Confident fires beat chance AND clear the 51.4% break-even — real edge so far.")
        elif hr > 0.5:
            print("  • Fires lean correct but not yet significant — keep collecting.")
        else:
            print("  • Fires are not beating chance on this data.")
    if need_more:
        print(f"  • Only {tot_fires} confident fires pooled — aim for ~100+ "
              f"(≈15-30 dealers) before trusting the actionable number.")
    print()


if __name__ == "__main__":
    main()
