# LinupOSAI

**Linup Roulette Tracker - AI Edition**

AI-enhanced variant of the Linup roulette betting application with advanced features for intelligent bet analysis, pattern recognition, and AI-powered suggestions.

Built on the latest LinupOS game engine (v18.1.3) with a revamped, self-learning
AI that studies **how you choose betting combinations** and which of your choices
actually win.

## Features

- 🎲 **Smart Bet Calculation**: Category-based outside/inside bet classification system
- 🤖 **Self-Learning AI Coach**: Learns your combination-picking style from your own
  games — no presets, no "hot numbers". See below.
- 💰 **Investment Management**: Track multiple betting sessions with compound growth analysis
- 📊 **Live Table Mode**: Real-time filtering and bet optimization
- 🔄 **Multiple Progression Modes**: Fibonacci and Martingale (built into the engine)
- 📱 **Cross-Platform**: Windows, Android, and desktop support

## The AI (revamped)

**"Linup" = lining up — waiting for the right entry (the wave).** So the AI does
two jobs: (1) learn *when you enter vs keep waiting*, and (2) learn *which
combination* you pick once you do.

The AI is **pure Python (no numpy/sklearn)** so `flet build apk` keeps working.
It learns by imitation, weighted by outcome:

1. **Reads the board** — after you watch the first 6–10 spins, it turns the recent
   history into a compact *state signature* (the leading group of every suggestion
   category + colour balance). See [`ai_game_state.py`](ai_game_state.py).
2. **Captures your choice** — when you place a bet, it snapshots that board state
   plus the exact combination you picked.
3. **Grades it** — after the spin it records win/loss and profit, and trains
   incrementally. See [`ai_strategy_model.py`](ai_strategy_model.py).
4. **Learns the wait** — every spin where you *don't* bet is a skipped line-up,
   every spin you enter on is an entry. The *setup signature* keys on **which
   combinations have lined up** — which sector anchors (W/T/Z) and which
   lines/dozens currently show a clear pair — because you wait until *something*
   sets up rather than for one fixed group. It also learns your **typical wait
   length** adaptively (no fixed number) from how many spins you let pass before
   entering.
5. **Coaches you** — a bar under the stats shows live:
   - while learning: `AI 🧠 learning your style — N more graded bets`
   - on a selection: `AI 🧠 34+35: 65% · LIKELY WIN`
   - waiting: `AI 🧠 ENTER — your kind of line-up · 34+35 65% · waited 8/~7`
     or `AI 🧠 WAIT — you usually pass this · waited 4/~7`

It scores combinations with a Wilson lower-bound blend of (a) your record with that
exact combo in this exact board state, (b) your overall record with that combo, and
(c) a per-feature Naive-Bayes layer that generalises to new boards. `analyze()`
surfaces your **successes** (combos that work) and **errors/leaks** (combos that
drain you).

### Active AI modules

| Module | Role |
| --- | --- |
| [`ai_game_state.py`](ai_game_state.py) | Board → feature/signature extraction |
| [`ai_strategy_model.py`](ai_strategy_model.py) | Combination-choice prediction model |
| [`ai_decision_tracker.py`](ai_decision_tracker.py) | Raw per-bet event log (SQLite) |

> The earlier prototype modules (`ai_sessions`, `ai_patterns`, `ai_analysis`,
> `ai_recommendations`, `ai_learning_engine`, `ai_adaptive_recommender`) are kept
> for reference but are no longer wired into the app.

## Current Version

v18.1.3-AI

## Technology Stack

- Python 3.10+
- Flet (Flutter for Python)
- SQLite3 (learning data lives alongside game data in `linup_data.db`)

## Installation

```bash
cd LinupOSAI
bash setup.sh
```

## Running

```bash
flet run main.py
```

## Building APK

```bash
flet build apk
```

## Repository Variants

- **LinupOS**: Main desktop application
- **LinupWIN**: Windows-optimized variant
- **Linup**: Android mobile variant
- **LinupOSAI**: AI-enhanced edition (this repo)
