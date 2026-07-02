#!/usr/bin/env python3
"""
Real-bet analyzer
=================

Reads the per-spin decision log written by the app (`~/linup_data/bet_log.jsonl`,
one JSON object per spin from LinupApp._log_real_bet) and measures what the
mechanical backtest cannot: how the PLAYER's own entry selection performs.

Each record captures, at decision time: the AI suggestion on screen
(suggested dozen+colour, RVS regime), whether the player ENTERED or passed, what
they bet, and the realized outcome (win / bank delta / cost).

Reported:
  1. Entry behaviour   — how often the player enters, and after how long a wait.
  2. Realized results  — actual ROI / win-rate / net on the bets they DID place
                          (this is the ground truth to compare vs their recalled
                          per-session %).
  3. By regime         — do they enter more in BIAS / STREAK / RHYTHM, and which
                          regime actually pays when they enter?
  4. Selection value   — did following the suggested dozen beat freelancing?

Usage:  python3 ai_bet_eval.py [logfile]   (default ~/linup_data/bet_log.jsonl)
Pure stdlib.
"""

import os
import sys
import json


def load(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def _roi(rows):
    cost = sum(r.get("cost", 0) or 0 for r in rows)
    net = sum(r.get("delta", 0) or 0 for r in rows)
    return net, cost, (100 * net / cost if cost else 0.0)


def _winrate(rows):
    graded = [r for r in rows if r.get("is_win") is not None]
    if not graded:
        return None, 0
    return 100 * sum(1 for r in graded if r["is_win"]) / len(graded), len(graded)


def section(title):
    print("\n" + title)
    print("-" * max(len(title), 40))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
        "~/linup_data/bet_log.jsonl")
    rows = load(path)
    if not rows:
        print(f"no bet log yet at {path}")
        print("Play some sessions with the app — every spin is logged — then re-run.")
        return

    print(f"Real-bet analysis — {len(rows)} spins logged from {os.path.basename(path)}")
    acted = [r for r in rows if r.get("acted")]
    passed = [r for r in rows if not r.get("acted")]
    sug = [r for r in rows if (r.get("suggested") or {}).get("dozen")]

    section("1. ENTRY BEHAVIOUR")
    print(f"  spins logged      : {len(rows)}")
    print(f"  entered (bet)     : {len(acted)}  ({100*len(acted)/len(rows):.0f}%)")
    print(f"  passed (no bet)   : {len(passed)}")
    print(f"  suggestion shown  : {len(sug)}  "
          f"(entered {sum(1 for r in sug if r.get('acted'))} of them)")
    waits = [r.get("spins_since_entry") for r in acted
             if isinstance(r.get("spins_since_entry"), int)]
    if waits:
        print(f"  avg wait before entry : {sum(waits)/len(waits):.1f} spins")

    section("2. REALIZED RESULTS on bets actually placed")
    net, cost, roi = _roi(acted)
    wr, ng = _winrate(acted)
    print(f"  entries       : {len(acted)}")
    print(f"  win rate      : {wr:.0f}%  ({ng} graded)" if wr is not None else "  win rate: --")
    print(f"  net           : {net:+.2f}   staked: {cost:.2f}")
    print(f"  ROI           : {roi:+.2f}%   (net / total staked)")

    section("3. BY REGIME (entries only)")
    print(f"  {'regime':<10}{'entries':>8}{'win%':>7}{'net':>10}{'ROI%':>8}")
    kinds = {}
    for r in acted:
        kinds.setdefault((r.get("regime") or {}).get("kind", "?"), []).append(r)
    for k, rs in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        wr, _ = _winrate(rs)
        n, c, roi = _roi(rs)
        print(f"  {str(k):<10}{len(rs):>8}{(wr if wr is not None else 0):>6.0f}%"
              f"{n:>10.1f}{roi:>7.1f}%")

    section("4. SELECTION VALUE — followed the suggested dozen vs not")
    foll = [r for r in acted if r.get("followed_suggestion")]
    free = [r for r in acted if not r.get("followed_suggestion")]
    for label, rs in (("followed suggestion", foll), ("freelanced", free)):
        if not rs:
            print(f"  {label:<22}: (none)")
            continue
        wr, _ = _winrate(rs)
        n, c, roi = _roi(rs)
        print(f"  {label:<22}: {len(rs):>4} entries  win {wr:.0f}%  "
              f"net {n:+.1f}  ROI {roi:+.1f}%")

    print("\nNOTE: this is REALIZED play (what you actually bet), not the "
          "every-spin\nmechanical backtest. Compare the ROI here to your recalled "
          "per-session %.\nWith enough entries we can learn which regimes/waits "
          "your entries win on.")


if __name__ == "__main__":
    main()
