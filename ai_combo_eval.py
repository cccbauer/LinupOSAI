#!/usr/bin/env python3
"""
Combo (dozen + colour) progression evaluation harness
=====================================================

Scores the thing the money actually cares about: does the live suggestion —
a wheel-sector dozen, optionally narrowed to one colour — HIT within a 3-spin
progression, and what is the net chip result?

Per-spin colour accuracy (see `ai_rhythm_eval.py`) is the wrong yardstick when
you ride a 3-step progression: you don't need to call the next spin, you need
the committed combo to LAND at least once across the three tries. This harness
measures that directly on real croupier sequences.

Model (mirrors main.py):
  - Live dozen = a dozen + the direct wheel neighbours of every member.
  - +R / +B narrows it to the red / black members (≈ half the numbers → half
    the chips, ~double the payout share).
  - All live groups are straight-up INSIDE bets: one chip per covered number,
    35:1 on a hit.
  - Dozen is picked by wheel-SECTOR affinity over the last 6 spins; a tie -> WAIT
    (no entry), exactly like the app.
  - Progression: stake 1x, then 3x, then 5x, stopping on the first hit.

For each entry we replay the ACTUAL next 3 spins under the progression and tally
net chips. Compared modes:
  dozen-only  — no colour filter (what the app bets when no pattern locks)
  +R / +B     — always that colour
  PATTERN     — the colour PatternDetector commits to (else dozen-only)
  RHYTHM      — the colour RhythmModel is confident about (else dozen-only)
  ORACLE      — best of {none,R,B} per entry using the real outcome (upper bound,
                cheats by peeking; shows the ceiling a perfect colour-picker hits)

Usage:  python3 ai_combo_eval.py [datafile ...]
        (defaults to croupier_data.txt; pass ~/linup_data/croupier_log.txt to
         include your played sessions)
Pure stdlib; imports parse_file / models from the existing AI modules.
"""

import sys
import os

from ai_rhythm_eval import parse_file, ROJOS
from ai_pattern import PatternDetector
from ai_rhythm import RhythmModel

# ── layout geometry (mirrors main.py) ────────────────────────────────────────
WHEEL_ORDER = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8,
               23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12,
               35, 3, 26]
WHEEL_NEIGHBORS = {
    n: {WHEEL_ORDER[(i - 1) % 37], WHEEL_ORDER[(i + 1) % 37]}
    for i, n in enumerate(WHEEL_ORDER)
}


def _live_grp(base):
    return base | set().union(*(WHEEL_NEIGHBORS[n] for n in base))


DOZENS = {'1a': set(range(1, 13)), '2a': set(range(13, 25)), '3a': set(range(25, 37))}
LIVE = {d: _live_grp(s) for d, s in DOZENS.items()}
# 0 is a wheel neighbour of 3a members (26, 32) -> included in 3a colour groups
LIVE_R = {d: (LIVE[d] & ROJOS) | ({0} if d == '3a' else set()) for d in DOZENS}
LIVE_B = {d: (LIVE[d] - ROJOS - {0}) | ({0} if d == '3a' else set()) for d in DOZENS}

SECTORS = {
    'Z0': {0, 3, 12, 15, 26, 32, 35},
    'ZG': {2, 4, 7, 18, 21, 19, 22, 25, 28, 29},
    'ZP': {5, 8, 10, 11, 13, 16, 23, 24, 27, 30, 33, 36},
    'H':  {1, 6, 9, 14, 17, 20, 31, 34},
}
SECTOR_OF = {n: s for s, nums in SECTORS.items() for n in nums}
DOZEN_SECTOR_AFFINITY = {
    d: {s: len(LIVE[d] & SECTORS[s]) / len(SECTORS[s]) for s in SECTORS}
    for d in DOZENS
}

WARMUP = 6            # spins of history before the sector pick is meaningful
PROGRESSION = (1, 2, 3)   # chip multipliers per step; stop on first hit (real play)
STRAIGHT_UP_RETURN = 36   # 35:1 win + own stake back, on the one hitting number
# Real-money framing for the risk report: min chip and bankroll. Max loss on an
# entry (all 3 steps miss) = coverage * chip * sum(PROGRESSION). Player cap: 2%.
CHIP_USD = 0.1
BANK_USD = 924.0


# ── the app's live dozen pick (sector affinity over last 6, WAIT on tie) ─────
def pick_dozen(window6):
    sc = {d: sum(DOZEN_SECTOR_AFFINITY[d].get(SECTOR_OF.get(n), 0.0)
                 for n in window6) / 6.0
          for d in DOZENS}
    ranked = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
    if ranked[0][1] <= 0:
        return None
    if len(ranked) > 1 and abs(ranked[0][1] - ranked[1][1]) < 1e-9:
        return None   # tie -> WAIT, no entry
    return ranked[0][0]


# ── dozen-CONDITIONED colour picker (the prototype) ──────────────────────────
# Instead of reading the raw B/R stream (what PatternDetector / RhythmModel do),
# look only at spins that landed in the dozen we're about to ride, and commit to
# whichever colour-half of THAT dozen has been hotter — but only when the lean
# clears a margin, else stay dozen-only (colour must beat the false-commit risk).
COND_WINDOW = 12     # recent spins considered  (mirror of main.py COND_WINDOW)
COND_MARGIN = 0.15   # |frac_red_in_dozen - 0.5| must exceed this to commit
COND_MIN = 4         # need at least this many in-dozen landings to have a read


def pick_color_conditioned(dozen, history,
                           window=None, margin=None, min_count=None):
    window = COND_WINDOW if window is None else window
    margin = COND_MARGIN if margin is None else margin
    min_count = COND_MIN if min_count is None else min_count
    recent = history[-window:]
    r = sum(1 for n in recent if n in LIVE_R[dozen])
    b = sum(1 for n in recent if n in LIVE_B[dozen])
    tot = r + b
    if tot < min_count:
        return None
    frac = r / tot
    if frac >= 0.5 + margin:
        return 'R'
    if frac <= 0.5 - margin:
        return 'B'
    return None


# ── RHYTHM-vs-STREAK regime colour picker (RVS) ──────────────────────────────
# Human-spotted pattern: a dealer is either RHYTHMIC (colours churn, runs stay
# short ≤~4) or STREAKY (sustained same-colour runs of 5+). Classify the regime
# from the recent repeat-probability P(next == last):
#   P(repeat) >= streak_thr  -> STREAKY  -> ride the run  (bet the last colour)
#   P(repeat) <= rhythm_thr  -> RHYTHMIC -> expect a break (bet the flip), but
#                               only once the current run has some length
#   in between               -> no call  (stay dozen-only)
# This is a 1st-order colour-regime read; unlike COND it ignores the dozen and
# looks purely at run structure, which is what the eye is picking up.
RVS_WINDOW = 12
RVS_STREAK_THR = 0.60   # P(repeat) >= this -> streaky (ride)
RVS_RHYTHM_THR = 0.40   # P(repeat) <= this -> rhythmic (flip)
RVS_MIN = 6             # min colours in window before any call
RVS_RHYTHM_RUN = 2      # rhythmic side only flips once the run is at least this
# GUARD (from watching dealer-05 & 06:49): a dealer can slip from rhythm INTO a
# streak mid-session. Once the CURRENT run reaches this length you are in a
# streak now — RIDE it, and never flip into it — regardless of the overall
# regime read. This is the user's own line: runs >4-5 = streak, not rhythm.
RVS_RIDE_LEN = 4        # current run >= this -> force ride (override the flip)
# THIRD regime (from dealer-05: 63% red = biased, not rhythmic). When one colour
# dominates the recent window, just ride the dominant colour — flipping fights
# the bias and bleeds. Highest precedence: bias overrides run/rhythm reads.
RVS_BIAS_MARGIN = 0.15  # |frac_red - 0.5| >= this -> biased (>=65% one colour)


def _colors_in(history):
    return [1 if n in ROJOS else 0 for n in history if n != 0]


def regime_color(history, window=None, streak_thr=None, rhythm_thr=None,
                 min_n=None, rhythm_run=None, ride_len=None, bias_margin=None):
    window = RVS_WINDOW if window is None else window
    streak_thr = RVS_STREAK_THR if streak_thr is None else streak_thr
    rhythm_thr = RVS_RHYTHM_THR if rhythm_thr is None else rhythm_thr
    min_n = RVS_MIN if min_n is None else min_n
    rhythm_run = RVS_RHYTHM_RUN if rhythm_run is None else rhythm_run
    ride_len = RVS_RIDE_LEN if ride_len is None else ride_len
    bias_margin = RVS_BIAS_MARGIN if bias_margin is None else bias_margin
    cols = _colors_in(history)[-window:]
    if len(cols) < min_n:
        return None
    reps = sum(cols[i] == cols[i - 1] for i in range(1, len(cols)))
    prep = reps / (len(cols) - 1)
    frac_red = sum(cols) / len(cols)
    last = cols[-1]
    # current trailing run length
    run = 1
    for i in range(len(cols) - 2, -1, -1):
        if cols[i] == last:
            run += 1
        else:
            break
    if abs(frac_red - 0.5) >= bias_margin:     # BIAS: ride the dominant colour
        pred = 1 if frac_red > 0.5 else 0
    elif run >= ride_len:                      # STREAK now: ride the run
        pred = last
    elif prep >= streak_thr and run >= 2:      # streaky dealer: ride the run
        pred = last
    elif prep <= rhythm_thr and run >= rhythm_run:  # rhythmic: break due -> flip
        pred = 1 - last
    else:
        return None
    return 'R' if pred == 1 else 'B'


def combo_numbers(dozen, colour):
    if colour == 'R':
        return LIVE_R[dozen]
    if colour == 'B':
        return LIVE_B[dozen]
    return LIVE[dozen]


def progression_pl(combo, next_spins):
    """Net chips over one entry: place 1x/3x/5x, stop on first hit.

    Each covered number carries `stake` chips; a hit returns 36*stake on the one
    number that landed. Returns (net_chips, hit_bool, chips_staked)."""
    K = len(combo)
    pl = 0
    staked = 0
    hit = False
    for stake, spin in zip(PROGRESSION, next_spins):
        pl -= stake * K            # one chip per number, this step
        staked += stake * K
        if spin in combo:
            pl += STRAIGHT_UP_RETURN * stake
            hit = True
            break
    return pl, hit, staked


# ── per-dealer entry set + colour signals (predict-before-observe) ───────────
def entries_for(nums):
    """Yield (entry_index, dozen, pat_colour, rhy_colour) for each valid entry.

    An entry exists at spin i when there are >=WARMUP prior spins, >=3 forward
    spins to ride the progression, and the dozen pick isn't a WAIT tie."""
    pat = PatternDetector(ROJOS)
    rhy = RhythmModel(ROJOS)
    for i in range(len(nums)):
        # signals are computed from spins strictly before i (no leakage)
        if WARMUP <= i <= len(nums) - 3:
            dozen = pick_dozen(nums[i - 6:i])
            if dozen is not None:
                pc = None
                try:
                    pc = pat.predict_color()
                except Exception:
                    pc = None
                rc = rhy.confident_color()
                yield i, dozen, pc, rc
        # now fold spin i into the online models for the next iteration
        pat.observe_num(nums[i])
        rhy.observe_num(nums[i])


MODES = ['dozen', '+R', '+B', 'PATTERN', 'RHYTHM', 'COND', 'RVS', 'ORACLE']


def eval_dealer(nums):
    """Return per-mode {entries, hits, net, chips} for one dealer."""
    acc = {m: {'entries': 0, 'hits': 0, 'net': 0, 'chips': 0} for m in MODES}
    for i, dozen, pc, rc in entries_for(nums):
        nxt = nums[i:i + 3]
        colour_for = {
            'dozen': None, '+R': 'R', '+B': 'B',
            'PATTERN': pc, 'RHYTHM': rc,
            'COND': pick_color_conditioned(dozen, nums[:i]),
            'RVS': regime_color(nums[:i]),
        }
        # ORACLE: whichever of {none,R,B} gives the best net on the real outcome
        best = None
        for c in (None, 'R', 'B'):
            pl, _, _ = progression_pl(combo_numbers(dozen, c), nxt)
            if best is None or pl > best[0]:
                best = (pl, c)
        colour_for['ORACLE'] = best[1]
        for m in MODES:
            pl, hit, staked = progression_pl(
                combo_numbers(dozen, colour_for[m]), nxt)
            a = acc[m]
            a['entries'] += 1
            a['hits'] += int(hit)
            a['net'] += pl
            a['chips'] += staked
    return acc


# ── report ───────────────────────────────────────────────────────────────────
def sweep_cond(dealers):
    """Grid-search the conditioned picker's (window, margin) over the dealers.

    Scores by net-chip improvement over dozen-only, summed per dealer, plus how
    many dealers it helped vs hurt — so we don't just chase raw net on one lucky
    dealer. Exploratory only: with few dealers this WILL overfit; treat the grid
    as a sensitivity check, not a tuned setting."""
    global COND_WINDOW, COND_MARGIN
    print("\nCOND sweep — improvement over dozen-only (net chips), summed / dealer")
    print(f"{'win':>4}{'margin':>8}{'sumΔnet':>9}{'helped':>8}{'hurt':>6}")
    print("-" * 36)
    rows = []
    for w in (6, 9, 12, 15):
        for mgn in (0.10, 0.15, 0.20, 0.25):
            COND_WINDOW, COND_MARGIN = w, mgn
            dnet = helped = hurt = 0
            for _, nums in dealers:
                acc = eval_dealer(nums)
                if not acc['dozen']['entries']:
                    continue
                delta = acc['COND']['net'] - acc['dozen']['net']
                dnet += delta
                helped += int(delta > 0)
                hurt += int(delta < 0)
            rows.append((dnet, helped, hurt, w, mgn))
            print(f"{w:>4}{mgn:>8.2f}{dnet:>9}{helped:>8}{hurt:>6}")
    best = max(rows, key=lambda r: (r[1] - r[2], r[0]))
    print("-" * 36)
    print(f"best by (helped−hurt, then Δnet): window={best[3]} margin={best[4]:.2f} "
          f"→ sumΔnet {best[0]:+}, helped {best[1]}, hurt {best[2]}")
    COND_WINDOW, COND_MARGIN = best[3], best[4]
    print(f"(using window={COND_WINDOW} margin={COND_MARGIN:.2f} for the table below)\n")


def sweep_rvs(dealers):
    """Grid-search RVS (streak_thr, rhythm_thr) — the regime cut-points — by
    net-chip improvement over dozen-only, summed per dealer. Exploratory; with
    few dealers it overfits, so read it as a sensitivity check."""
    global RVS_STREAK_THR, RVS_RHYTHM_THR
    print("\nRVS sweep — improvement over dozen-only (net chips), summed / dealer")
    print(f"{'streak≥':>8}{'rhythm≤':>9}{'sumΔnet':>9}{'helped':>8}{'hurt':>6}")
    print("-" * 40)
    rows = []
    for st in (0.55, 0.60, 0.65, 0.70):
        for rh in (0.30, 0.35, 0.40, 0.45):
            RVS_STREAK_THR, RVS_RHYTHM_THR = st, rh
            dnet = helped = hurt = 0
            for _, nums in dealers:
                acc = eval_dealer(nums)
                if not acc['dozen']['entries']:
                    continue
                delta = acc['RVS']['net'] - acc['dozen']['net']
                dnet += delta
                helped += int(delta > 0)
                hurt += int(delta < 0)
            rows.append((dnet, helped, hurt, st, rh))
            print(f"{st:>8.2f}{rh:>9.2f}{dnet:>9}{helped:>8}{hurt:>6}")
    best = max(rows, key=lambda r: (r[1] - r[2], r[0]))
    print("-" * 40)
    print(f"best by (helped−hurt, then Δnet): streak≥{best[3]:.2f} rhythm≤{best[4]:.2f} "
          f"→ sumΔnet {best[0]:+}, helped {best[1]}, hurt {best[2]}")
    RVS_STREAK_THR, RVS_RHYTHM_THR = best[3], best[4]
    print(f"(using streak≥{RVS_STREAK_THR:.2f} rhythm≤{RVS_RHYTHM_THR:.2f} below)\n")


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--sweep")]
    do_sweep = "--sweep" in sys.argv
    do_sweep_rvs = "--sweep-rvs" in sys.argv
    paths = argv or [os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "croupier_data.txt")]
    dealers = []
    for p in paths:
        if not os.path.exists(p):
            print(f"data file not found: {p}")
            continue
        dealers += parse_file(p)
    if not dealers:
        print("no croupier data found.")
        return

    if do_sweep:
        sweep_cond(dealers)
    if do_sweep_rvs:
        sweep_rvs(dealers)

    print(f"\nCombo progression eval — {len(dealers)} croupier(s)")
    print(f"progression {PROGRESSION} chips (stop on hit) · straight-up 35:1 · "
          f"WARMUP {WARMUP} spins · WAIT on tie")
    print("Each dealer is INDEPENDENT — the question per dealer is whether the "
          "AI\npicks THAT dealer's profitable colour. net = won − staked "
          "(chips).")
    print("=" * 78)

    # Per-dealer NET result for each mode (independence respected — no pooling
    # of the colour decision across dealers). Best colour = the dealer's own.
    print(f"{'dealer':<14}{'entries':>7}" +
          "".join(f"{m:>9}" for m in MODES) + "  bestC  AIpick?")
    print("-" * 78)
    wins = {m: 0 for m in MODES}          # dealers where this mode is net>0
    beats = {m: 0 for m in ('+R', '+B', 'PATTERN', 'RHYTHM', 'COND', 'RVS')}
    pat_matched = 0
    graded = 0
    for label, nums in dealers:
        acc = eval_dealer(nums)
        e = acc['dozen']['entries']
        row = f"{label:<14}{e:>7}"
        for m in MODES:
            row += f"{acc[m]['net']:>9}"
            if acc[m]['net'] > 0:
                wins[m] += 1
        # this dealer's own best colour (by net): none / R / B
        best_c = max((None, 'R', 'B'),
                     key=lambda c: acc[{'R': '+R', 'B': '+B', None: 'dozen'}[c]]['net'])
        best_lbl = {None: 'none', 'R': 'R', 'B': 'B'}[best_c]
        # did PATTERN's net at least match dozen-only for this dealer?
        if e:
            graded += 1
            if acc['PATTERN']['net'] >= acc['dozen']['net']:
                pat_matched += 1
        for m in ('+R', '+B', 'PATTERN', 'RHYTHM', 'COND', 'RVS'):
            if e and acc[m]['net'] > acc['dozen']['net']:
                beats[m] += 1
        ai_ok = 'yes' if e and acc['PATTERN']['net'] >= acc['dozen']['net'] else 'no'
        row += f"  {best_lbl:>5}  {ai_ok:>6}"
        print(row)

    n = len(dealers)
    print("-" * 78)
    print("READ (counting dealers, since dealers are independent):")
    print(f"  • dozen-only is net-positive on {wins['dozen']}/{n} dealers — "
          f"the safe baseline barely clears zero.")
    for m in ('PATTERN', 'RHYTHM', 'COND', 'RVS'):
        print(f"  • {m}: net-positive on {wins[m]}/{n} dealers; "
              f"≥ dozen-only on {beats[m]}/{n}.")
    print(f"  • PATTERN did NOT hurt vs dozen-only on {pat_matched}/{graded} "
          f"dealers (the key safety bar — colour should never make it worse).")
    print(f"  • ORACLE (perfect per-dealer colour) is net-positive on "
          f"{wins['ORACLE']}/{n} — the headroom a better colour-picker unlocks.")
    if n < 15:
        print(f"  • Only {n} dealers — collect ~15+ INDEPENDENT croupiers before "
              f"trusting this (each contributes one vote).")
    print()


if __name__ == "__main__":
    main()
