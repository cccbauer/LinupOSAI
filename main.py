import flet as ft
from collections import deque
import sqlite3
import os
import math
import random
from datetime import datetime
import asyncio
import csv
import inspect
import uuid
from pathlib import Path

# --- AI: combination-choice learning system ---
from ai_game_state import GameStateExtractor
from ai_strategy_model import StrategyModel, MIN_TRAINED_OBS
from ai_rhythm import RhythmModel, RHYTHM_WARMUP
from ai_pattern import PatternDetector, PATTERN_WARMUP
try:
    from ai_decision_tracker import DecisionTracker, Decision
    _HAS_DECISION_TRACKER = True
except Exception:
    _HAS_DECISION_TRACKER = False

# --- GROUP CONFIGURATION ---
ROJOS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
GRUPOS_MAESTROS = {
    '34': {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34},
    '35': {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35},
    '36': {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36},
    '1a': set(range(1, 13)), '2a': set(range(13, 25)), '3a': set(range(25, 37)),
    'Z0': {0, 3, 12, 15, 26, 32, 35},
    'ZG': {2, 4, 7, 18, 21, 19, 22, 25, 28, 29},
    'ZP': {5, 8, 10, 11, 13, 16, 23, 24, 27, 30, 33, 36},
    'H':  {1, 6, 9, 14, 17, 20, 31, 34},
    'T1': {2, 4, 6, 13, 15, 17, 19, 21, 25, 27, 32, 34},
    'T2': {1, 5, 8, 10, 11, 16, 20, 23, 24, 30, 33, 36},
    'T3': {0, 3, 7, 9, 12, 14, 18, 22, 26, 28, 29, 31, 35},
    # Wave zones — wheel position relative to 0
    # W1 Lip:    0 + 6 each side  → 13 numbers
    'W1': {0, 2, 3, 4, 7, 12, 15, 19, 21, 26, 28, 32, 35},
    # W2 Curls:  next 6 each side → 12 numbers
    'W2': {6, 9, 13, 14, 17, 18, 22, 25, 27, 29, 31, 34},
    # W3 Through: remaining       → 12 numbers
    'W3': {1, 5, 8, 10, 11, 16, 20, 23, 24, 30, 33, 36},
    # Filter groups (for mixer combinations)
    'R': ROJOS,
    'B': set(range(1, 37)) - ROJOS,
    'Even': {n for n in range(2, 37, 2)},
    'Odd': {n for n in range(1, 37, 2)},
    '1-18': set(range(1, 19)),
    '19-36': set(range(19, 37)),
}
PROG_FIBO = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
C_COL, C_DOC, C_SEC, C_SET, C_WAV = '#00d2ff', '#2ecc71', '#e67e22', '#9b59b6', '#e91e63'
C_FLT_R, C_FLT_B, C_FLT_E, C_FLT_O, C_FLT_18, C_FLT_36 = '#c0392b', '#222222', '#446644', '#664444', '#555577', '#445566'
NUM_COLS = 20

# ── Wheel neighbours (European single-zero wheel order) ──────────────
WHEEL_ORDER = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
WHEEL_NEIGHBORS = {
    n: {WHEEL_ORDER[(i - 1) % 37], WHEEL_ORDER[(i + 1) % 37]}
    for i, n in enumerate(WHEEL_ORDER)
}
# Live dozen groups: each dozen + direct wheel neighbours of every member
def _live_grp(base):
    return base | set().union(*(WHEEL_NEIGHBORS[n] for n in base))

LIVE_FILTER_SETS = {
    'R':     ROJOS,
    'B':     set(range(1, 37)) - ROJOS,
    '1-18':  set(range(1, 19)),
    'Even':  {n for n in range(2, 37, 2)},
    'Odd':   {n for n in range(1, 37, 2)},
    '19-36': set(range(19, 37)),
}
# Suffix maps for building group keys from filter
_DOC_SFX = {None: '_L', 'R': '_LR', 'B': '_LB',
            '1-18': '_L18', 'Even': '_LE', 'Odd': '_LO', '19-36': '_L36'}
_COL_SFX = {None: '', 'R': '_R', 'B': '_B',
            '1-18': '_18', 'Even': '_E', 'Odd': '_O', '19-36': '_36'}

for _d in ('1a', '2a', '3a'):
    GRUPOS_MAESTROS[f'{_d}_L']   = _live_grp(GRUPOS_MAESTROS[_d])
    GRUPOS_MAESTROS[f'{_d}_LR']  = GRUPOS_MAESTROS[f'{_d}_L'] & ROJOS
    GRUPOS_MAESTROS[f'{_d}_LB']  = GRUPOS_MAESTROS[f'{_d}_L'] - ROJOS - {0}
    GRUPOS_MAESTROS[f'{_d}_L18'] = GRUPOS_MAESTROS[f'{_d}_L'] & LIVE_FILTER_SETS['1-18']
    GRUPOS_MAESTROS[f'{_d}_LE']  = GRUPOS_MAESTROS[f'{_d}_L'] & LIVE_FILTER_SETS['Even']
    GRUPOS_MAESTROS[f'{_d}_LO']  = GRUPOS_MAESTROS[f'{_d}_L'] & LIVE_FILTER_SETS['Odd']
    GRUPOS_MAESTROS[f'{_d}_L36'] = GRUPOS_MAESTROS[f'{_d}_L'] & LIVE_FILTER_SETS['19-36']
# 0 is a wheel neighbour of 3a numbers (26, 32) → include it in every 3a filtered group
for _sfx in ('_LR', '_LB', '_L18', '_LE', '_LO', '_L36'):
    GRUPOS_MAESTROS[f'3a{_sfx}'] |= {0}
for _c in ('34', '35', '36'):
    GRUPOS_MAESTROS[f'{_c}_R']  = GRUPOS_MAESTROS[_c] & ROJOS
    GRUPOS_MAESTROS[f'{_c}_B']  = GRUPOS_MAESTROS[_c] - ROJOS - {0}
    GRUPOS_MAESTROS[f'{_c}_18'] = GRUPOS_MAESTROS[_c] & LIVE_FILTER_SETS['1-18']
    GRUPOS_MAESTROS[f'{_c}_E']  = GRUPOS_MAESTROS[_c] & LIVE_FILTER_SETS['Even']
    GRUPOS_MAESTROS[f'{_c}_O']  = GRUPOS_MAESTROS[_c] & LIVE_FILTER_SETS['Odd']
    GRUPOS_MAESTROS[f'{_c}_36'] = GRUPOS_MAESTROS[_c] & LIVE_FILTER_SETS['19-36']
# All live / filtered groups are inside bets (one chip per number)
GRUPOS_LIVE_INSIDE: set = set()
for _d in ('1a', '2a', '3a'):
    for _sfx in _DOC_SFX.values():
        GRUPOS_LIVE_INSIDE.add(f'{_d}{_sfx}')
for _c in ('34', '35', '36'):
    for _sfx in _COL_SFX.values():
        if _sfx:   # empty suffix = standard column (stays as outside)
            GRUPOS_LIVE_INSIDE.add(f'{_c}{_sfx}')

# ── Wheel-sector affinity for the live dozen suggestion ──────────────
# The sectors Z0/ZG/ZP/H partition all 37 numbers, so every spin sits in
# exactly one sector. Each live dozen zone (Na_L) overlaps the sectors by
# different amounts, so a "hot" sector favours the dozen whose wheel-zone
# best covers it (e.g. Z0→3a, ZG→1a, H→2a/3a). Precompute:
#   SECTOR_OF[n]                 -> the sector containing number n
#   DOZEN_SECTOR_AFFINITY[d][s]  -> fraction of sector s covered by d_L
_SECTORS = ('Z0', 'ZG', 'ZP', 'H')
SECTOR_OF = {}
for _s in _SECTORS:
    for _n in GRUPOS_MAESTROS[_s]:
        SECTOR_OF[_n] = _s
DOZEN_SECTOR_AFFINITY = {
    _d: {_s: len(GRUPOS_MAESTROS[f'{_d}_L'] & GRUPOS_MAESTROS[_s]) / len(GRUPOS_MAESTROS[_s])
         for _s in _SECTORS}
    for _d in ('1a', '2a', '3a')
}

# ── Dozen-CONDITIONED colour picker (COND) ───────────────────────────────────
# Colour the live dozen suggestion by which colour-half of the SUGGESTED dozen
# has been landing more over the recent window — committing only when the lean
# clears a margin, else staying dozen-only. This beats reading the raw B/R
# stream (the old PatternDetector overlay) because the exploitable edge is a
# joint dozen×colour property, not a property of the colour sequence alone.
# Validated per-dealer in ai_combo_eval.py (net-chip terms under the 1/3/5
# progression). The window is a live sliding read, so it self-adapts every
# session; re-tune the two constants as more sessions are logged with:
#     python3 ai_combo_eval.py --sweep ~/linup_data/croupier_log.txt
COND_WINDOW = 12     # recent spins considered
COND_MARGIN = 0.15   # |frac_red_in_dozen - 0.5| must exceed this to commit
COND_MIN    = 4      # need at least this many in-dozen landings for a read


def cond_color_for(dozen, history):
    """'R' / 'B' / None — the colour to append to a live dozen suggestion.

    Looks only at spins that landed in `dozen`'s live colour groups over the
    recent window; returns None (stay dozen-only) unless one colour clears the
    margin. Reuses GRUPOS_MAESTROS so the covered numbers never drift from the
    bet the app actually places (incl. the 0 folded into 3a groups)."""
    reds = GRUPOS_MAESTROS.get(f'{dozen}_LR', ())
    blacks = GRUPOS_MAESTROS.get(f'{dozen}_LB', ())
    recent = history[-COND_WINDOW:] if history else []
    r = sum(1 for n in recent if n in reds)
    b = sum(1 for n in recent if n in blacks)
    tot = r + b
    if tot < COND_MIN:
        return None
    frac = r / tot
    if frac >= 0.5 + COND_MARGIN:
        return 'R'
    if frac <= 0.5 - COND_MARGIN:
        return 'B'
    return None


# ── RHYTHM-vs-STREAK-vs-BIAS colour picker (RVS) — the deployed overlay ───────
# Classifies the croupier's recent colour regime and rides / flips accordingly:
#   BIAS   (>=65% one colour in window)      -> ride the dominant colour
#   STREAK (current run >= RIDE_LEN, or high P(repeat)) -> ride the run
#   RHYTHM (short runs, low P(repeat))                  -> flip (a break is due)
#   else                                                -> no colour (dozen only)
# Replaced COND as the overlay: under the real 1x-2x-3x combo (chip-in)
# progression and the player's 2% max-loss cap, RVS is the best risk-adjusted
# colour picker we have — it covers ~14 numbers (max loss ~1.3% of bank) vs the
# bare dozen's ~28 (~1.8%), so the combo can be sized up within the 2% budget.
# Encodes the operator's own read (bias / streak / rhythm). PROVISIONAL: tuned
# in-sample on ~13 dealers; re-validate held-out as sessions accrue via
#     python3 ai_combo_eval.py --sweep-rvs ~/linup_data/croupier_log.txt
RVS_WINDOW, RVS_STREAK_THR, RVS_RHYTHM_THR = 12, 0.60, 0.40
RVS_MIN, RVS_RHYTHM_RUN, RVS_RIDE_LEN, RVS_BIAS_MARGIN = 6, 2, 4, 0.15
# Live, TUNABLE config. The deployed values above are the defaults; a validated
# candidate the player applies from the Bet Eval page overwrites this dict (and
# is persisted to linup_data/rvs_config.json, reloaded at startup). Never
# auto-applied — only on explicit approval after passing a held-out test.
RVS_CFG = {'window': RVS_WINDOW, 'streak': RVS_STREAK_THR, 'rhythm': RVS_RHYTHM_THR,
           'min': RVS_MIN, 'rhythm_run': RVS_RHYTHM_RUN, 'ride_len': RVS_RIDE_LEN,
           'bias': RVS_BIAS_MARGIN}


def _regime(history, cfg=None):
    """Classify the recent colour regime under `cfg` (defaults to live RVS_CFG).
    Returns (pred_bit|None, kind, detail); kind in
    'watching' / 'BIAS' / 'STREAK' / 'RHYTHM' / 'none'."""
    c = cfg or RVS_CFG
    cols = [1 if n in ROJOS else 0 for n in history if n != 0][-int(c['window']):]
    if len(cols) < c['min']:
        return (None, 'watching', {'n': len(cols)})
    reps = sum(cols[i] == cols[i - 1] for i in range(1, len(cols)))
    prep = reps / (len(cols) - 1)
    frac_red = sum(cols) / len(cols)
    last = cols[-1]
    run = 1
    for i in range(len(cols) - 2, -1, -1):
        if cols[i] == last:
            run += 1
        else:
            break
    if abs(frac_red - 0.5) >= c['bias']:            # BIAS: ride dominant
        return (1 if frac_red > 0.5 else 0, 'BIAS', {'frac': frac_red})
    if run >= c['ride_len']:                        # STREAK now: ride run
        return (last, 'STREAK', {'run': run})
    if prep >= c['streak'] and run >= 2:            # streaky: ride
        return (last, 'STREAK', {'run': run})
    if prep <= c['rhythm'] and run >= c['rhythm_run']:  # rhythmic: flip
        return (1 - last, 'RHYTHM', {'run': run})
    return (None, 'none', {'prep': prep, 'frac': frac_red})


def regime_color(history, cfg=None):
    """'R' / 'B' / None — colour to append to the live dozen suggestion."""
    pred, _, _ = _regime(history, cfg)
    if pred is None:
        return None
    return 'R' if pred == 1 else 'B'


def regime_status(history):
    """Human-readable one-liner for the AI bar, reflecting the RVS overlay."""
    pred, kind, d = _regime(history)
    col = 'R' if pred == 1 else ('B' if pred == 0 else None)
    if kind == 'watching':
        return f"watching… {d['n']}/{RVS_MIN} colours"
    if kind == 'BIAS':
        return f"BIAS {int(round(max(d['frac'], 1 - d['frac']) * 100))}% → bet {col}"
    if kind == 'STREAK':
        return f"STREAK ×{d['run']} → ride {col}"
    if kind == 'RHYTHM':
        return f"RHYTHM → flip {col}"
    return "no clear regime — dozen only"


class LinupApp:
    def __init__(self, page: ft.Page):
        self.page = page

        self.mixer_btns: dict = {}
        self.lbl_bank = None
        self.lbl_inv  = None
        self.lbl_pl   = None
        self.sug_row  = None
        self.btn_inv  = None
        self.reg_rows_box   = None
        self.reg_header_row = None
        self._on_game_screen = False
        self.current_investment_id = None
        self.lbl_inv_pl = None

        self.page.title      = "Linup v19.1.3-AI"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor    = '#1a1a1a'
        self.page.padding    = 0
        self.page.scroll     = None
        self.page.update()          # paint dark background before anything else loads
        self.page.on_resized = self._on_resize

        # Desktop-only window sizing (Android/iOS fill screen natively)
        _mobile = self.page.platform in (
            ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
        if not _mobile:
            try:
                import sys as _sys, ctypes as _ct, ctypes.util as _ctu

                if _sys.platform == 'darwin':
                    class _R(ctypes.Structure):
                        _fields_ = [('x', _ct.c_double), ('y', _ct.c_double),
                                    ('w', _ct.c_double), ('h', _ct.c_double)]
                    _cg = _ct.cdll.LoadLibrary(_ctu.find_library('CoreGraphics'))
                    _cg.CGMainDisplayID.restype = _ct.c_uint32
                    _cg.CGDisplayBounds.restype = _R
                    _b = _cg.CGDisplayBounds(_cg.CGMainDisplayID())
                    screen_h = int(_b.h)
                elif _sys.platform == 'win32':
                    screen_h = _ct.windll.user32.GetSystemMetrics(1)
                else:
                    import tkinter as _tk
                    _r = _tk.Tk(); _r.withdraw(); _r.update()
                    screen_h = _r.winfo_screenheight()
                    _r.destroy()
            except Exception:
                screen_h = 900
            win_h = max(int(screen_h * 9 / 8), 600)
            self.page.window.width      = 420
            self.page.window.height     = win_h
            self.page.window.min_width  = 380
            self.page.window.min_height = 600
            self.page.window.left       = 0
            self.page.window.top        = 0

        self.root = ft.Container(expand=True, bgcolor='#1a1a1a')
        self.page.add(self.root)
        self.page.update()

        self.show_splash()
        self.init_db()
        self.reset_variables()
        self._init_ai_systems()      # AI: combination-choice learning
        self.page.run_task(self._after_splash)

    def _init_ai_systems(self):
        """Initialise the AI that learns how the player picks combinations.

        Everything is wrapped so the app keeps working even if the AI fails.
        """
        self.ai_ok = False
        self.current_choice = None      # snapshot held between bet and result
        self.current_decision_id = None
        self.spins_since_entry = 0      # adaptive line-up wait counter
        self.rhythm_model = None        # live B/R rhythm predictor (per croupier)
        self.pattern_model = None       # observe-20-then-commit colour pattern
        try:
            self.state_extractor = GameStateExtractor(GRUPOS_MAESTROS,
                                                      WHEEL_NEIGHBORS)
            self.strategy_model = StrategyModel(self.db_path, self.state_extractor)
            self.rhythm_model = RhythmModel(ROJOS)
            self.pattern_model = PatternDetector(ROJOS)
            if _HAS_DECISION_TRACKER:
                try:
                    self.decision_tracker = DecisionTracker(db_path=self.db_path)
                except Exception:
                    self.decision_tracker = None
            else:
                self.decision_tracker = None
            self.ai_ok = True
        except Exception as e:
            print(f"AI init warning: {e}")
            self.ai_ok = False

    async def _after_splash(self):
        await asyncio.sleep(4.0)
        self.show_main_menu()

    # ──────────────────────────────────────────────────────────────────
    # TEXT HELPER
    # ──────────────────────────────────────────────────────────────────
    def _txt(self, label, size=15, bold=True):
        return ft.Text(
            label, size=size,
            weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
            text_align=ft.TextAlign.CENTER,
        )

    # ──────────────────────────────────────────────────────────────────
    # RESPONSIVE COLUMN WIDTH
    # ──────────────────────────────────────────────────────────────────
    def _col_width(self):
        w  = self.page.width or 360
        vc = getattr(self, 'visible_cats', {k: True for k in ['basic','cols','docs','secs','thirds','wave']})
        n  = (1
              + (6 if vc.get('basic',  True) else 0)
              + (3 if vc.get('cols',   True) else 0)
              + (3 if vc.get('docs',   True) else 0)
              + (4 if vc.get('secs',   True) else 0)
              + (3 if vc.get('thirds', True) else 0)
              + (3 if vc.get('wave',   True) else 0))
        return max(11, int((w - 4) / max(n, 1)))

    def _on_resize(self, e):
        if self._on_game_screen and self.reg_rows_box is not None:
            self.update_registration_table()

    # ──────────────────────────────────────────────────────────────────
    # DATABASE
    # ──────────────────────────────────────────────────────────────────
    def init_db(self):
        self.db_error = None
        candidates = []
        asp = getattr(self.page, 'app_support_path', None)
        if asp:
            candidates.append(os.path.join(str(asp), "linup_data"))
        candidates += [
            os.path.join(os.path.expanduser("~"), "linup_data"),
            os.path.join(os.getcwd(), "linup_data"),
            os.path.join("/tmp", "linup_data"),
        ]
        self.db_path = None
        for data_dir in candidates:
            try:
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "linup_data.db")
                conn = sqlite3.connect(db_path)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS sesiones "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    " mesa TEXT, fecha TEXT, profit REAL, "
                    " banca_inicial REAL, banca_final REAL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS table_stats "
                    "(investment_id INTEGER NOT NULL DEFAULT 0, mesa TEXT NOT NULL, "
                    " wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, "
                    " last_bank REAL DEFAULT 0, "
                    " PRIMARY KEY (investment_id, mesa))"
                )
                # Migration: if old schema had mesa as sole PK, rebuild with investment_id
                try:
                    cols = [r[1] for r in conn.execute(
                        "PRAGMA table_info(table_stats)").fetchall()]
                    if 'investment_id' not in cols:
                        conn.execute(
                            "ALTER TABLE table_stats RENAME TO table_stats_old")
                        conn.execute(
                            "CREATE TABLE table_stats "
                            "(investment_id INTEGER NOT NULL DEFAULT 0, mesa TEXT NOT NULL, "
                            " wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, "
                            " last_bank REAL DEFAULT 0, "
                            " PRIMARY KEY (investment_id, mesa))")
                        conn.execute(
                            "INSERT INTO table_stats "
                            "(investment_id, mesa, wins, losses, last_bank) "
                            "SELECT 0, mesa, wins, losses, last_bank FROM table_stats_old")
                        conn.execute("DROP TABLE table_stats_old")
                        conn.commit()
                except Exception:
                    pass
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS investments "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    " name TEXT, capital REAL, created_at TEXT)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS investment_tables "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    " investment_id INTEGER, mesa_name TEXT, init_bank REAL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS compound_sessions "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    " investment_id INTEGER NOT NULL DEFAULT 0, "
                    " session_num INTEGER NOT NULL, "
                    " date TEXT NOT NULL, "
                    " mesa TEXT NOT NULL, "
                    " bank_start REAL NOT NULL, "
                    " bank_end REAL NOT NULL, "
                    " profit REAL NOT NULL, "
                    " profit_pct REAL NOT NULL)"
                )
                conn.commit()
                try:
                    conn.execute("ALTER TABLE sesiones ADD COLUMN banca_inicial REAL")
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE investments ADD COLUMN inv_type TEXT DEFAULT 'FIAT'")
                    conn.commit()
                except Exception:
                    pass
                for _col in [
                    "ALTER TABLE investment_tables ADD COLUMN token_symbol TEXT DEFAULT ''",
                    "ALTER TABLE investment_tables ADD COLUMN token_balance REAL DEFAULT 0",
                    "ALTER TABLE investment_tables ADD COLUMN token_price REAL DEFAULT 0",
                    "ALTER TABLE investment_tables ADD COLUMN chips_per_token REAL DEFAULT 0",
                    # Per-table base chip, remembered from the last setup on that table
                    "ALTER TABLE table_stats ADD COLUMN base_chip REAL DEFAULT 0",
                ]:
                    try:
                        conn.execute(_col)
                        conn.commit()
                    except Exception:
                        pass
                # One-time migration: CHIPS investments now store capital in
                # CHIPS (= sum of table banks) instead of USD, so max-loss math
                # stays in a single unit. Guarded by user_version so it runs once.
                try:
                    ver = conn.execute("PRAGMA user_version").fetchone()[0]
                    if ver < 1:
                        conn.execute(
                            "UPDATE investments SET capital = COALESCE("
                            " (SELECT SUM(init_bank) FROM investment_tables "
                            "  WHERE investment_id = investments.id), capital) "
                            "WHERE inv_type = 'CHIPS'"
                        )
                        conn.execute("PRAGMA user_version = 1")
                        conn.commit()
                except Exception:
                    pass
                conn.close()
                self.db_path = db_path
                break
            except Exception as ex:
                self.db_error = str(ex)
                continue
        if not self.db_path:
            self.db_error = f"All paths failed. Last: {self.db_error}"
        # Load any user-applied RVS tuning + entry-policy (from the Bet Eval
        # page). Never auto-set — only what the player previously approved.
        self.entry_policy = None
        try:
            self._load_rvs_config()
            self.entry_policy = self._load_entry_policy()
        except Exception:
            pass

    def _get_conn(self):
        if not self.db_path:
            return None
        try:
            return sqlite3.connect(self.db_path)
        except Exception:
            return None

    def _guardar_sesion(self):
        """Save or update session. Returns (True, None) or (False, error_msg)."""
        try:
            if not self.db_path:
                init_err = getattr(self, "db_error", "unknown")
                raise Exception(f"DB unavailable. Error: {init_err}")
            conn = sqlite3.connect(self.db_path)
            try:
                profit = round(float(self.banca_actual - self.banca_inicial), 2)
                fecha  = datetime.now().strftime("%d/%m %H:%M")
                if self.session_id is not None:
                    conn.execute(
                        "UPDATE sesiones SET profit=?, banca_final=?, fecha=? WHERE id=?",
                        (profit, round(float(self.banca_actual), 2), fecha, self.session_id)
                    )
                else:
                    cursor = conn.execute(
                        "INSERT INTO sesiones (mesa, fecha, profit, banca_inicial, banca_final) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (str(self.nombre_mesa), fecha, profit,
                         round(float(self.banca_inicial), 2),
                         round(float(self.banca_actual), 2))
                    )
                    self.session_id = cursor.lastrowid
                conn.commit()
                return True, None
            finally:
                conn.close()
        except Exception as ex:
            return False, str(ex)

    def _save_compound_session(self):
        """Persist this session to compound_sessions (DB + CSV)."""
        import csv
        inv_id = self.current_investment_id or 0
        conn   = self._get_conn()
        if not conn:
            return
        try:
            cursor  = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM compound_sessions WHERE investment_id=?",
                (inv_id,)
            )
            session_num = (cursor.fetchone()[0] or 0) + 1
            date_str    = datetime.now().strftime('%y.%m.%d')
            profit      = round(self.banca_actual - self.banca_inicial, 2)
            profit_pct  = round((profit / self.banca_inicial * 100) if self.banca_inicial else 0.0, 2)
            bank_start  = round(self.banca_inicial, 2)
            bank_end    = round(self.banca_actual, 2)
            mesa        = str(self.nombre_mesa)

            conn.execute(
                "INSERT INTO compound_sessions "
                "(investment_id, session_num, date, mesa, bank_start, bank_end, profit, profit_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (inv_id, session_num, date_str, mesa,
                 bank_start, bank_end, profit, profit_pct)
            )
            conn.commit()

            # Mirror to CSV next to the DB for easy spreadsheet access
            csv_path  = self.db_path.replace('.db', '_compound.csv')
            write_hdr = not os.path.exists(csv_path)
            with open(csv_path, 'a', newline='') as f:
                w = csv.writer(f)
                if write_hdr:
                    w.writerow(['investment_id', 'session_num', 'date', 'mesa',
                                'bank_start', 'bank_end', 'profit', 'profit_pct'])
                w.writerow([inv_id, session_num, date_str, mesa,
                            bank_start, bank_end, profit, profit_pct])
        except Exception:
            pass
        finally:
            conn.close()

    def _update_table_stats(self, is_win: bool):
        """Increment win or loss counter and update last_bank for this table.
        A break-even session (0% P/L) is not counted as W or L."""
        profit = round(self.banca_actual - self.banca_inicial, 2)
        conn = self._get_conn()
        if not conn:
            return
        try:
            w    = 0 if profit == 0 else (1 if is_win else 0)
            l    = 0 if profit == 0 else (0 if is_win else 1)
            bk   = round(float(self.banca_actual), 2)
            inv  = self.current_investment_id or 0
            conn.execute(
                "INSERT INTO table_stats (investment_id, mesa, wins, losses, last_bank) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(investment_id, mesa) DO UPDATE SET "
                "wins=wins+?, losses=losses+?, last_bank=?",
                (inv, self.nombre_mesa, w, l, bk, w, l, bk)
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _load_base_chip(self, investment_id, mesa, default=0.1):
        """Return the base chip last saved for this (investment, table), or default."""
        conn = self._get_conn()
        if not conn:
            return default
        try:
            row = conn.execute(
                "SELECT base_chip FROM table_stats WHERE investment_id=? AND mesa=?",
                (investment_id or 0, str(mesa))
            ).fetchone()
            if row and row[0] and float(row[0]) > 0:
                return float(row[0])
        except Exception:
            pass
        finally:
            conn.close()
        return default

    def _save_base_chip(self, investment_id, mesa, base_chip):
        """Persist the base chip for this (investment, table) so it's remembered."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            conn.execute(
                "INSERT INTO table_stats (investment_id, mesa, base_chip) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(investment_id, mesa) DO UPDATE SET base_chip=?",
                (investment_id or 0, str(mesa), float(base_chip), float(base_chip))
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _recompute_table_stats(self, investment_id: int):
        """Rebuild table_stats wins/losses/last_bank entirely from compound_sessions."""
        conn = self._get_conn()
        if not conn:
            return
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT mesa, profit, bank_end FROM compound_sessions "
                "WHERE investment_id=? ORDER BY session_num, id",
                (investment_id,)
            )
            rows = cursor.fetchall()
            mesa_stats = {}
            for m, p, be in rows:
                if m not in mesa_stats:
                    mesa_stats[m] = {'wins': 0, 'losses': 0, 'last_bank': be}
                if p > 0:
                    mesa_stats[m]['wins'] += 1
                elif p < 0:
                    mesa_stats[m]['losses'] += 1
                mesa_stats[m]['last_bank'] = be
            for m, s in mesa_stats.items():
                conn.execute(
                    "INSERT INTO table_stats (investment_id, mesa, wins, losses, last_bank) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(investment_id, mesa) DO UPDATE SET "
                    "wins=excluded.wins, losses=excluded.losses, last_bank=excluded.last_bank",
                    (investment_id, m, s['wins'], s['losses'], s['last_bank'])
                )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────
    # STATE
    # ──────────────────────────────────────────────────────────────────
    def reset_variables(self):
        self.banca_inicial        = 100.0
        self.banca_actual         = 100.0
        self.idx_fibo_out         = 0
        self.nivel_martingala_out = 0
        self.idx_fibo_in          = 0
        self.nivel_martingala_in  = 0
        self.last_bet_outside     = None
        self.last_prog_state      = True   # was progression on when last bet resolved
        self.last_bank_delta      = 0.0
        self.stop_loss_triggered  = False
        self.goal_achieved_shown  = False
        self.activa               = False
        self.free_spin_mode       = False
        self.live_table_mode      = False
        self.live_filter          = None   # None, 'R', 'B'
        self.prog_on              = True   # progression on/off
        self.sniper_mode          = True   # sniper mode on/off (intersection of groups) - default ON
        self.sniper_safety_level  = 1      # 1-5 safety level when sniper is off
        self.fixed_multi          = 1      # 1-5 when progression is off
        self.grupos_activos       = []
        self.history_nums         = []
        self.sliding_window       = deque(maxlen=6)
        # New session/croupier → forget the previous reads.
        if getattr(self, 'rhythm_model', None):
            self.rhythm_model.reset()
        if getattr(self, 'pattern_model', None):
            self.pattern_model.reset()
        self.val_fin              = 0.10
        self.val_fout             = 0.30
        self.nombre_mesa          = "TABLE 1"
        self.session_id           = None
        self.play_session_id      = None   # unique per play session (bet log)
        self.inv_name             = ""
        self.inv_capital          = 0.0
        self.chip_usd_rate        = 0.0   # USD per chip (CHIPS investments)
        self.inv_other_pl         = 0.0
        self.inv_type             = 'FIAT'
        # Which column categories are shown in the registration table / mixer
        if not hasattr(self, 'visible_cats'):
            self.visible_cats = {
                'basic':  True,   # R N P I B A
                'cols':   True,   # 34 35 36
                'docs':   True,   # 1a 2a 3a
                'secs':   True,   # Z0 ZG ZP H
                'thirds': True,   # T1 T2 T3
                'wave':   True,   # W1 W2 W3
                'filters': True,  # R B 1-18 19-36
            }

    def _fmt_bank(self, val: float) -> str:
        if self.inv_type == 'CHIPS':
            rate = getattr(self, 'chip_usd_rate', 0.0)
            if rate > 0:
                return f"{int(round(val)):,} (${val * rate:,.2f})"
            return f"{int(round(val)):,}"
        return f"${val:.2f}"

    # ──────────────────────────────────────────────────────────────────
    # CRYPTO PRICE FETCH  (CoinGecko free API, no key required)
    # ──────────────────────────────────────────────────────────────────
    # symbol → (display label, coingecko_id or None for stablecoins)
    _TOKENS = [
        ('BTC',  'BTC – Bitcoin',   'bitcoin'),
        ('ETH',  'ETH – Ethereum',  'ethereum'),
        ('SOL',  'SOL – Solana',    'solana'),
        ('LTC',  'LTC – Litecoin',  'litecoin'),
        ('BNB',  'BNB – BNB Chain', 'binancecoin'),
        ('XRP',  'XRP – XRP',       'ripple'),
        ('ADA',  'ADA – Cardano',   'cardano'),
        ('DOGE', 'DOGE – Dogecoin', 'dogecoin'),
        ('USDT', 'USDT – Tether',   None),
        ('USDC', 'USDC – USD Coin', None),
    ]

    # Default chip conversion per token: how many tokens the base "Credits"
    # (10) are worth — i.e. the "= tokens" field default. The casino prices a
    # chip at ≈ $0.005 (10 credits ≈ $0.05), so each value is 0.05 / reference
    # price. SOL/BTC/ETH/LTC/USDT are exact casino rates; the rest are derived
    # on the same $0.005/chip basis and are editable in the setup form.
    _CHIP_TOKEN_DEFAULTS = {
        'BTC':  0.000001,
        'ETH':  0.00002,
        'SOL':  0.0004,
        'LTC':  0.001,
        'BNB':  0.00005,
        'XRP':  0.02,
        'ADA':  0.05,
        'DOGE': 0.25,
        'USDT': 0.05,
        'USDC': 0.05,
    }
    _DEFAULT_CHIP_TOKENS = 0.0004  # fallback ("= tokens" for 10 credits)

    async def _fetch_token_price(self, symbol: str) -> float:
        import urllib.request, json, ssl
        sym = symbol.upper()
        # Stablecoins — no network call needed
        token = next((t for t in self._TOKENS if t[0] == sym), None)
        if token and token[2] is None:
            return 1.0
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        loop = asyncio.get_running_loop()
        # Primary: Binance spot price (SYMBOLUSDT pair)
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={sym}USDT"
            def _binance():
                with urllib.request.urlopen(url, timeout=6, context=ctx) as r:
                    return json.loads(r.read())
            data = await loop.run_in_executor(None, _binance)
            return float(data['price'])
        except Exception:
            pass
        # Fallback: CoinGecko
        try:
            coin_id = token[2] if token else sym.lower()
            url = (f"https://api.coingecko.com/api/v3/simple/price"
                   f"?ids={coin_id}&vs_currencies=usd")
            def _coingecko():
                with urllib.request.urlopen(url, timeout=8, context=ctx) as r:
                    return json.loads(r.read())
            data = await loop.run_in_executor(None, _coingecko)
            return float(data[coin_id]['usd'])
        except Exception:
            return 0.0

    # ──────────────────────────────────────────────────────────────────
    # NAVIGATION
    # ──────────────────────────────────────────────────────────────────


    def _set_view(self, content: ft.Control):
        self.root.content = content
        self.page.update()

    def _go_home(self, e=None):
        """Return to investment dashboard if inside one, otherwise main menu."""
        if self.current_investment_id is not None:
            inv_id = self.current_investment_id
            self.show_investment_dashboard(inv_id)
        else:
            self.show_main_menu()

    # ──────────────────────────────────────────────────────────────────
    # SPLASH SCREEN
    # ──────────────────────────────────────────────────────────────────
    def show_splash(self):
        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True,
                content=ft.Column(
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Linup", color='#3498db', size=64,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(height=16),
                        ft.Image(src="roulette.gif", width=200, height=200),
                        ft.Container(height=16),
                        ft.Text("v19.1.3-AI", color='#9b59b6', size=18),
                        ft.Container(height=48),
                        ft.ProgressRing(color='#3498db', width=36, height=36,
                                        stroke_width=3),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # MAIN MENU
    # ──────────────────────────────────────────────────────────────────
    def show_main_menu(self, e=None):
        self._on_game_screen = False
        self.current_investment_id = None
        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.Column(
                    expand=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Text("Linup", color='#3498db', size=42,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(height=40),
                        ft.ElevatedButton(
                            "NEW INVESTMENT",
                            on_click=self.show_new_investment_form,
                            width=280, height=60,
                            style=ft.ButtonStyle(bgcolor='#27ae60',
                                                 color=ft.Colors.WHITE),
                        ),
                        ft.Container(height=12),
                        ft.ElevatedButton(
                            "LOAD INVESTMENT",
                            on_click=self.show_load_investments,
                            width=280, height=60,
                            style=ft.ButtonStyle(bgcolor='#2980b9',
                                                 color=ft.Colors.WHITE),
                        ),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # NEW INVESTMENT — Step 1: name + capital
    # ──────────────────────────────────────────────────────────────────
    def show_new_investment_form(self, e=None):
        inv_name_field = ft.TextField(
            label="Investment Name", value="",
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=50,
        )
        capital_field = ft.TextField(
            label="Capital ($)", value="",
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=50,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        inv_type = ['FIAT']

        fiat_btn = ft.ElevatedButton(
            "FIAT", expand=1, height=44,
            style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
        )
        chips_btn = ft.ElevatedButton(
            "CHIPS", expand=1, height=44,
            style=ft.ButtonStyle(bgcolor='#333333', color=ft.Colors.WHITE),
        )
        capital_label = ft.Text("Capital ($)", color='#7f8c8d', size=12)

        def set_type(t):
            inv_type[0] = t
            fiat_btn.style  = ft.ButtonStyle(bgcolor='#27ae60' if t == 'FIAT'  else '#333333', color=ft.Colors.WHITE)
            chips_btn.style = ft.ButtonStyle(bgcolor='#f39c12' if t == 'CHIPS' else '#333333', color=ft.Colors.WHITE)
            capital_label.value = "Capital ($)  ·  auto-calculated from tables" if t == 'CHIPS' else "Capital ($)"
            capital_field.visible = t == 'FIAT'
            fiat_btn.update(); chips_btn.update()
            capital_label.update(); capital_field.update()

        fiat_btn.on_click  = lambda _e: set_type('FIAT')
        chips_btn.on_click = lambda _e: set_type('CHIPS')

        def on_next(ev):
            try:
                inv_name = inv_name_field.value.strip().upper() or "INVESTMENT 1"
                capital  = float(capital_field.value or 0) if inv_type[0] == 'FIAT' else 0.0
            except Exception:
                return
            self._show_num_tables_form(inv_name, capital, inv_type[0])

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(
                    expand=True,
                    controls=[
                        ft.ElevatedButton(
                            "CANCEL", on_click=self.show_main_menu,
                            style=ft.ButtonStyle(bgcolor='#c0392b',
                                                 color=ft.Colors.WHITE),
                        ),
                        ft.Container(height=16),
                        ft.Text("NEW INVESTMENT", color='#3498db', size=20,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(height=12),
                        ft.Text("TYPE", color='#7f8c8d', size=12),
                        ft.Container(height=4),
                        ft.Row(controls=[fiat_btn, chips_btn], spacing=8),
                        ft.Container(height=12),
                        inv_name_field,
                        ft.Container(height=8),
                        capital_label,
                        capital_field,
                        ft.Container(height=20),
                        ft.ElevatedButton(
                            "NEXT  →", on_click=on_next,
                            height=60, expand=True,
                            style=ft.ButtonStyle(bgcolor='#2980b9',
                                                 color=ft.Colors.WHITE),
                        ),
                    ],
                ),
            )
        )

    # NEW INVESTMENT — Step 2: number of tables
    # ──────────────────────────────────────────────────────────────────
    def _show_num_tables_form(self, inv_name: str, capital: float, inv_type: str = 'FIAT'):
        num_tables_field = ft.TextField(
            label="Number of Tables", value="1",
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=50,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        def on_next(ev):
            try:
                num_tables = max(1, min(10, int(num_tables_field.value or 1)))
            except Exception:
                return
            self._show_table_setup(inv_name, capital, num_tables, inv_type)

        cap_txt = f"Capital: ${capital:,.2f}" if inv_type == 'FIAT' else f"Type: {inv_type}"

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(
                    expand=True,
                    controls=[
                        ft.ElevatedButton(
                            "←  BACK", on_click=self.show_new_investment_form,
                            style=ft.ButtonStyle(bgcolor='#c0392b',
                                                 color=ft.Colors.WHITE),
                        ),
                        ft.Container(height=16),
                        ft.Text(inv_name, color='#3498db', size=20,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(cap_txt, color='#7f8c8d', size=14),
                        ft.Container(height=12),
                        num_tables_field,
                        ft.Container(height=20),
                        ft.ElevatedButton(
                            "NEXT  →", on_click=on_next,
                            height=60, expand=True,
                            style=ft.ButtonStyle(bgcolor='#2980b9',
                                                 color=ft.Colors.WHITE),
                        ),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # NEW INVESTMENT — Step 2: table names and banks
    # ──────────────────────────────────────────────────────────────────
    def _show_table_setup(self, inv_name: str, capital: float, num_tables: int,
                          inv_type: str = 'FIAT'):
        # ── FIAT MODE ──────────────────────────────────────────────
        if inv_type == 'FIAT':
            bank_per_table = round(capital * 0.03, 2)
            capital_per_table = round(capital / num_tables, 2)
            
            name_fields, bank_fields = [], []
            rows = []
            
            for i in range(num_tables):
                nf = ft.TextField(
                    value=f"TABLE {i + 1}",
                    bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=40,
                    expand=2, text_size=14,
                )
                bf = ft.TextField(
                    value=str(bank_per_table),
                    bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=40,
                    keyboard_type=ft.KeyboardType.NUMBER, expand=1, text_size=14,
                )
                
                name_fields.append(nf)
                bank_fields.append(bf)
                
                rows.append(ft.Row(controls=[nf, bf], spacing=6))

            def on_create_fiat(_):
                tables_data = []
                for nf, bf in zip(name_fields, bank_fields):
                    t_name = nf.value.strip().upper() or f"TABLE {len(tables_data) + 1}"
                    try:
                        t_bank = float(bf.value or bank_per_table)
                    except Exception:
                        t_bank = bank_per_table
                    tables_data.append((t_name, t_bank))
                self._create_investment(inv_name, capital, tables_data, 'FIAT')

            controls = [
                ft.ElevatedButton(
                    "←  BACK", on_click=self.show_new_investment_form,
                    style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
                ),
                ft.Container(height=12),
                ft.Text(f"{inv_name}  |  Capital: ${capital:.2f}", color='#3498db',
                        size=16, weight=ft.FontWeight.BOLD),
                ft.Container(height=4),
                ft.Text("Table Names", color='#7f8c8d', size=12),
                ft.Row(controls=[
                    ft.Text("TABLE", color='#7f8c8d', size=11, expand=2),
                    ft.Text("BANK", color='#7f8c8d', size=11, expand=1),
                ]),
                ft.Container(height=8),
            ] + rows + [
                ft.Container(height=20),
                ft.ElevatedButton(
                    "CREATE INVESTMENT", on_click=on_create_fiat,
                    height=60, expand=True,
                    style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
                ),
            ]

        # ── CHIPS MODE ─────────────────────────────────────────────
        else:
            # Each entry: (name_f, bal_f, price_f, cc_f, ct_f, chip_lbl)
            chip_rows_refs = []
            rows = []

            dd_options = [
                ft.dropdown.Option(key=sym, text=lbl)
                for sym, lbl, _ in self._TOKENS
            ]

            _tf_dark = dict(bgcolor='#3a3a3a', color=ft.Colors.WHITE,
                            label_style=ft.TextStyle(color='#aaaaaa'))

            total_lbl = ft.Text("TOTAL CAPITAL:  0 chips  ($0.00)",
                                color='#f39c12', size=14, weight=ft.FontWeight.BOLD)

            def _chips_totals():
                """Return (total_chips, total_usd) across all table rows."""
                total_chips = total_usd = 0.0
                for (dd, bf, pf, ccf, ctf) in chip_rows_refs:
                    try:
                        bal   = float(bf.value  or 0)
                        price = float(pf.value  or 0)
                        cc    = float(ccf.value or 10)
                        ct    = float(ctf.value or self._DEFAULT_CHIP_TOKENS)
                        cpt   = cc / ct if ct > 0 else 0
                        total_chips += bal * cpt
                        total_usd   += bal * price
                    except Exception:
                        pass
                return total_chips, total_usd

            def _refresh_total(_=None):
                tc, tu = _chips_totals()
                total_lbl.value = f"TOTAL CAPITAL:  {tc:,.0f} chips  (${tu:,.2f})"
                try:
                    total_lbl.update()
                except Exception:
                    pass

            for i in range(num_tables):
                token_dd = ft.Dropdown(
                    options=dd_options,
                    value='SOL',
                    expand=True,
                    bgcolor='#3a3a3a',
                    color=ft.Colors.WHITE,
                    border_color='#555555',
                    focused_border_color='#f39c12',
                    text_style=ft.TextStyle(color=ft.Colors.WHITE, size=14),
                    hint_style=ft.TextStyle(color='#aaaaaa'),
                )
                bal_f = ft.TextField(
                    value="0", label="Token balance",
                    height=45, keyboard_type=ft.KeyboardType.NUMBER,
                    **_tf_dark,
                )
                price_f = ft.TextField(
                    value="0", label="Price (USD)  –  editable",
                    height=45, keyboard_type=ft.KeyboardType.NUMBER,
                    expand=True, **_tf_dark,
                )
                cc_f = ft.TextField(
                    value="10", label="Credits",
                    height=45, keyboard_type=ft.KeyboardType.NUMBER,
                    expand=1, **_tf_dark,
                )
                ct_f = ft.TextField(
                    value=str(self._CHIP_TOKEN_DEFAULTS.get('SOL', self._DEFAULT_CHIP_TOKENS)),
                    label="= tokens",
                    height=45, keyboard_type=ft.KeyboardType.NUMBER,
                    expand=1, **_tf_dark,
                )
                chip_lbl   = ft.Text("0 chips  |  $0.00", color='#f1c40f',
                                     size=13, weight=ft.FontWeight.BOLD)
                status_lbl = ft.Text("Select a token to fetch price",
                                     color='#7f8c8d', size=11)

                def _make_updater(bf, pf, ccf, ctf, clbl):
                    def update(_=None):
                        try:
                            bal   = float(bf.value  or 0)
                            price = float(pf.value  or 0)
                            cc    = float(ccf.value or 10)
                            ct    = float(ctf.value or self._DEFAULT_CHIP_TOKENS)
                            cpt   = cc / ct if ct > 0 else 0
                            chips = int(bal * cpt)
                            usd   = bal * price
                            clbl.value = f"{chips:,} chips  (${usd:,.2f})"
                        except Exception:
                            clbl.value = "—"
                        try:
                            clbl.update()
                        except Exception:
                            pass
                        _refresh_total()
                    return update

                upd = _make_updater(bal_f, price_f, cc_f, ct_f, chip_lbl)
                bal_f.on_change   = upd
                price_f.on_change = upd
                cc_f.on_change    = upd
                ct_f.on_change    = upd

                def _make_fetch_handler(dd, pf, ctf, slbl, upd_fn):
                    async def _do_fetch():
                        sym = dd.value or 'SOL'
                        # Snap the "= tokens" conversion to this token's default
                        ctf.value = str(self._CHIP_TOKEN_DEFAULTS.get(
                            sym, self._DEFAULT_CHIP_TOKENS))
                        ctf.update()
                        slbl.value = f"Fetching {sym}…"
                        self.page.update()
                        price = await self._fetch_token_price(sym)
                        if price > 0:
                            pf.value   = str(price)
                            slbl.value = f"✓  {sym}  =  ${price:,.4f}"
                        else:
                            slbl.value = "Could not fetch — enter price manually"
                        self.page.update()
                        upd_fn()

                    def trigger(_):
                        self.page.run_task(_do_fetch)

                    return trigger

                fetch_handler = _make_fetch_handler(token_dd, price_f, ct_f, status_lbl, upd)
                token_dd.on_change = fetch_handler

                fetch_btn = ft.ElevatedButton(
                    "GET PRICE", on_click=fetch_handler,
                    height=45, width=110,
                    style=ft.ButtonStyle(bgcolor='#2980b9', color=ft.Colors.WHITE),
                )

                chip_rows_refs.append((token_dd, bal_f, price_f, cc_f, ct_f))
                rows.append(ft.Container(
                    bgcolor='#222222', border_radius=8, padding=10,
                    margin=ft.margin.only(bottom=8),
                    content=ft.Column(spacing=6, controls=[
                        ft.Text(f"TABLE {i + 1}", color='#7f8c8d', size=11),
                        token_dd,
                        status_lbl,
                        bal_f,
                        ft.Row(controls=[price_f, fetch_btn], spacing=6),
                        ft.Text("Conversion  (credits = tokens)",
                                color='#7f8c8d', size=11),
                        ft.Row(controls=[cc_f, ct_f], spacing=6),
                        chip_lbl,
                    ]),
                ))

            def on_create_chips(_):
                tables_data = []
                total_chips = total_usd = 0.0
                for idx, (dd, bf, pf, ccf, ctf) in enumerate(chip_rows_refs):
                    t_name = dd.value or f"TABLE {idx + 1}"
                    try:
                        bal   = float(bf.value  or 0)
                        price = float(pf.value  or 0)
                        cc    = float(ccf.value or 10)
                        ct    = float(ctf.value or self._DEFAULT_CHIP_TOKENS)
                        cpt   = cc / ct if ct > 0 else 0
                        chips = round(bal * cpt, 2)
                    except Exception:
                        bal = price = cpt = chips = 0.0
                    tables_data.append((t_name, chips, t_name, bal, price, cpt))
                    total_chips += chips
                    total_usd   += bal * price
                # Capital is stored in CHIPS so it matches the per-table banks
                # (max-loss math stays in one unit); USD stays derivable from
                # the per-table token data saved alongside.
                self._create_investment(inv_name, total_chips, tables_data, 'CHIPS')

            controls = [
                ft.ElevatedButton(
                    "←  BACK", on_click=self.show_new_investment_form,
                    style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
                ),
                ft.Container(height=12),
                ft.Text(f"{inv_name}  ·  CHIPS", color='#f39c12',
                        size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Enter token balance + conversion for each table.",
                        color='#7f8c8d', size=12),
                ft.Container(height=8),
            ] + rows + [
                ft.Container(
                    bgcolor='#222222', border_radius=8,
                    padding=12, margin=ft.margin.only(top=4, bottom=4),
                    content=total_lbl,
                ),
                ft.Container(height=8),
                ft.ElevatedButton(
                    "CREATE INVESTMENT", on_click=on_create_chips,
                    height=60, expand=True,
                    style=ft.ButtonStyle(bgcolor='#f39c12', color=ft.Colors.WHITE),
                ),
            ]

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(expand=True, controls=controls),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # SAVE INVESTMENT TO DB
    # ──────────────────────────────────────────────────────────────────
    def _create_investment(self, inv_name: str, capital: float, tables_data: list,
                           inv_type: str = 'FIAT'):
        conn = self._get_conn()
        inv_id = None
        if conn:
            try:
                fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
                cursor = conn.execute(
                    "INSERT INTO investments (name, capital, created_at, inv_type) "
                    "VALUES (?, ?, ?, ?)",
                    (inv_name, round(capital, 2), fecha, inv_type)
                )
                inv_id = cursor.lastrowid
                if inv_type == 'CHIPS':
                    for (mesa_name, chip_bal, token_sym,
                         token_bal, token_price, chips_per_tok) in tables_data:
                        conn.execute(
                            "INSERT INTO investment_tables "
                            "(investment_id, mesa_name, init_bank, "
                            " token_symbol, token_balance, token_price, chips_per_token) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (inv_id, mesa_name, round(chip_bal, 2),
                             token_sym, token_bal, token_price,
                             round(chips_per_tok, 6))
                        )
                else:
                    for mesa_name, init_bank in tables_data:
                        conn.execute(
                            "INSERT INTO investment_tables "
                            "(investment_id, mesa_name, init_bank) VALUES (?, ?, ?)",
                            (inv_id, mesa_name, round(init_bank, 2))
                        )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()
        if inv_id:
            self.show_investment_dashboard(inv_id)
        else:
            self.show_main_menu()

    # ──────────────────────────────────────────────────────────────────
    # INVESTMENT DASHBOARD
    # ──────────────────────────────────────────────────────────────────
    def show_investment_dashboard(self, investment_id):
        self._on_game_screen = False
        self.current_investment_id = investment_id
        inv_name    = "Investment"
        inv_capital = 0.0
        header_cap_txt = "$0.00"
        table_rows  = []
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, capital, inv_type FROM investments WHERE id=?",
                    (investment_id,)
                )
                row = cursor.fetchone()
                db_inv_type = 'FIAT'
                if row:
                    inv_name, inv_capital, db_inv_type = row[0], row[1], (row[2] or 'FIAT')

                cursor.execute(
                    "SELECT mesa_name, init_bank, token_price, chips_per_token "
                    "FROM investment_tables "
                    "WHERE investment_id=? ORDER BY id",
                    (investment_id,)
                )
                inv_tables = cursor.fetchall()

                # usd_per_chip for each mesa (used for CHIPS display)
                mesa_chip_rate = {
                    row[0]: ((row[2] / row[3]) if row[3] and row[3] > 0 else 0.0)
                    for row in inv_tables
                }

                # Collect all table data first so we can compute per-table other_pl
                all_tdata = []  # (mesa_name, init_bank, wins, losses, last_bank)
                for mesa_name, init_bank, _tp, _cpt in inv_tables:
                    cursor.execute(
                        "SELECT wins, losses, last_bank FROM table_stats "
                        "WHERE investment_id=? AND mesa=?",
                        (investment_id, mesa_name)
                    )
                    stats = cursor.fetchone()
                    if stats and (stats[0] or stats[1]):
                        w = stats[0] or 0
                        l = stats[1] or 0
                        bk = stats[2] or float(init_bank)
                    else:
                        w, l, bk = 0, 0, float(init_bank)
                    all_tdata.append((mesa_name, float(init_bank), w, l, bk))

                total_wins   = sum(d[2] for d in all_tdata)
                total_losses = sum(d[3] for d in all_tdata)

                # Sum profits per mesa from compound_sessions (source of truth after editing)
                cursor.execute(
                    "SELECT mesa, SUM(profit) FROM compound_sessions "
                    "WHERE investment_id=? GROUP BY mesa",
                    (investment_id,)
                )
                mesa_pl = {row[0]: (row[1] or 0.0) for row in cursor.fetchall()}

                for i, (mesa_name, init_bank, wins, losses, last_bank) in enumerate(all_tdata):
                    # P/L from all OTHER tables (used in game screen bar)
                    if mesa_pl:
                        other_pl = sum(v for k, v in mesa_pl.items() if k != mesa_name)
                    else:
                        other_pl = sum((d[4] - d[1]) for j, d in enumerate(all_tdata) if j != i)

                    total = wins + losses
                    eff   = (wins / total * 100) if total > 0 else 0.0
                    color = '#2ecc71' if (total == 0 or eff >= 50) else '#ff4444'
                    if db_inv_type == 'CHIPS':
                        usd_val = last_bank * mesa_chip_rate.get(mesa_name, 0.0)
                        bk_fmt = f"{int(round(last_bank)):,} (${usd_val:.2f})"
                    else:
                        bk_fmt = f"${last_bank:.2f}"
                    if total == 0:
                        txt = f"{mesa_name}  |  {bk_fmt}  |  New"
                    else:
                        txt = (f"{mesa_name}  |  {bk_fmt}"
                               f"  |  W:{wins} L:{losses}  |  {eff:.0f}%")

                    def make_loader(m, bk, has_hist, opl, itype=db_inv_type,
                                    rate=mesa_chip_rate.get(mesa_name, 0.0)):
                        def loader(ev):
                            self.reset_variables()
                            self.current_investment_id = investment_id
                            self.inv_name      = inv_name
                            self.inv_capital   = float(inv_capital)
                            self.chip_usd_rate = float(rate)  # USD per chip (CHIPS only)
                            self.inv_other_pl  = opl
                            self.inv_type      = itype
                            self.nombre_mesa   = str(m)
                            self.banca_inicial = float(bk)
                            self.banca_actual  = float(bk)
                            self.render_setup_form(has_hist)
                        return loader

                    table_rows.append(
                        ft.ElevatedButton(
                            txt,
                            on_click=make_loader(mesa_name, last_bank, total > 0, other_pl),
                            width=340, height=60,
                            style=ft.ButtonStyle(bgcolor='#222222', color=color),
                        )
                    )

                # Use sum of actual session profits when available; fall back to last_bank - init_bank
                if mesa_pl:
                    total_pl = sum(mesa_pl.values())
                else:
                    total_pl = sum(d[4] - d[1] for d in all_tdata)
                total_bank = sum(d[4] for d in all_tdata)
                if table_rows:
                    # Efficiency = avg per-table W/L ratio across tables that have played
                    played = [(d[2], d[3]) for d in all_tdata if d[2] + d[3] > 0]
                    te     = (sum(w / (w + l) * 100 for w, l in played) / len(played)) if played else 0.0
                    tc     = '#2ecc71' if total_pl >= 0 else '#ff4444'
                    pl_sign  = "+" if total_pl >= 0 else ""
                    pl_pct   = (total_pl / float(inv_capital) * 100) if inv_capital else 0.0
                    eff_txt  = f"EFF: {te:.0f}%  W:{total_wins} L:{total_losses}\n" if played else ""
                    table_rows.insert(0, ft.Container(
                        bgcolor='#1e2d1e' if total_pl >= 0 else '#2d1e1e',
                        padding=10, margin=ft.margin.only(bottom=4),
                        content=ft.Text(
                            f"{eff_txt}"
                            + (f"{int(round(total_bank)):,}  |  P/L: {pl_sign}{int(round(total_pl)):,} ({pl_sign}{pl_pct:.1f}%)"
                               if db_inv_type == 'CHIPS'
                               else f"${total_bank:.2f}  |  P/L: {pl_sign}${total_pl:.2f} ({pl_sign}{pl_pct:.1f}%)"),
                            color=tc, size=13, weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ))

                # ── Actual saved sessions (primary view) ───────────────
                num_sessions = total_wins + total_losses

                # For CHIPS: initial USD capital + USD P/L from mesa rates
                total_usd_cap = sum(
                    d[1] * mesa_chip_rate.get(d[0], 0.0) for d in all_tdata
                ) if db_inv_type == 'CHIPS' else float(inv_capital)
                total_usd_pl = sum(
                    (d[4] - d[1]) * mesa_chip_rate.get(d[0], 0.0) for d in all_tdata
                ) if db_inv_type == 'CHIPS' else total_pl

                # Capital shown in CHIPS with USD in parenthesis (FIAT stays $)
                if db_inv_type == 'CHIPS':
                    header_cap_txt = (f"{int(round(inv_capital)):,} chips  "
                                      f"(${total_usd_cap:,.2f})")
                else:
                    header_cap_txt = f"${inv_capital:.2f}"

                proj_capital = total_usd_cap if db_inv_type == 'CHIPS' else float(inv_capital)
                per_session_rate = (
                    (total_usd_pl / proj_capital / num_sessions)
                    if (num_sessions > 0 and proj_capital > 0) else 0.0
                )

                # mesa_usd_rate reuses mesa_chip_rate (same data, already fetched)
                mesa_usd_rate = mesa_chip_rate

                cursor.execute(
                    "SELECT session_num, date, mesa, profit, profit_pct "
                    "FROM compound_sessions WHERE investment_id=? ORDER BY id",
                    (investment_id,)
                )
                saved_sessions = cursor.fetchall()

                session_rows = [
                    ft.Text("ACTUAL SESSIONS", color='#3498db', size=11,
                            weight=ft.FontWeight.BOLD,
                            text_align=ft.TextAlign.CENTER),
                ]
                if saved_sessions:
                    # CHIPS: running total in USD; FIAT: running total in dollars
                    running = total_usd_cap if db_inv_type == 'CHIPS' else float(inv_capital)
                    for s_num, s_date, s_mesa, s_profit, s_pct in saved_sessions:
                        if db_inv_type == 'CHIPS':
                            disp = s_profit * mesa_usd_rate.get(s_mesa, 0.0)
                        else:
                            disp = s_profit
                        running += disp
                        sign = "+" if disp >= 0 else ""
                        col  = '#2ecc71' if disp >= 0 else '#ff4444'
                        chip_pfx = (f"{'+' if s_profit >= 0 else ''}"
                                    f"{int(round(s_profit)):,}  "
                                    if db_inv_type == 'CHIPS' else "")
                        session_rows.append(
                            ft.Container(
                                bgcolor='#1a1a2e', border_radius=4,
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                margin=ft.margin.only(bottom=2),
                                content=ft.Row(controls=[
                                    ft.Text(f"#{s_num}  {s_date}", color='#aaaaaa',
                                            size=10, width=90),
                                    ft.Text(s_mesa, color=ft.Colors.WHITE,
                                            size=10, expand=True),
                                    ft.Text(f"{chip_pfx}{sign}${disp:.2f} ({sign}{s_pct:.1f}%)",
                                            color=col, size=10,
                                            weight=ft.FontWeight.BOLD),
                                ], spacing=6),
                            )
                        )
                    run_base = total_usd_cap if db_inv_type == 'CHIPS' else float(inv_capital)
                    run_col  = '#2ecc71' if running >= run_base else '#ff4444'
                    run_diff = running - run_base
                    run_sign = "+" if run_diff >= 0 else ""
                    session_rows.append(
                        ft.Container(
                            bgcolor='#0d1a0d', border_radius=4,
                            padding=ft.padding.symmetric(horizontal=8, vertical=5),
                            margin=ft.margin.only(top=4),
                            content=ft.Text(
                                f"Running total: ${running:.2f}  ({run_sign}${run_diff:.2f})",
                                color=run_col, size=11, weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        )
                    )
                else:
                    session_rows.append(
                        ft.Text("No sessions saved yet — press SAVE after a session.",
                                color='#7f8c8d', size=11,
                                text_align=ft.TextAlign.CENTER)
                    )

                table_rows.append(ft.Container(
                    bgcolor='#111111', border_radius=6,
                    padding=8, margin=ft.margin.only(top=10),
                    height=300,
                    content=ft.Column(controls=session_rows, spacing=2, scroll=ft.ScrollMode.AUTO),
                ))

                # ── Bottom action buttons ───────────────────────────────
                def _open_projection(_ev, r=per_session_rate, c=proj_capital,
                                     n=inv_name, iid=investment_id, e=te, it='FIAT'):
                    self.show_compound_custom_view(iid, n, c, r, e, it)

                def _open_graph(_, c=float(inv_capital),
                                n=inv_name, iid=investment_id, it=db_inv_type,
                                mur=dict(mesa_usd_rate), uc=total_usd_cap):
                    self.show_actual_graph_view(iid, n, c, it, mur, uc)

                def _edit_sessions(_, n=inv_name, c=float(inv_capital),
                                   iid=investment_id, it=db_inv_type):
                    self.show_edit_sessions(iid, n, c, it)

                def _open_bet_eval(_, iid=investment_id):
                    self.show_bet_eval_view(iid)

                table_rows.append(ft.Container(height=6))
                table_rows.append(
                    ft.Row(
                        controls=[
                            ft.ElevatedButton(
                                "COMPOUND GROWTH",
                                on_click=_open_projection,
                                expand=True, height=45,
                                style=ft.ButtonStyle(bgcolor='#2980b9',
                                                     color=ft.Colors.WHITE),
                            ),
                            ft.ElevatedButton(
                                "ACTUAL GRAPH",
                                on_click=_open_graph,
                                expand=True, height=45,
                                style=ft.ButtonStyle(bgcolor='#6c3483',
                                                     color=ft.Colors.WHITE),
                            ),
                            ft.ElevatedButton(
                                "EDIT SESSIONS",
                                on_click=_edit_sessions,
                                expand=True, height=45,
                                style=ft.ButtonStyle(bgcolor='#d35400',
                                                     color=ft.Colors.WHITE),
                            ),
                        ],
                        spacing=8,
                    )
                )
                table_rows.append(
                    ft.Row(
                        controls=[
                            ft.ElevatedButton(
                                "AI BET EVAL",
                                on_click=_open_bet_eval,
                                expand=True, height=45,
                                style=ft.ButtonStyle(bgcolor='#16a085',
                                                     color=ft.Colors.WHITE),
                            ),
                        ],
                        spacing=8,
                    )
                )

            except Exception as ex:
                table_rows.append(ft.Text(f"Error: {ex}", color='#ff4444'))
            finally:
                conn.close()

        if not table_rows:
            table_rows.append(ft.Text("No tables found.", color='#7f8c8d'))

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Container(
                            bgcolor='#2c3e50',
                            padding=ft.padding.only(left=8, right=8, top=36, bottom=8),
                            content=ft.Row(
                                controls=[
                                    ft.ElevatedButton(
                                        "MENU",
                                        on_click=self.show_main_menu,
                                        style=ft.ButtonStyle(bgcolor='#34495e',
                                                             color=ft.Colors.WHITE),
                                    ),
                                    ft.Text(
                                        f"{inv_name}  |  {header_cap_txt}",
                                        color=ft.Colors.WHITE, size=13,
                                        weight=ft.FontWeight.BOLD, expand=True,
                                        text_align=ft.TextAlign.RIGHT,
                                    ),
                                ],
                            ),
                        ),
                        ft.ListView(controls=table_rows, expand=True,
                                    spacing=4, padding=10),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # COMPOUND INTEREST WIDGET
    # ──────────────────────────────────────────────────────────────────
    def _build_compound_widget(self, periods: int, start_capital: float,
                               rate: float, efficiency: float = 0.0,
                               inv_type: str = 'FIAT'):
        # efficiency: 0–100 (e.g. 70 → 70 % win rate)
        eff      = max(0.0, min(100.0, efficiency)) / 100.0
        denom    = 2 * eff - 1
        # Derive symmetric win/loss rate so that the weighted average == rate
        r        = (rate / denom) if abs(denom) > 0.01 else abs(rate)
        r        = abs(r)

        # Random W/L sequence matching the efficiency ratio
        wins_n   = round(periods * eff)
        losses_n = periods - wins_n
        wl_seq   = ['W'] * wins_n + ['L'] * losses_n
        random.shuffle(wl_seq)

        rate_txt = f"{rate * 100:+.2f}% / session  ·  EFF {efficiency:.0f}%"

        def _cell(text, color, expand, bold=False, size=13):
            return ft.Container(
                expand=expand,
                content=ft.Text(
                    text, color=color, size=size,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.BOLD if bold else ft.FontWeight.NORMAL,
                ),
            )

        def _red_cell(text, expand):
            return ft.Container(
                expand=expand,
                bgcolor='#3d0000', border_radius=4,
                padding=ft.padding.symmetric(vertical=1),
                content=ft.Text(
                    text, color='#ff4444', size=13,
                    text_align=ft.TextAlign.CENTER,
                    weight=ft.FontWeight.BOLD,
                ),
            )

        def _badge(label, win):
            return ft.Container(
                expand=1,
                bgcolor='#1a3d1a' if win else '#3d0000',
                border_radius=4,
                padding=ft.padding.symmetric(vertical=1),
                content=ft.Text(
                    label,
                    color='#2ecc71' if win else '#ff4444',
                    size=12, weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
            )

        header = ft.Row([
            _cell("DAY",  '#7f8c8d', 1, bold=True),
            _cell("RES",  '#7f8c8d', 1, bold=True),
            _cell("CAPITAL", '#7f8c8d', 2, bold=True),
            _cell("GAIN",    '#7f8c8d', 2, bold=True),
            _cell("TOT%",    '#7f8c8d', 1, bold=True),
        ], spacing=3)

        def _fv(v):  # format capital/gain value
            if inv_type == 'CHIPS':
                return f"{int(round(v)):,}"
            return f"${v:.2f}"

        # Day 0 — starting capital
        data_rows = [ft.Row([
            _cell("0",                  '#7f8c8d', 1),
            _cell("—",                  '#7f8c8d', 1),
            _cell(_fv(start_capital),   ft.Colors.WHITE, 2),
            _cell("—",                  '#7f8c8d', 2),
            _cell("0.0%",               '#7f8c8d', 1),
        ], spacing=3)]

        cap = start_capital
        for i, result in enumerate(wl_seq, start=1):
            win     = (result == 'W')
            new_cap = cap * (1 + r) if win else cap * (1 - r)
            gain    = new_cap - cap
            total_gain = new_cap - start_capital
            total_pct  = (total_gain / start_capital * 100) if start_capital > 0 else 0.0
            cap     = new_cap

            gain_txt = f"{'+' if gain >= 0 else ''}{_fv(gain)}"
            pct_txt  = f"{'+' if total_pct >= 0 else ''}{total_pct:.1f}%"

            gain_cell = _cell(gain_txt, '#2ecc71', 2) if win else _red_cell(gain_txt, 2)
            pct_cell  = _cell(pct_txt,  '#2ecc71', 1) if win else _red_cell(pct_txt,  1)

            data_rows.append(ft.Row([
                _cell(str(i),       ft.Colors.WHITE, 1),
                _badge(result, win),
                _cell(_fv(new_cap), ft.Colors.WHITE, 2),
                gain_cell,
                pct_cell,
            ], spacing=3))

        return ft.Container(
            bgcolor='#1a2535', padding=10, border_radius=8,
            content=ft.Column(
                [
                    ft.Text(
                        "COMPOUND GROWTH",
                        color='#3498db', size=14, weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        rate_txt,
                        color='#5dade2', size=12,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=4),
                    header,
                    ft.Divider(color='#333333', height=1),
                ] + data_rows,
                spacing=4, tight=True,
            ),
        )

    # ──────────────────────────────────────────────────────────────────
    # COMPOUND INTEREST — CUSTOM PERIOD VIEW
    # ──────────────────────────────────────────────────────────────────
    def show_compound_custom_view(self, investment_id, inv_name: str,
                                  inv_capital: float, rate: float, efficiency: float = 0.0,
                                  inv_type: str = 'FIAT'):
        periods_field = ft.TextField(
            value="30",
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            expand=True,
        )
        result_col = ft.Column([], tight=True)

        def generate(ev=None):
            try:
                p = max(1, min(730, int(periods_field.value or 30)))
            except Exception:
                p = 30
            result_col.controls = [self._build_compound_widget(p, inv_capital, rate, efficiency, inv_type)]
            result_col.update()

        def go_back(ev):
            self.show_investment_dashboard(investment_id)

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(
                    expand=True,
                    controls=[
                        ft.ElevatedButton(
                            "←  BACK", on_click=go_back,
                            style=ft.ButtonStyle(bgcolor='#c0392b',
                                                 color=ft.Colors.WHITE),
                        ),
                        ft.Container(height=12),
                        ft.Text(
                            f"{inv_name}  —  CUSTOM COMPOUND PERIOD",
                            color='#3498db', size=14, weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"Base: {int(round(inv_capital)):,}  |  Rate: {rate * 100:+.2f}% / session"
                            if inv_type == 'CHIPS' else
                            f"Base: ${inv_capital:.2f}  |  Rate: {rate * 100:+.2f}% / session",
                            color='#7f8c8d', size=12,
                        ),
                        ft.Container(height=10),
                        ft.Row([
                            ft.Text("PERIODS:", color=ft.Colors.WHITE),
                            periods_field,
                            ft.ElevatedButton(
                                "GENERATE", on_click=generate,
                                style=ft.ButtonStyle(bgcolor='#27ae60',
                                                     color=ft.Colors.WHITE),
                            ),
                        ], spacing=8),
                        ft.Container(height=10),
                        result_col,
                    ],
                ),
            )
        )
        generate()   # auto-generate on open

    # ──────────────────────────────────────────────────────────────────
    # EDIT ACTUAL SESSIONS
    # ──────────────────────────────────────────────────────────────────
    def show_edit_sessions(self, investment_id: int, inv_name: str, inv_capital: float,
                           inv_type: str = 'FIAT'):
        """Display and edit all compound sessions for an investment."""
        sessions = []
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, session_num, date, mesa, bank_start, bank_end, profit, profit_pct "
                    "FROM compound_sessions WHERE investment_id=? ORDER BY session_num, id",
                    (investment_id,)
                )
                sessions = cursor.fetchall()
            except Exception:
                pass
            finally:
                conn.close()

        # Each entry: dict with sid (None = new), field widgets
        session_fields = []
        sessions_col = ft.Column(spacing=2)

        def _build_row(entry):
            def on_up(e, en=entry):
                i = session_fields.index(en)
                if i > 0:
                    session_fields[i], session_fields[i - 1] = session_fields[i - 1], session_fields[i]
                    _rebuild_col()

            def on_down(e, en=entry):
                i = session_fields.index(en)
                if i < len(session_fields) - 1:
                    session_fields[i], session_fields[i + 1] = session_fields[i + 1], session_fields[i]
                    _rebuild_col()

            def on_delete(e, en=entry):
                if en['sid'] is None:
                    session_fields.remove(en)
                    _rebuild_col()
                    return
                dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
                def confirm(ev2, en=en):
                    conn2 = self._get_conn()
                    if conn2:
                        try:
                            conn2.execute("DELETE FROM compound_sessions WHERE id=?", (en['sid'],))
                            conn2.commit()
                        except Exception:
                            pass
                        finally:
                            conn2.close()
                    session_fields.remove(en)
                    dlg.open = False
                    dlg.update()
                    _rebuild_col()
                def cancel(ev2):
                    dlg.open = False
                    dlg.update()
                dlg.title = ft.Text("DELETE SESSION", color='#ff4444', size=14, weight=ft.FontWeight.BOLD)
                dlg.content = ft.Text(
                    f"Delete session ({entry['date_field'].value})?\nThis cannot be undone.",
                    color=ft.Colors.WHITE, size=12,
                )
                dlg.actions = [
                    ft.ElevatedButton("CANCEL", on_click=cancel, expand=1,
                        style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE)),
                    ft.ElevatedButton("DELETE", on_click=confirm, expand=1,
                        style=ft.ButtonStyle(bgcolor='#ff4444', color=ft.Colors.WHITE)),
                ]
                dlg.actions_alignment = ft.MainAxisAlignment.CENTER
                self.page.show_dialog(dlg)

            return ft.Row(controls=[
                entry['date_field'],
                entry['mesa_field'],
                entry['bs_field'],
                entry['be_field'],
                entry['profit_field'],
                ft.IconButton(ft.Icons.ARROW_UPWARD, on_click=on_up,
                              icon_size=13, icon_color='#aaaaaa', width=28, height=36),
                ft.IconButton(ft.Icons.ARROW_DOWNWARD, on_click=on_down,
                              icon_size=13, icon_color='#aaaaaa', width=28, height=36),
                ft.ElevatedButton(
                    content=ft.Text("✕", size=13, weight=ft.FontWeight.BOLD,
                                    text_align=ft.TextAlign.CENTER),
                    on_click=on_delete, height=36, width=36,
                    style=ft.ButtonStyle(
                        bgcolor='#c0392b', color=ft.Colors.WHITE,
                        padding=ft.padding.all(0),
                    ),
                ),
            ], spacing=2, tight=True)

        def _rebuild_col():
            sessions_col.controls = [_build_row(e) for e in session_fields]
            self.page.update()

        def _wire_profit(entry):
            """Attach on_change to bs/be fields so profit updates live."""
            def _recalc(e, en=entry):
                try:
                    bs = float(en['bs_field'].value or 0)
                except ValueError:
                    bs = 0.0
                try:
                    be = float(en['be_field'].value or 0)
                except ValueError:
                    be = 0.0
                en['profit_field'].value = str(round(be - bs, 2))
                en['profit_field'].update()
            entry['bs_field'].on_change = _recalc
            entry['be_field'].on_change = _recalc

        for sid, snum, date_str, mesa, bs, be, prof, prof_pct in sessions:
            entry = dict(
                sid=sid,
                date_field=ft.TextField(value=date_str, bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                        height=36, width=75, text_size=11,
                                        tooltip="Format: yy.mm.dd or dd/mm hh:mm"),
                mesa_field=ft.TextField(value=mesa or '', bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                        height=36, width=50, text_size=11),
                bs_field=ft.TextField(value=str(round(bs, 2)), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                      height=36, keyboard_type=ft.KeyboardType.NUMBER, width=55, text_size=11),
                be_field=ft.TextField(value=str(round(be, 2)), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                      height=36, keyboard_type=ft.KeyboardType.NUMBER, width=55, text_size=11),
                profit_field=ft.TextField(value=str(round(prof, 2)), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                          height=36, width=55, text_size=11, read_only=True),
            )
            _wire_profit(entry)
            session_fields.append(entry)

        sessions_col.controls = [_build_row(e) for e in session_fields]

        def on_add_session(ev):
            import datetime
            last_be = 0.0
            last_date = datetime.date.today().strftime('%y.%m.%d')
            last_mesa = ''
            if session_fields:
                prev = session_fields[-1]
                try:
                    last_be = float(prev['be_field'].value or 0)
                except ValueError:
                    pass
                last_date = prev['date_field'].value or last_date
                last_mesa = prev['mesa_field'].value or ''
            entry = dict(
                sid=None,
                date_field=ft.TextField(value=last_date, bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                        height=36, width=75, text_size=11),
                mesa_field=ft.TextField(value=last_mesa, bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                        height=36, width=50, text_size=11),
                bs_field=ft.TextField(value=str(round(last_be, 2)), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                      height=36, keyboard_type=ft.KeyboardType.NUMBER, width=55, text_size=11),
                be_field=ft.TextField(value=str(round(last_be, 2)), bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                      height=36, keyboard_type=ft.KeyboardType.NUMBER, width=55, text_size=11),
                profit_field=ft.TextField(value='0.00', bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK,
                                          height=36, width=55, text_size=11, read_only=True),
            )
            _wire_profit(entry)
            session_fields.append(entry)
            _rebuild_col()

        def on_save_all(ev):
            conn = self._get_conn()
            if not conn:
                return
            err_msg = None
            try:
                for new_snum, entry in enumerate(session_fields, start=1):
                    date_str = str(entry['date_field'].value).strip()
                    mesa_val = str(entry['mesa_field'].value).strip()
                    try:
                        bank_start = float(entry['bs_field'].value or 0)
                    except ValueError:
                        bank_start = 0.0
                    try:
                        bank_end = float(entry['be_field'].value or 0)
                    except ValueError:
                        bank_end = 0.0
                    profit = round(bank_end - bank_start, 2)
                    profit_pct = round((profit / bank_start * 100) if bank_start != 0 else 0, 2)
                    if entry['sid'] is None:
                        conn.execute(
                            "INSERT INTO compound_sessions "
                            "(investment_id, session_num, date, mesa, bank_start, bank_end, profit, profit_pct) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (investment_id, new_snum, date_str, mesa_val, bank_start, bank_end, profit, profit_pct),
                        )
                    else:
                        conn.execute(
                            "UPDATE compound_sessions "
                            "SET session_num=?, date=?, mesa=?, bank_start=?, bank_end=?, profit=?, profit_pct=? "
                            "WHERE id=?",
                            (new_snum, date_str, mesa_val, bank_start, bank_end, profit, profit_pct, entry['sid']),
                        )
                conn.commit()
            except Exception as ex:
                err_msg = str(ex)
            finally:
                conn.close()

            if err_msg:
                dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
                def _ce(ev2): dlg.open = False; dlg.update()
                dlg.title = ft.Text("ERROR", color='#ff4444', size=14, weight=ft.FontWeight.BOLD)
                dlg.content = ft.Text(f"Save failed: {err_msg}", color=ft.Colors.WHITE, size=11)
                dlg.actions = [ft.ElevatedButton("OK", on_click=_ce,
                    style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE))]
                dlg.actions_alignment = ft.MainAxisAlignment.CENTER
                self.page.show_dialog(dlg)
                return

            # Recompute table_stats from compound_sessions on a fresh connection
            self._recompute_table_stats(investment_id)

            dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
            def close_dlg(ev2):
                dlg.open = False
                dlg.update()
                self.show_investment_dashboard(investment_id)
            dlg.title = ft.Text("SESSIONS SAVED", color='#2ecc71', size=14, weight=ft.FontWeight.BOLD)
            dlg.content = ft.Text("All changes saved successfully.", color=ft.Colors.WHITE)
            dlg.actions = [ft.ElevatedButton("OK", on_click=close_dlg,
                style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE))]
            dlg.actions_alignment = ft.MainAxisAlignment.CENTER
            self.page.show_dialog(dlg)

        def go_back(ev):
            self.show_investment_dashboard(investment_id)

        header = ft.Row(controls=[
            ft.Text("DATE", color='#7f8c8d', width=75, weight=ft.FontWeight.BOLD, size=9),
            ft.Text("TABLE", color='#7f8c8d', width=50, weight=ft.FontWeight.BOLD, size=9),
            ft.Text("START $", color='#7f8c8d', width=55, weight=ft.FontWeight.BOLD, size=9),
            ft.Text("END $", color='#7f8c8d', width=55, weight=ft.FontWeight.BOLD, size=9),
            ft.Text("PROFIT", color='#7f8c8d', width=55, weight=ft.FontWeight.BOLD, size=9),
            ft.Text("", color='#7f8c8d', width=96, weight=ft.FontWeight.BOLD, size=9),
        ], spacing=2, tight=True)

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(expand=True, controls=[
                    ft.ElevatedButton("←  BACK", on_click=go_back,
                        style=ft.ButtonStyle(bgcolor='#34495e', color=ft.Colors.WHITE)),
                    ft.Container(height=12),
                    ft.Text(f"{inv_name}  —  EDIT SESSIONS",
                        color='#3498db', size=16, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Total sessions: {len(sessions)}  |  Base capital: "
                            + (f"{int(round(inv_capital)):,} chips" if inv_type == 'CHIPS'
                               else f"${inv_capital:.2f}"),
                        color='#7f8c8d', size=12),
                    ft.Container(height=10),
                    ft.Divider(color='#333333', height=1),
                    header,
                    ft.Divider(color='#333333', height=1),
                    sessions_col,
                    ft.Container(height=10),
                    ft.ElevatedButton("+ ADD SESSION", on_click=on_add_session,
                        height=44, expand=True,
                        style=ft.ButtonStyle(bgcolor='#2980b9', color=ft.Colors.WHITE)),
                    ft.Container(height=8),
                    ft.ElevatedButton("SAVE ALL CHANGES", on_click=on_save_all,
                        height=50, expand=True,
                        style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE)),
                ]),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # ACTUAL GROWTH GRAPH
    # ──────────────────────────────────────────────────────────────────
    def _read_bet_log(self) -> list:
        """Load all per-spin records from bet_log.jsonl (best-effort)."""
        import json
        rows = []
        path = (os.path.join(os.path.dirname(self.db_path), 'bet_log.jsonl')
                if getattr(self, 'db_path', None) else None)
        if path and os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                rows.append(json.loads(line))
                            except Exception:
                                pass
            except Exception:
                pass
        return rows

    def _compute_bet_eval(self) -> dict:
        """Analyse the real-bet log (bet_log.jsonl) — the player's realized entry
        decisions and outcomes. Returns a stats dict, or {'empty': True}."""
        rows = self._read_bet_log()
        if not rows:
            return {'empty': True}

        def roi(rs):
            cost = sum(r.get('cost', 0) or 0 for r in rs)
            net = sum(r.get('delta', 0) or 0 for r in rs)
            return net, cost, (100 * net / cost if cost else 0.0)

        def winrate(rs):
            g = [r for r in rs if r.get('is_win') is not None]
            if not g:
                return None
            return 100 * sum(1 for r in g if r['is_win']) / len(g)

        def block(rs):
            n, c, ro = roi(rs)
            return {'entries': len(rs), 'win': winrate(rs), 'net': n, 'roi': ro}

        scoreboard = self._suggestion_scoreboard(rows)
        acted = [r for r in rows if r.get('acted')]
        passed = [r for r in rows if not r.get('acted')]
        sug = [r for r in rows if (r.get('suggested') or {}).get('dozen')]
        waits = [r.get('spins_since_entry') for r in acted
                 if isinstance(r.get('spins_since_entry'), int)]
        by_regime = {}
        for r in acted:
            by_regime.setdefault((r.get('regime') or {}).get('kind', '?'), []).append(r)
        regimes = [dict(kind=k, **block(rs))
                   for k, rs in sorted(by_regime.items(), key=lambda kv: -len(kv[1]))]
        graded = sum(1 for r in acted if r.get('is_win') is not None)
        return {
            'empty': False,
            'spins': len(rows), 'entered': len(acted), 'passed': len(passed),
            'entry_rate': 100 * len(acted) / len(rows),
            'sug_shown': len(sug), 'sug_entered': sum(1 for r in sug if r.get('acted')),
            'avg_wait': (sum(waits) / len(waits) if waits else None),
            'graded': graded, **{k: v for k, v in zip(('net', 'staked', 'roi'), roi(acted))},
            'win': winrate(acted),
            'regimes': regimes,
            'followed': block([r for r in acted if r.get('followed_suggestion')]),
            'freelanced': block([r for r in acted if not r.get('followed_suggestion')]),
            'scoreboard': scoreboard,
        }

    def _suggestion_scoreboard(self, rows) -> list:
        """Counterfactual: for every logged spin, score EACH category's on-screen
        suggestion against the real outcome under the 1/2/3 chip-in progression
        (straight-up 35:1). Answers 'which suggestion types actually pay'. Uses
        the logged number sequence per session; needs records that carry the
        'suggestions' field (logged from v19.0.1+). Returns [] if none do."""
        PROG = (1, 2, 3)
        sessions = {}
        for r in rows:
            sessions.setdefault(r.get('session'), []).append(r)
        cats = {}
        for _sid, rs in sessions.items():
            rs = sorted(rs, key=lambda r: r.get('spin', 0))
            nums = [r.get('num') for r in rs]
            for i, r in enumerate(rs):
                sug = r.get('suggestions')
                if not sug or i + 3 > len(nums):   # need this spin + 2 forward
                    continue
                window = nums[i:i + 3]
                for cat, groups in sug.items():
                    if not groups:
                        continue
                    covered = set()
                    for g in groups:
                        covered |= GRUPOS_MAESTROS.get(g, set())
                    if not covered:
                        continue
                    K = len(covered)
                    pl, hit, staked = 0, False, 0
                    for stake, spin in zip(PROG, window):
                        pl -= stake * K
                        staked += stake * K
                        if spin in covered:
                            pl += 36 * stake
                            hit = True
                            break
                    d = cats.setdefault(cat, {'entries': 0, 'hits': 0,
                                              'net': 0, 'staked': 0, 'cov': 0})
                    d['entries'] += 1
                    d['hits'] += int(hit)
                    d['net'] += pl
                    d['staked'] += staked
                    d['cov'] += K
        out = []
        for cat, d in cats.items():
            e = d['entries']
            if not e:
                continue
            out.append({'cat': cat, 'entries': e,
                        'hitrate': 100 * d['hits'] / e,
                        'roi': 100 * d['net'] / d['staked'] if d['staked'] else 0.0,
                        'net': d['net'], 'avg_cov': d['cov'] / e})
        out.sort(key=lambda x: -x['roi'])
        return out

    # ── persistence for user-applied tuning / entry policy ───────────────────
    def _cfg_path(self, name):
        return (os.path.join(os.path.dirname(self.db_path), name)
                if getattr(self, 'db_path', None) else None)

    def _load_rvs_config(self):
        import json
        p = self._cfg_path('rvs_config.json')
        if p and os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                cfg = json.load(f)
            for k in list(RVS_CFG.keys()):
                if k in cfg:
                    RVS_CFG[k] = cfg[k]

    def _save_rvs_config(self, cfg):
        import json
        RVS_CFG.clear()
        RVS_CFG.update(cfg)
        p = self._cfg_path('rvs_config.json')
        if p:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(cfg, f)

    def _load_entry_policy(self):
        import json
        p = self._cfg_path('entry_policy.json')
        if p and os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            ks = d.get('kinds')
            return set(ks) if ks else None
        return None

    def _save_entry_policy(self, kinds):
        import json
        self.entry_policy = set(kinds) if kinds else None
        p = self._cfg_path('entry_policy.json')
        if p:
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'kinds': sorted(kinds) if kinds else []}, f)

    # ── #1: validated RVS auto-tune (train/test, never auto-applied) ─────────
    def _load_dealer_sequences(self):
        """[(label,[nums])] from croupier_log.txt + bundled croupier_data.txt."""
        import re
        seqs, paths = [], []
        if getattr(self, 'db_path', None):
            paths.append(os.path.join(os.path.dirname(self.db_path), 'croupier_log.txt'))
        paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'croupier_data.txt'))
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            label, nums = None, []
            try:
                for raw in open(path, encoding='utf-8'):
                    line = raw.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('@'):
                        if nums:
                            seqs.append((label or f'd{len(seqs)+1}', nums))
                        label, nums = line[1:].strip() or None, []
                    else:
                        nums.extend(int(x) for x in re.findall(r'\d+', line)
                                    if 0 <= int(x) <= 36)
                if nums:
                    seqs.append((label or f'd{len(seqs)+1}', nums))
            except Exception:
                pass
        return seqs

    @staticmethod
    def _pick_dozen_sa(window6):
        sc = {d: sum(DOZEN_SECTOR_AFFINITY[d].get(SECTOR_OF.get(n), 0.0)
                     for n in window6) / 6.0 for d in ('1a', '2a', '3a')}
        ranked = sorted(sc.items(), key=lambda kv: kv[1], reverse=True)
        if ranked[0][1] <= 0 or abs(ranked[0][1] - ranked[1][1]) < 1e-9:
            return None
        return ranked[0][0]

    def _eval_rvs(self, dealers, cfg):
        """Net chips & staked over dealers: sector dozen + RVS(cfg) colour, ridden
        under the 1/2/3 chip-in progression (straight-up 35:1)."""
        PROG = (1, 2, 3)
        net = staked = 0
        for _lbl, nums in dealers:
            for i in range(6, len(nums) - 2):
                dozen = self._pick_dozen_sa(nums[i - 6:i])
                if not dozen:
                    continue
                color = regime_color(nums[:i], cfg)
                cov = GRUPOS_MAESTROS.get(f'{dozen}{_DOC_SFX.get(color, "_L")}')
                if not cov:
                    continue
                K = len(cov)
                for stake, spin in zip(PROG, nums[i:i + 3]):
                    net -= stake * K
                    staked += stake * K
                    if spin in cov:
                        net += 36 * stake
                        break
        return net, staked

    def _tune_rvs_candidate(self, min_dealers=8):
        """Fit RVS thresholds on a train split, validate on a held-out split.
        Returns the candidate + its held-out ROI vs the current config's."""
        dealers = self._load_dealer_sequences()
        if len(dealers) < min_dealers:
            return {'ok': False,
                    'reason': f'need ≥{min_dealers} dealers, have {len(dealers)}'}
        train = [d for i, d in enumerate(dealers) if i % 2 == 0]
        test = [d for i, d in enumerate(dealers) if i % 2 == 1]

        def roi(ds, cfg):
            n, s = self._eval_rvs(ds, cfg)
            return (100 * n / s if s else 0.0)

        best = None
        for streak in (0.55, 0.60, 0.65):
            for rhythm in (0.30, 0.35, 0.40):
                for ride in (4, 5):
                    for bias in (0.12, 0.15, 0.20):
                        cfg = {**RVS_CFG, 'streak': streak, 'rhythm': rhythm,
                               'ride_len': ride, 'bias': bias}
                        r = roi(train, cfg)
                        if best is None or r > best[0]:
                            best = (r, cfg)
        cand = best[1]
        cand_roi = roi(test, cand)
        cur_roi = roi(test, dict(RVS_CFG))
        return {'ok': True, 'n_train': len(train), 'n_test': len(test),
                'candidate': cand, 'cand_test_roi': cand_roi,
                'cur_test_roi': cur_roi, 'improvement': cand_roi - cur_roi}

    # ── #2: entry-policy learning (train/test on the player's real bets) ─────
    def _learn_entry_policy_candidate(self, min_entries=20, min_per_kind=5,
                                      train_frac=0.6):
        """From real bets: learn which regimes the player's ENTRIES win in on the
        earlier bets, then check filtering to those regimes improves ROI on the
        LATER (held-out) bets. Temporal past→future split — works within a single
        session and is the honest test for an entry policy."""
        acted = [r for r in self._read_bet_log()
                 if r.get('acted') and r.get('is_win') is not None]
        if len(acted) < min_entries:
            return {'ok': False,
                    'reason': f'need ≥{min_entries} graded entries, have {len(acted)}'}
        cut = max(1, int(len(acted) * train_frac))
        train, test = acted[:cut], acted[cut:]
        if not test:
            return {'ok': False,
                    'reason': 'not enough entries to hold out a test set'}

        def roi(rs):
            c = sum(r.get('cost', 0) or 0 for r in rs)
            n = sum(r.get('delta', 0) or 0 for r in rs)
            return (100 * n / c if c else 0.0)

        bykind = {}
        for r in train:
            bykind.setdefault((r.get('regime') or {}).get('kind', '?'), []).append(r)
        policy = {k for k, rs in bykind.items()
                  if len(rs) >= min_per_kind and roi(rs) > 0}
        test_all = roi(test)
        test_pol = roi([r for r in test
                        if (r.get('regime') or {}).get('kind', '?') in policy])
        return {'ok': True, 'policy': sorted(policy),
                'train_bykind': {k: (len(rs), roi(rs)) for k, rs in bykind.items()},
                'test_all_roi': test_all, 'test_policy_roi': test_pol,
                'improvement': test_pol - test_all,
                'n_train': len(train), 'n_test': len(test)}

    def _roi_bars(self, items):
        """items: [(label, value_float)] -> a horizontal bar chart Container.
        Bars grow right (green, +) / left (red, −) from a centre zero line; the
        numeric value is baked into each label so nothing overflows."""
        import flet.canvas as cv
        import inspect
        _tv = ('value' if 'value' in inspect.signature(cv.Text.__init__).parameters
               else 'text')

        def _t(x, y, s, color='#dddddd', size=11):
            return cv.Text(x=x, y=y, style=ft.TextStyle(color=color, size=size),
                           **{_tv: str(s)})

        items = list(items)
        row_h, top, label_w = 24, 6, 150
        H = top * 2 + max(len(items), 1) * row_h

        def build(cw):
            shapes = []
            if not items:
                return shapes
            bw = max(30, cw - label_w - 6)
            cx = label_w + bw / 2
            maxabs = max((abs(v) for _, v in items), default=1) or 1
            shapes.append(cv.Line(x1=cx, y1=top, x2=cx, y2=top + len(items) * row_h,
                                  paint=ft.Paint(color='#555555', stroke_width=1)))
            for i, (label, v) in enumerate(items):
                cy = top + i * row_h + row_h / 2
                length = (abs(v) / maxabs) * (bw / 2 - 4)
                color = '#2ecc71' if v >= 0 else '#e74c3c'
                rx = cx if v >= 0 else cx - length
                shapes.append(cv.Rect(x=rx, y=cy - 7, width=max(length, 1), height=14,
                                      paint=ft.Paint(color=color,
                                                     style=ft.PaintingStyle.FILL)))
                shapes.append(_t(2, cy - 7, str(label)[:26]))
            return shapes

        canvas = cv.Canvas(
            shapes=[], expand=True, height=H, resize_interval=0,
            on_resize=lambda e: (setattr(canvas, 'shapes', build(e.width))
                                 or canvas.update()))
        return ft.Container(bgcolor='#0d0d0d', border_radius=8, padding=4,
                            content=canvas, height=H)

    def show_bet_eval_view(self, investment_id: int = None):
        """AI Bet Eval page — how the player's real entry decisions performed
        (reads bet_log.jsonl, global across all logged play)."""
        s = self._compute_bet_eval()

        def go_back(ev):
            if investment_id is not None:
                self.show_investment_dashboard(investment_id)
            else:
                self.show_main_menu()

        def _apply_cfg(cfg):
            def h(ev):
                try:
                    self._save_rvs_config(cfg)
                except Exception:
                    pass
                self.show_bet_eval_view(investment_id)
            return h

        def _apply_policy(kinds):
            def h(ev):
                try:
                    self._save_entry_policy(kinds)
                except Exception:
                    pass
                self.show_bet_eval_view(investment_id)
            return h

        def _clear_policy(ev):
            try:
                self._save_entry_policy(None)
            except Exception:
                pass
            self.show_bet_eval_view(investment_id)

        def pct(x):
            return '--' if x is None else f"{x:.0f}%"

        rows = []

        def hdr(t):
            rows.append(ft.Text(t, color='#16a085', size=15,
                                weight=ft.FontWeight.BOLD))

        def line(t, c='#dddddd'):
            rows.append(ft.Text(t, color=c, size=13))

        if s.get('empty'):
            line("No bets logged yet.", '#f1c40f')
            line("Play some sessions — every spin is logged — then reopen this page.")
        else:
            hdr("Entry behaviour")
            line(f"Spins logged: {s['spins']}")
            line(f"Entered (bet): {s['entered']}   ({s['entry_rate']:.0f}%)")
            line(f"Passed (no bet): {s['passed']}")
            line(f"Suggestion shown: {s['sug_shown']}   (entered {s['sug_entered']})")
            if s['avg_wait'] is not None:
                line(f"Avg wait before entry: {s['avg_wait']:.1f} spins")
            rows.append(ft.Divider(color='#333'))

            hdr("Realized results — bets you actually placed")
            line(f"Entries: {s['entered']}    Win rate: {pct(s['win'])} ({s['graded']} graded)")
            line(f"Net: {s['net']:+.2f}    Staked: {s['staked']:.2f}")
            rows.append(ft.Text(
                f"ROI: {s['roi']:+.2f}%",
                color=('#2ecc71' if s['roi'] >= 0 else '#ff5555'),
                size=18, weight=ft.FontWeight.BOLD))
            rows.append(ft.Divider(color='#333'))

            hdr("By regime (entries only)  — bar = ROI")
            if not s['regimes']:
                line("(no entries yet)")
            else:
                rows.append(self._roi_bars(
                    [(f"{rr['kind']} {rr['roi']:+.0f}% ({rr['entries']}b)", rr['roi'])
                     for rr in s['regimes']]))
            rows.append(ft.Divider(color='#333'))

            hdr("Following the suggested dozen vs freelancing")
            fb = [(f"{lbl_} {b['roi']:+.0f}% ({b['entries']}b)", b['roi'])
                  for lbl_, b in (("Followed", s['followed']),
                                  ("Freelanced", s['freelanced'])) if b['entries']]
            if fb:
                rows.append(self._roi_bars(fb))
            else:
                line("(no entries yet)")
            rows.append(ft.Divider(color='#333'))

            hdr("Suggestion scoreboard — every option (bar = ROI)")
            _CAT_NAME = {'docs': 'Dozen+col', 'cols': 'Columns',
                         'secs': 'Sectors', 'thirds': 'Thirds', 'wave': 'Waves'}
            if not s.get('scoreboard'):
                line("Needs spins logged with v19.0.1+ (all on-screen "
                     "suggestions). Play more and reopen.", '#f1c40f')
            else:
                rows.append(self._roi_bars(
                    [(f"{_CAT_NAME.get(sc['cat'], sc['cat'])} {sc['roi']:+.0f}% "
                      f"({sc['hitrate']:.0f}% hit)", sc['roi'])
                     for sc in s['scoreboard']]))
            rows.append(ft.Container(height=6))
            line("Realized play (what you actually bet), not the every-spin "
                 "backtest. The scoreboard is counterfactual — how each option "
                 "type would have paid, following its suggestion.", '#7f8c8d')

        # ── #1 RVS auto-tune (always shown; uses dealer sequences) ───────────
        rows.append(ft.Divider(color='#16a085'))
        hdr("Model tuning — RVS (held-out validated)")
        cand = self._tune_rvs_candidate()
        if not cand.get('ok'):
            line(cand.get('reason', '—'), '#f1c40f')
        else:
            line(f"Fit on {cand['n_train']} dealers, tested on {cand['n_test']} "
                 f"held-out.")
            line(f"Current config held-out ROI: {cand['cur_test_roi']:+.2f}%")
            cc = '#2ecc71' if cand['improvement'] >= 0 else '#ff5555'
            rows.append(ft.Text(
                f"Candidate held-out ROI: {cand['cand_test_roi']:+.2f}%  "
                f"(Δ {cand['improvement']:+.2f})", color=cc, size=14,
                weight=ft.FontWeight.BOLD))
            c = cand['candidate']
            line(f"cfg: streak≥{c['streak']}  rhythm≤{c['rhythm']}  "
                 f"ride≥{c['ride_len']}  bias≥{c['bias']}", '#aaaaaa')
            if cand['improvement'] > 0.5:
                rows.append(ft.ElevatedButton(
                    "APPLY TUNED CONFIG", on_click=_apply_cfg(c), height=42,
                    style=ft.ButtonStyle(bgcolor='#16a085', color=ft.Colors.WHITE)))
                line("Beats current on data it wasn't tuned on. Applies on tap only.",
                     '#7f8c8d')
            else:
                line("No candidate beats the current config out-of-sample — "
                     "keeping current.", '#7f8c8d')

        # ── #2 entry-policy learning (uses the player's real bets) ───────────
        rows.append(ft.Divider(color='#16a085'))
        hdr("Entry policy — your winning regimes (held-out validated)")
        pol = self._learn_entry_policy_candidate()
        if not pol.get('ok'):
            line(pol.get('reason', '—'), '#f1c40f')
        else:
            line(f"Fit on {pol['n_train']} entries, tested on {pol['n_test']} "
                 f"held-out.  (bar = ROI per regime, train)")
            rows.append(self._roi_bars(
                [(f"{k} {rk:+.0f}% ({nk}b)", rk)
                 for k, (nk, rk) in sorted(pol['train_bykind'].items(),
                                           key=lambda kv: -kv[1][1])]))
            line(f"Recommend entering only: "
                 f"{', '.join(pol['policy']) if pol['policy'] else '(none)'}")
            cc = '#2ecc71' if pol['improvement'] >= 0 else '#ff5555'
            rows.append(ft.Text(
                f"Held-out: all {pol['test_all_roi']:+.1f}%  →  "
                f"filtered {pol['test_policy_roi']:+.1f}%  (Δ {pol['improvement']:+.1f})",
                color=cc, size=13))
            if pol['policy'] and pol['improvement'] > 0.5:
                rows.append(ft.ElevatedButton(
                    "APPLY ENTRY FILTER", on_click=_apply_policy(pol['policy']),
                    height=42,
                    style=ft.ButtonStyle(bgcolor='#16a085', color=ft.Colors.WHITE)))
                line("The AI bar will flag ENTER/SKIP by regime. Applies on tap only.",
                     '#7f8c8d')
            else:
                line("Filtering doesn't improve held-out ROI — no filter "
                     "recommended.", '#7f8c8d')
        if getattr(self, 'entry_policy', None):
            rows.append(ft.Row(spacing=8, controls=[
                ft.Text(f"Active entry filter: {', '.join(sorted(self.entry_policy))}",
                        color='#f1c40f', size=12, expand=True),
                ft.ElevatedButton("CLEAR", on_click=_clear_policy, height=34,
                                  style=ft.ButtonStyle(bgcolor='#7f8c8d',
                                                       color=ft.Colors.WHITE)),
            ]))

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True,
                content=ft.Column(expand=True, controls=[
                    ft.Container(
                        bgcolor='#2c3e50',
                        padding=ft.padding.only(left=8, right=8, top=36, bottom=8),
                        content=ft.Row(controls=[
                            ft.ElevatedButton(
                                "BACK", on_click=go_back,
                                style=ft.ButtonStyle(bgcolor='#34495e',
                                                     color=ft.Colors.WHITE)),
                            ft.Text("AI BET EVAL  —  all logged play",
                                    color=ft.Colors.WHITE, size=13,
                                    weight=ft.FontWeight.BOLD, expand=True,
                                    text_align=ft.TextAlign.RIGHT),
                        ]),
                    ),
                    ft.ListView(controls=rows, expand=True, spacing=6, padding=14),
                ]),
            )
        )

    def show_actual_graph_view(self, investment_id: int, inv_name: str,
                               inv_capital: float, inv_type: str = 'FIAT',
                               mesa_usd_rate: dict = None, usd_capital: float = 0.0):
        """Display comprehensive growth analysis with stats, table, bar chart, pie chart."""
        import flet.canvas as cv, inspect
        # cv.Text uses 'value' in Flet ≥0.83, 'text' in older versions
        _tv = ('value' if 'value' in inspect.signature(cv.Text.__init__).parameters
               else 'text')

        def _cv_text(x, y, txt, color='#888888', size=8):
            return cv.Text(x=x, y=y,
                           style=ft.TextStyle(color=color, size=size),
                           **{_tv: str(txt)})

        # Fetch detailed session data
        sessions = []  # list of (id, date_str, profit, mesa, bank_start, bank_end)
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT rowid, date, profit, mesa, bank_start, bank_end FROM compound_sessions "
                    "WHERE investment_id=? ORDER BY rowid",
                    (investment_id,)
                )
                sessions = cursor.fetchall()
            except Exception:
                pass
            finally:
                conn.close()

        if mesa_usd_rate is None:
            mesa_usd_rate = {}

        chips_mode = inv_type == 'CHIPS'

        def go_back(ev):
            self.show_investment_dashboard(investment_id)

        def export_data(ev):
            """Export analytics data to CSV and PDF."""
            # Build KPIs dict for export
            kpis_for_export = {
                'Total Sessions': n_sessions,
                'Winning Sessions': n_winning,
                'Losing Sessions': n_losing,
                'Success Rate (%)': f"{success_rate:.1f}",
                'Max Gain (%)': f"{max_gain:.2f}",
                'Max Loss (%)': f"{max_loss:.2f}",
                'Average per Session (%)': f"{avg_per_session:.3f}",  # 3 decimals for precision
                'Consistency': f"{consistency:.2f}",
                'Win/Loss Ratio': f"{win_loss_ratio:.2f}",
                'Best Streak': best_streak,
                'Worst Streak': worst_streak,
                'Max Drawdown (%)': f"{max_drawdown:.2f}",
                'Initial Capital': _fv(start_capital),
                'Final Capital': _fv(final_capital),
                'Total Growth (%)': f"{total_return_pct:.2f}",
            }
            
            # Export to CSV
            csv_path = self._export_to_csv(investment_id, inv_name, session_data,
                                          bucket_labels, bucket_counts, kpis_for_export)
            # Export to PDF
            pdf_path, pdf_error = self._export_to_pdf(investment_id, inv_name, session_data,
                                                       bucket_labels, bucket_counts, kpis_for_export)
            
            # Show result dialog
            msg = ""
            if csv_path:
                msg += f"✓ CSV: {os.path.basename(csv_path)}\n"
            else:
                msg += "✗ CSV export failed\n"
            if pdf_path:
                msg += f"✓ PDF: {os.path.basename(pdf_path)}"
            else:
                msg += f"✗ PDF export failed"
                if pdf_error:
                    msg += f"\n\n{pdf_error}"
            
            dlg = ft.AlertDialog(
                title=ft.Text("Export Complete", color='#3498db', weight=ft.FontWeight.BOLD),
                content=ft.Text(msg, color=ft.Colors.WHITE),
                modal=True, bgcolor='#1e1e1e',
            )
            dlg.actions = [
                ft.ElevatedButton(
                    "OK", on_click=lambda _e: (setattr(dlg, 'open', False), dlg.update()),
                    style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
                )
            ]
            self.page.show_dialog(dlg)

        # Always display in USD for the graph
        def _fv(v):
            return f"${v:.2f}"

        # Calculate statistics
        start_capital = usd_capital if chips_mode else float(inv_capital)
        session_data = []  # list of (return_pct, bank_start, bank_end, profit_amount, date_str)
        
        running_capital = start_capital
        for sid, date_str, profit, mesa, bank_start, bank_end in sessions:
            delta = (profit * mesa_usd_rate.get(mesa, 0.0)) if chips_mode else profit
            bank_end_calc = running_capital + delta
            return_pct = (delta / running_capital * 100) if running_capital > 0 else 0
            session_data.append((return_pct, running_capital, bank_end_calc, delta, date_str))
            running_capital = bank_end_calc

        final_capital = running_capital
        total_return_pct = ((final_capital - start_capital) / start_capital * 100) if start_capital > 0 else 0

        # Calculate KPIs
        n_sessions = len(session_data)
        n_winning = sum(1 for r, _, _, _, _ in session_data if r > 0)
        n_losing = sum(1 for r, _, _, _, _ in session_data if r < 0)
        n_neutral = n_sessions - n_winning - n_losing  # Sessions with exactly 0% return
        success_rate = (n_winning / n_sessions * 100) if n_sessions > 0 else 0
        
        return_pcts = [r for r, _, _, _, _ in session_data]
        max_gain = max(return_pcts) if return_pcts else 0
        max_loss = min(return_pcts) if return_pcts else 0
        avg_per_session = sum(return_pcts) / n_sessions if n_sessions > 0 else 0
        consistency = (sum((r - avg_per_session) ** 2 for r in return_pcts) / n_sessions) ** 0.5 if n_sessions > 0 else 0
        
        total_gains = sum(r for r in return_pcts if r > 0)
        total_losses = abs(sum(r for r in return_pcts if r < 0))
        win_loss_ratio = (total_gains / total_losses) if total_losses > 0 else (total_gains if total_gains > 0 else 0)
        
        # Calculate streaks (0% returns treated as neutral, not losses)
        best_streak = 0
        worst_streak = 0
        current_win_streak = 0
        current_loss_streak = 0
        for r in return_pcts:
            if r > 0:
                current_win_streak += 1
                current_loss_streak = 0
                best_streak = max(best_streak, current_win_streak)
            elif r < 0:  # Only count negative as losses, not 0%
                current_loss_streak += 1
                current_win_streak = 0
                worst_streak = max(worst_streak, current_loss_streak)
            else:  # r == 0
                current_win_streak = 0
                current_loss_streak = 0
        
        # Calculate max drawdown
        max_capital = start_capital
        max_drawdown = 0
        for r, bank_start, bank_end, _, _ in session_data:
            max_capital = max(max_capital, bank_end)
            drawdown = ((max_capital - bank_end) / max_capital * 100) if max_capital > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        # Bucket sessions for pie chart (5 buckets)
        bucket_ranges = [(-float('inf'), -5), (-5, 0), (0, 5), (5, 10), (10, float('inf'))]
        bucket_labels = ["< -5%", "-5% to 0%", "0% to 5%", "5% to 10%", "> 10%"]
        bucket_colors = ['#c0392b', '#e67e22', '#2ecc71', '#27ae60', '#1e8449']
        bucket_counts = [0] * 5
        
        for r, _, _, _, _ in session_data:
            if r < -5:
                bucket_counts[0] += 1
            elif r <= 0:
                bucket_counts[1] += 1
            elif r <= 5:
                bucket_counts[2] += 1
            elif r <= 10:
                bucket_counts[3] += 1
            else:
                bucket_counts[4] += 1

        controls: list = [
            ft.Row(controls=[
                ft.ElevatedButton(
                    "←  BACK", on_click=go_back,
                    style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
                    expand=1,
                ),
                ft.ElevatedButton(
                    "⬇  EXPORT", on_click=export_data,
                    style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
                    expand=1,
                ),
            ], spacing=3),
            ft.Container(height=12),
            ft.Text(f"{inv_name}  —  ACTUAL GROWTH",
                    color='#3498db', size=14, weight=ft.FontWeight.BOLD),
            ft.Container(height=6),
        ]

        if n_sessions == 0:
            controls.append(
                ft.Text("No sessions saved yet — play and save sessions first.",
                        color='#7f8c8d', size=12,
                        text_align=ft.TextAlign.CENTER)
            )
        else:
            # ──────────────────────────────────────────────────────────────────
            # INDICATORS (KPIs)
            # ──────────────────────────────────────────────────────────────────
            kpi_rows = [
                (f"Total sesiones", f"{n_sessions}", '#95a5a6'),
                (f"Ganadoras", f"{n_winning}", '#2ecc71'),
                (f"Perdedoras", f"{n_losing}", '#e74c3c'),
                (f"Efectividad", f"{success_rate:.1f}%", '#3498db'),
                (f"Max ganancia", f"+{max_gain:.2f}%", '#2ecc71'),
                (f"Max pérdida", f"{max_loss:.2f}%", '#e74c3c'),
                (f"Promedio por sesión", f"{avg_per_session:+.3f}%", '#f39c12'),  # Show 3 decimals for precision
                (f"Consistencia", f"{consistency:.2f}%", '#9b59b6'),
                (f"Relación Ganancia/Pérdida", f"{win_loss_ratio:.2f}", '#3498db'),
                (f"Mejor racha", f"{best_streak}", '#2ecc71'),
                (f"Peor racha", f"{worst_streak}", '#e74c3c'),
                (f"Máx. drawdown", f"{max_drawdown:.2f}%", '#e67e22'),
                (f"Capital inicial", _fv(start_capital), '#95a5a6'),
                (f"Capital final", _fv(final_capital), '#2ecc71' if final_capital >= start_capital else '#e74c3c'),
                (f"Crecimiento total", f"{total_return_pct:+.2f}%", '#2ecc71' if total_return_pct >= 0 else '#e74c3c'),
            ]
            
            kpi_grid = []
            for i in range(0, len(kpi_rows), 3):
                row_items = kpi_rows[i:i+3]
                row_controls = []
                for label, value, color in row_items:
                    row_controls.append(
                        ft.Container(
                            bgcolor='#1a2a3a',
                            padding=8,
                            border_radius=4,
                            expand=True,
                            content=ft.Column(
                                tight=True,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(label, color='#7f8c8d', size=9, text_align=ft.TextAlign.CENTER),
                                    ft.Text(value, color=color, size=12, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                                ],
                            ),
                        )
                    )
                kpi_grid.append(ft.Row(controls=row_controls, spacing=4))
            
            controls.append(
                ft.Container(
                    bgcolor='#0d0d0d',
                    padding=10,
                    border_radius=6,
                    content=ft.Column(controls=kpi_grid, spacing=4),
                )
            )
            controls.append(ft.Container(height=12))

            # ──────────────────────────────────────────────────────────────────
            # GROWTH GRAPH
            # ──────────────────────────────────────────────────────────────────
            pts = [(0, start_capital)]
            for r, bank_start, bank_end, _, _ in session_data:
                pts.append((len(pts), bank_end))

            yvals  = [p[1] for p in pts]
            # Range floor uses start_capital (same unit as the plotted values:
            # USD for CHIPS, capital for FIAT) so the y-scale isn't distorted.
            data_range = max(max(yvals) - min(yvals), abs(start_capital * 0.01), 1.0)
            mid    = (max(yvals) + min(yvals)) / 2
            half   = data_range * 1.5 / 2
            min_y  = mid - half
            max_y  = mid + half
            y_span = max_y - min_y
            max_xi = len(pts) - 1
            line_color = '#2ecc71' if final_capital >= start_capital else '#ff4444'

            ML, MR, MT, MB = 62, 8, 8, 22
            CH = 240

            def _build_shapes(cw):
                pw = max(cw - ML - MR, 1.0)
                ph = float(CH - MT - MB)

                def sx(xi): return ML + (xi / max_xi) * pw if max_xi else ML
                def sy(yv): return MT + (1.0 - (yv - min_y) / y_span) * ph

                shapes = []
                shapes.append(cv.Rect(x=ML, y=MT, width=pw, height=ph,
                                     paint=ft.Paint(color='#1a2535', style=ft.PaintingStyle.FILL)))

                for i in range(5):
                    gy  = MT + i * ph / 4
                    val = max_y - i * y_span / 4
                    shapes.append(cv.Line(x1=ML, y1=gy, x2=ML + pw, y2=gy,
                                         paint=ft.Paint(color='#2a2a2a', stroke_width=1)))
                    shapes.append(_cv_text(0, gy - 6, _fv(val)))

                bey = sy(start_capital)
                if MT <= bey <= MT + ph:
                    x = ML
                    while x < ML + pw:
                        shapes.append(cv.Line(x1=x, y1=bey, x2=min(x + 4, ML + pw), y2=bey,
                                             paint=ft.Paint(color='#666666', stroke_width=1)))
                        x += 8

                # Screen-space points + smooth (Catmull-Rom -> cubic Bézier)
                # curve segments that still pass through every data point.
                sp = [(sx(xi), sy(yi)) for xi, yi in pts]

                def _smooth_segments():
                    segs = []
                    n = len(sp)
                    for i in range(n - 1):
                        p0 = sp[i - 1] if i > 0 else sp[i]
                        p1 = sp[i]
                        p2 = sp[i + 1]
                        p3 = sp[i + 2] if i + 2 < n else sp[i + 1]
                        cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
                        cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
                        cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
                        cp2y = p2[1] - (p3[1] - p1[1]) / 6.0
                        segs.append(cv.Path.CubicTo(cp1x=cp1x, cp1y=cp1y,
                                                    cp2x=cp2x, cp2y=cp2y,
                                                    x=p2[0], y=p2[1]))
                    return segs

                curve = _smooth_segments()

                fill = [cv.Path.MoveTo(x=sp[0][0], y=sp[0][1])]
                fill.extend(curve)
                fill.append(cv.Path.LineTo(x=sp[-1][0], y=MT + ph))
                fill.append(cv.Path.LineTo(x=sx(0), y=MT + ph))
                fill.append(cv.Path.Close())
                shapes.append(cv.Path(elements=fill, paint=ft.Paint(color=line_color + '33', style=ft.PaintingStyle.FILL)))

                line = [cv.Path.MoveTo(x=sp[0][0], y=sp[0][1])]
                line.extend(curve)
                shapes.append(cv.Path(elements=line, paint=ft.Paint(color=line_color, stroke_width=2, style=ft.PaintingStyle.STROKE)))

                if len(pts) <= 25:
                    for xi, yi in pts:
                        shapes.append(cv.Circle(x=sx(xi), y=sy(yi), radius=3,
                                               paint=ft.Paint(color=line_color, style=ft.PaintingStyle.FILL)))

                x_step = max(1, round(max_xi / 5))
                for i in range(0, len(pts), x_step):
                    shapes.append(_cv_text(sx(i) - 4, MT + ph + 4, str(i)))

                shapes.append(cv.Line(x1=ML, y1=MT, x2=ML, y2=MT + ph,
                                     paint=ft.Paint(color='#444444', stroke_width=1)))
                shapes.append(cv.Line(x1=ML, y1=MT + ph, x2=ML + pw, y2=MT + ph,
                                     paint=ft.Paint(color='#444444', stroke_width=1)))
                return shapes

            canvas_ctrl = cv.Canvas(shapes=[], expand=True, height=CH, resize_interval=0,
                                   on_resize=lambda e: (setattr(canvas_ctrl, 'shapes', _build_shapes(e.width)) or canvas_ctrl.update()))

            controls.append(ft.Text("Crecimiento del Capital", color='#3498db', size=12, weight=ft.FontWeight.BOLD))
            controls.append(ft.Container(bgcolor='#0d0d0d', border_radius=8, padding=0, content=canvas_ctrl, height=CH))
            controls.append(ft.Container(height=12))

            # ──────────────────────────────────────────────────────────────────
            # BAR CHART (Return % per session)
            # ──────────────────────────────────────────────────────────────────
            min_ret = min(return_pcts) if return_pcts else 0
            max_ret = max(return_pcts) if return_pcts else 0
            # Use tighter dynamic range with minimal padding
            ret_range = max_ret - min_ret
            if ret_range == 0:
                min_ret = -1
                max_ret = 1
            else:
                # Add small padding (5% of range) on each side for tighter display
                padding = ret_range * 0.05
                min_ret -= padding
                max_ret += padding

            def _build_bar_chart(cw):
                shapes = []
                bar_height = 150
                bar_width = cw - 40
                bar_x_start = 20

                # Background
                shapes.append(cv.Rect(x=bar_x_start, y=10, width=bar_width, height=bar_height,
                                     paint=ft.Paint(color='#1a2535', style=ft.PaintingStyle.FILL)))

                # Center line (0%)
                center_y = 10 + bar_height / 2
                shapes.append(cv.Line(x1=bar_x_start, y1=center_y, x2=bar_x_start + bar_width, y2=center_y,
                                     paint=ft.Paint(color='#666666', stroke_width=1)))

                # Y-axis labels with % symbol (positioned to the left)
                # Top label (max%)
                shapes.append(_cv_text(5, 12, f"{max_ret:.1f}%"))
                # Center label (0%)
                shapes.append(_cv_text(10, center_y - 4, "0%"))
                # Bottom label (min%)
                shapes.append(_cv_text(5, 10 + bar_height - 8, f"{min_ret:.1f}%"))

                # Bars - positive go up, negative go down from center
                n_bars = min(len(return_pcts), 20)  # Limit to 20 bars for visibility
                bar_spacing = bar_width / (n_bars + 1)
                max_abs_ret = max(abs(min_ret), abs(max_ret)) if max_ret != min_ret else 1
                
                for i in range(n_bars):
                    idx = int(i * len(return_pcts) / n_bars)
                    ret = return_pcts[idx]
                    # Normalize to -1 to +1 range (relative to max absolute value)
                    bar_height_px = (ret / max_abs_ret) * (bar_height / 2)
                    
                    if ret >= 0:
                        # Positive: draw upward from center
                        bar_y = center_y - bar_height_px
                    else:
                        # Negative: draw downward from center
                        bar_y = center_y
                        bar_height_px = abs(bar_height_px)
                    
                    bar_color = '#2ecc71' if ret > 0 else '#e74c3c'
                    bar_x = bar_x_start + (i + 1) * bar_spacing

                    shapes.append(cv.Rect(
                        x=bar_x - 2, y=bar_y, width=4, height=bar_height_px,
                        paint=ft.Paint(color=bar_color, style=ft.PaintingStyle.FILL)
                    ))

                return shapes

            bar_chart = cv.Canvas(shapes=[], expand=True, height=180, resize_interval=0,
                                 on_resize=lambda e: (setattr(bar_chart, 'shapes', _build_bar_chart(e.width)) or bar_chart.update()))

            controls.append(ft.Text("Retorno por Sesión (%)", color='#3498db', size=12, weight=ft.FontWeight.BOLD))
            controls.append(ft.Container(bgcolor='#0d0d0d', border_radius=8, padding=0, content=bar_chart, height=180))
            controls.append(ft.Container(height=12))

            # ──────────────────────────────────────────────────────────────────
            # PIE CHART (Session buckets)
            # ──────────────────────────────────────────────────────────────────
            def _build_pie_chart(cw):
                shapes = []
                total_sessions = sum(bucket_counts)
                if total_sessions == 0:
                    return shapes

                # Pie geometry — centered in the 160px-tall canvas
                center_x = cw / 2
                center_y = 80
                radius = 64
                inner_radius = 30  # donut hole

                start_angle = -math.pi / 2  # start at 12 o'clock
                for i, count in enumerate(bucket_counts):
                    if count == 0:
                        continue
                    frac = count / total_sessions
                    sweep = frac * 2 * math.pi
                    end_angle = start_angle + sweep

                    # Approximate the wedge with line segments along the arc
                    steps = max(2, int(sweep / 0.15) + 1)
                    elements = [cv.Path.MoveTo(x=center_x, y=center_y)]
                    for s in range(steps + 1):
                        a = start_angle + sweep * (s / steps)
                        elements.append(cv.Path.LineTo(
                            x=center_x + radius * math.cos(a),
                            y=center_y + radius * math.sin(a),
                        ))
                    elements.append(cv.Path.Close())
                    shapes.append(cv.Path(
                        elements=elements,
                        paint=ft.Paint(color=bucket_colors[i], style=ft.PaintingStyle.FILL)
                    ))

                    # Percentage label at the slice midpoint (only if big enough)
                    if frac >= 0.04:
                        mid = start_angle + sweep / 2
                        lr = (radius + inner_radius) / 2
                        shapes.append(_cv_text(
                            center_x + lr * math.cos(mid) - 8,
                            center_y + lr * math.sin(mid) - 6,
                            f"{frac * 100:.0f}%", color='#ffffff', size=9,
                        ))

                    start_angle = end_angle

                # Donut hole (matches card background) + total count in the middle
                shapes.append(cv.Circle(x=center_x, y=center_y, radius=inner_radius,
                                        paint=ft.Paint(color='#0d0d0d', style=ft.PaintingStyle.FILL)))
                shapes.append(_cv_text(center_x - 8, center_y - 12,
                                       str(total_sessions), color='#ffffff', size=14))
                shapes.append(_cv_text(center_x - 14, center_y + 4,
                                       "ses.", color='#7f8c8d', size=8))

                return shapes

            pie_chart = cv.Canvas(shapes=[], expand=True, height=160, resize_interval=0,
                                 on_resize=lambda e: (setattr(pie_chart, 'shapes', _build_pie_chart(e.width)) or pie_chart.update()))

            # Legend
            legend_items = []
            for label, count, color in zip(bucket_labels, bucket_counts, bucket_colors):
                pct = (count / n_sessions * 100) if n_sessions > 0 else 0
                legend_items.append(
                    ft.Row(spacing=8, controls=[
                        ft.Container(width=12, height=12, bgcolor=color, border_radius=2),
                        ft.Text(f"{label}: {count} ({pct:.1f}%)", color='#95a5a6', size=10),
                    ])
                )

            controls.append(ft.Text("Distribución de Sesiones", color='#3498db', size=12, weight=ft.FontWeight.BOLD))
            controls.append(ft.Container(bgcolor='#0d0d0d', border_radius=8, padding=0, content=pie_chart, height=160))
            controls.append(ft.Container(padding=8, content=ft.Column(controls=legend_items, spacing=4)))
            controls.append(ft.Container(height=12))

            # ──────────────────────────────────────────────────────────────────
            # SESSIONS TABLE
            # ──────────────────────────────────────────────────────────────────
            table_rows = [
                ft.Row(controls=[
                    ft.Text("Operación", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                    ft.Text("%", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                    ft.Text("Capital Inicial", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                    ft.Text("GyP", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                    ft.Text("Capital Final", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                    ft.Text("Acum %", color='#7f8c8d', size=9, weight=ft.FontWeight.BOLD, expand=1),
                ], spacing=4)
            ]

            cumul_pct = 0
            for idx, (ret_pct, bank_start, bank_end, profit_amt, date_str) in enumerate(session_data):
                cumul_pct += ret_pct
                ret_color = '#2ecc71' if ret_pct > 0 else '#e74c3c'
                cumul_color = '#2ecc71' if cumul_pct > 0 else '#e74c3c'
                
                table_rows.append(
                    ft.Row(controls=[
                        ft.Text(date_str or f"Ses {idx+1}", color='#95a5a6', size=9, expand=1),
                        ft.Text(f"{ret_pct:+.2f}%", color=ret_color, size=9, expand=1),
                        ft.Text(_fv(bank_start), color='#95a5a6', size=9, expand=1),
                        ft.Text(f"{profit_amt:+.2f}$", color=ret_color, size=9, expand=1),
                        ft.Text(_fv(bank_end), color='#95a5a6', size=9, expand=1),
                        ft.Text(f"{cumul_pct:+.2f}%", color=cumul_color, size=9, expand=1),
                    ], spacing=4)
                )

            controls.append(ft.Text("Tabla de Sesiones", color='#3498db', size=12, weight=ft.FontWeight.BOLD))
            controls.append(
                ft.Container(
                    bgcolor='#0d0d0d',
                    padding=8,
                    border_radius=6,
                    content=ft.Column(controls=table_rows, spacing=2),
                )
            )

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(expand=True, controls=controls),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # EXPORT ANALYTICS
    # ──────────────────────────────────────────────────────────────────
    def _export_to_csv(self, investment_id: int, inv_name: str, session_data: list,
                       bucket_labels: list, bucket_counts: list, kpis: dict) -> str:
        """Export session data and KPIs to CSV file. Returns file path."""
        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"LinupOS_Export_{inv_name}_{timestamp}.csv"
            filepath = os.path.join(os.path.expanduser("~"), "Downloads", filename)
            
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # KPI Summary section
                writer.writerow(["INVESTMENT SUMMARY"])
                writer.writerow(["Investment", inv_name])
                writer.writerow(["Export Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                
                # KPI rows
                writer.writerow(["KEY PERFORMANCE INDICATORS"])
                writer.writerow(["Metric", "Value"])
                for key, value in kpis.items():
                    writer.writerow([key, value])
                writer.writerow([])
                
                # Distribution buckets
                writer.writerow(["SESSION DISTRIBUTION"])
                writer.writerow(["Range", "Count"])
                for label, count in zip(bucket_labels, bucket_counts):
                    writer.writerow([label, count])
                writer.writerow([])
                
                # Sessions table
                writer.writerow(["SESSION DETAILS"])
                writer.writerow(["Date", "Operation #", "Return %", "Capital Start", "P/L", "Capital End", "Cumulative %"])

                cumul_pct = 0
                for idx, (ret_pct, bank_start, bank_end, profit_amt, date_str) in enumerate(session_data):
                    cumul_pct += ret_pct
                    writer.writerow([
                        date_str or "",
                        idx + 1,
                        f"{ret_pct:.2f}",
                        f"{bank_start:.2f}",
                        f"{profit_amt:.2f}",
                        f"{bank_end:.2f}",
                        f"{cumul_pct:.2f}",
                    ])
            
            return filepath
        except Exception as e:
            return None

    def _export_to_pdf(self, investment_id: int, inv_name: str, session_data: list,
                       bucket_labels: list, bucket_counts: list, kpis: dict) -> tuple:
        """Export session data and KPIs to PDF file. Returns (file_path, error_msg) tuple."""
        try:
            try:
                from reportlab.lib.pagesizes import letter, A4
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
                from reportlab.lib import colors
                from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
                from reportlab.graphics.shapes import Drawing, Line, Rect, String, Circle
                from reportlab.graphics import renderPDF
            except ImportError:
                return None, "reportlab not installed. Run: pip install reportlab>=4.0.0"
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"LinupOS_Export_{inv_name}_{timestamp}.pdf"
            filepath = os.path.join(os.path.expanduser("~"), "Downloads", filename)
            
            # Create PDF
            doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#3498db'),
                spaceAfter=12,
                alignment=TA_CENTER,
                fontName='Helvetica-Bold'
            )
            story.append(Paragraph(f"LinupOS Investment Report: {inv_name}", title_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Export info
            info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, textColor=colors.grey)
            story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", info_style))
            story.append(Spacer(1, 0.3*inch))
            
            # ──────────────────────────────────────────────────────────────────
            # CAPITAL PROGRESSION CHART
            # ──────────────────────────────────────────────────────────────────
            if session_data:
                story.append(Paragraph("Capital Progression", ParagraphStyle('SectionTitle', parent=styles['Heading2'], 
                                                                             fontSize=14, textColor=colors.HexColor('#2ecc71'))))
                
                # Build capital progression points
                start_capital = float(session_data[0][1]) if session_data else 0
                capitals = [start_capital]
                for ret_pct, bank_start, bank_end, profit_amt, date_str in session_data:
                    capitals.append(bank_end)
                
                # Create line chart drawing
                drawing = Drawing(6*inch, 2.8*inch)
                drawing.add(Rect(0, 0, 6*inch, 2.8*inch, fillColor=colors.HexColor('#f5f5f5'), strokeColor=colors.grey))
                
                if len(capitals) > 1:
                    min_capital = min(capitals)
                    max_capital = max(capitals)
                    capital_range = max_capital - min_capital if max_capital != min_capital else 1
                    
                    # Scale factors
                    chart_width = 5.2*inch
                    chart_height = 2*inch
                    x_step = chart_width / (len(capitals) - 1) if len(capitals) > 1 else chart_width
                    
                    # Y-axis labels (positioned outside, left of chart)
                    drawing.add(String(-0.05*inch, 0.1*inch + 0.05*inch, f"${max_capital:.0f}", fontSize=7, textAnchor="end"))  # Top
                    drawing.add(String(-0.05*inch, 0.1*inch + chart_height/2 - 0.05*inch, f"${(min_capital + max_capital)/2:.0f}", fontSize=7, textAnchor="end"))  # Middle
                    drawing.add(String(-0.05*inch, 0.1*inch + chart_height + 0.05*inch, f"${min_capital:.0f}", fontSize=7, textAnchor="end"))  # Bottom
                    
                    # Y-axis label
                    drawing.add(String(-0.15*inch, 0.1*inch + chart_height/2, "Capital ($)", fontSize=8, textAnchor="start"))
                    
                    # Draw grid lines
                    for i in range(len(capitals)):
                        x = 0.4*inch + (i * x_step)
                        drawing.add(Line(x, 0.1*inch, x, 0.1*inch + chart_height, strokeColor=colors.grey, strokeWidth=0.5))
                    
                    # Draw capital line (higher capital values go UP)
                    for i in range(len(capitals) - 1):
                        x1 = 0.4*inch + (i * x_step)
                        y1 = 0.1*inch + ((capitals[i] - min_capital) / capital_range * chart_height)
                        x2 = 0.4*inch + ((i + 1) * x_step)
                        y2 = 0.1*inch + ((capitals[i + 1] - min_capital) / capital_range * chart_height)
                        drawing.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor('#3498db'), strokeWidth=2))
                        drawing.add(Circle(x1, y1, 2, fillColor=colors.HexColor('#3498db')))
                    
                    # X-axis label
                    mid_x = 0.4*inch + chart_width/2
                    drawing.add(String(mid_x, 0.02*inch, "Sessions", fontSize=9, textAnchor="middle"))
                
                story.append(drawing)
                story.append(Spacer(1, 0.2*inch))
            
            # ──────────────────────────────────────────────────────────────────
            # RETURN % BAR CHART
            # ──────────────────────────────────────────────────────────────────
            return_pcts = [r for r, _, _, _, _ in session_data]
            if return_pcts:
                story.append(Paragraph("Return % per Session", ParagraphStyle('SectionTitle', parent=styles['Heading2'], 
                                                                              fontSize=14, textColor=colors.HexColor('#2ecc71'))))
                
                min_ret = min(return_pcts) if return_pcts else 0
                max_ret = max(return_pcts) if return_pcts else 0
                ret_range = max_ret - min_ret
                if ret_range == 0:
                    min_ret, max_ret = -1, 1
                else:
                    padding = ret_range * 0.05
                    min_ret -= padding
                    max_ret += padding
                
                drawing = Drawing(6*inch, 2.5*inch)
                drawing.add(Rect(0, 0, 6*inch, 2.5*inch, fillColor=colors.HexColor('#f5f5f5'), strokeColor=colors.grey))
                
                chart_width = 5.2*inch
                chart_height = 2*inch
                bar_width = chart_width / max(len(return_pcts), 1)
                center_y = 0.35*inch + chart_height / 2
                
                # Y-axis labels (positioned outside, left of chart - INVERTED)
                drawing.add(String(-0.05*inch, 0.35*inch + 0.05*inch, f"{max_ret:.1f}%", fontSize=7, textAnchor="end"))  # Top
                drawing.add(String(-0.05*inch, center_y - 0.05*inch, "0%", fontSize=7, textAnchor="end"))  # Center
                drawing.add(String(-0.05*inch, 0.35*inch + chart_height - 0.05*inch, f"{min_ret:.1f}%", fontSize=7, textAnchor="end"))  # Bottom
                
                # Y-axis label
                drawing.add(String(-0.15*inch, 0.35*inch + chart_height/2, "Return %", fontSize=8, textAnchor="start"))
                
                # Draw center line
                drawing.add(Line(0.4*inch, center_y, 0.4*inch + chart_width, center_y, 
                                strokeColor=colors.grey, strokeWidth=1))
                
                # Draw bars (limit to 20) - positive UP, negative DOWN
                n_bars = min(len(return_pcts), 20)
                for i in range(n_bars):
                    idx = int(i * len(return_pcts) / n_bars)
                    ret = return_pcts[idx]
                    max_abs = max(abs(min_ret), abs(max_ret))
                    bar_height_px = (ret / max_abs) * (chart_height / 2)
                    
                    x = 0.4*inch + (i * bar_width) + (bar_width * 0.4)
                    if ret >= 0:  # Positive (green) goes UP from center
                        y = center_y
                    else:  # Negative (red) goes DOWN from center
                        y = center_y - abs(bar_height_px)
                        bar_height_px = abs(bar_height_px)
                    
                    bar_color = colors.HexColor('#2ecc71') if ret > 0 else colors.HexColor('#e74c3c')
                    drawing.add(Rect(x, y, bar_width * 0.2, bar_height_px, 
                                    fillColor=bar_color, strokeColor=bar_color))
                
                # X-axis label
                mid_x = 0.4*inch + chart_width/2
                drawing.add(String(mid_x, 0.15*inch, "Sessions", fontSize=9, textAnchor="middle"))
                
                story.append(drawing)
                story.append(Spacer(1, 0.2*inch))
            
            # ──────────────────────────────────────────────────────────────────
            # DISTRIBUTION CHART
            # ──────────────────────────────────────────────────────────────────
            if bucket_counts:
                story.append(Paragraph("Session Distribution", ParagraphStyle('SectionTitle', parent=styles['Heading2'], 
                                                                              fontSize=14, textColor=colors.HexColor('#2ecc71'))))
                
                total_sessions = sum(bucket_counts)
                if total_sessions > 0:
                    drawing = Drawing(6*inch, 2.4*inch)
                    drawing.add(Rect(0, 0, 6*inch, 2.4*inch, fillColor=colors.HexColor('#f5f5f5'), strokeColor=colors.grey))
                    
                    bar_height = 0.25*inch
                    chart_width = 5.2*inch
                    center_x = 0.4*inch + chart_width / 2
                    bucket_colors_hex = ['#c0392b', '#e67e22', '#2ecc71', '#27ae60', '#1e8449']
                    
                    # Draw negatives (left) and positives (right)
                    for idx, (label, count, color_hex) in enumerate(zip(bucket_labels, bucket_counts, bucket_colors_hex)):
                        pct = (count / total_sessions * 100) if total_sessions > 0 else 0
                        bar_width_px = (chart_width / 2 - 0.2*inch) * (pct / 100)
                        y = 0.2*inch + idx * (bar_height + 0.05*inch)
                        
                        if idx < 2:  # Negatives (left)
                            x = center_x - bar_width_px
                        else:  # Positives (right)
                            x = center_x
                        
                        drawing.add(Rect(x, y, bar_width_px, bar_height,
                                        fillColor=colors.HexColor(color_hex), strokeColor=colors.grey))
                        
                        # Add percentage label
                        label_x = x + bar_width_px / 2 if idx >= 2 else x - 0.05*inch
                        label_anchor = "middle" if idx >= 2 else "end"
                        drawing.add(String(label_x, y + bar_height/2, f"{pct:.0f}%", fontSize=7, textAnchor=label_anchor))
                    
                    # Center line
                    drawing.add(Line(center_x, 0.15*inch, center_x, 0.15*inch + 5*bar_height + 4*0.05*inch,
                                    strokeColor=colors.grey, strokeWidth=2))
                    
                    # Y-axis label
                    drawing.add(String(-0.15*inch, 0.8*inch, "Distribution", fontSize=8, textAnchor="start"))
                    
                    # X-axis labels
                    drawing.add(String(0.4*inch + (chart_width/4), -0.2*inch, "Negative", fontSize=8, textAnchor="middle"))
                    drawing.add(String(center_x + (chart_width/4), -0.2*inch, "Positive", fontSize=8, textAnchor="middle"))
                    
                    # Legend
                    legend_y_start = 0.2*inch
                    for idx, (label, color_hex) in enumerate(zip(bucket_labels, bucket_colors_hex)):
                        legend_y = legend_y_start + idx * 0.18*inch
                        drawing.add(Rect(5.5*inch, legend_y, 0.15*inch, 0.12*inch, 
                                        fillColor=colors.HexColor(color_hex), strokeColor=colors.grey))
                        drawing.add(String(5.7*inch, legend_y + 0.03*inch, label, fontSize=7))
                    
                    story.append(drawing)
                
                story.append(Spacer(1, 0.3*inch))
            
            # ──────────────────────────────────────────────────────────────────
            # PAGE BREAK BEFORE TABLES
            # ──────────────────────────────────────────────────────────────────
            story.append(PageBreak())
            
            # KPI Summary
            kpi_title = ParagraphStyle('SectionTitle', parent=styles['Heading2'], fontSize=14,
                                      textColor=colors.HexColor('#2ecc71'), spaceAfter=8)
            story.append(Paragraph("Key Performance Indicators", kpi_title))
            
            kpi_data = [["Metric", "Value"]]
            for key, value in kpis.items():
                kpi_data.append([str(key), str(value)])
            
            kpi_table = Table(kpi_data, colWidths=[3*inch, 2*inch])
            kpi_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(kpi_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Distribution
            story.append(Paragraph("Session Distribution", kpi_title))
            dist_data = [["Range", "Count"]]
            for label, count in zip(bucket_labels, bucket_counts):
                dist_data.append([label, str(count)])
            
            dist_table = Table(dist_data, colWidths=[2.5*inch, 1*inch])
            dist_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
            ]))
            story.append(dist_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Session Details
            story.append(Paragraph("Session Details", kpi_title))
            session_data_table = [["Date", "Op#", "Return %", "Start", "P/L", "End", "Cumul %"]]

            cumul_pct = 0
            for idx, (ret_pct, bank_start, bank_end, profit_amt, date_str) in enumerate(session_data):
                cumul_pct += ret_pct
                session_data_table.append([
                    date_str or "",
                    str(idx + 1),
                    f"{ret_pct:.2f}",
                    f"{bank_start:.2f}",
                    f"{profit_amt:.2f}",
                    f"{bank_end:.2f}",
                    f"{cumul_pct:.2f}",
                ])

            session_table = Table(session_data_table, colWidths=[1.0*inch, 0.5*inch, 0.8*inch, 1.0*inch, 0.8*inch, 1.0*inch, 0.9*inch])
            
            # Build table style with conditional row coloring
            table_style = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]
            
            # Add conditional row coloring
            for row_idx in range(1, len(session_data_table)):
                ret_pct = float(session_data_table[row_idx][2])
                if ret_pct > 0:
                    bg_color = colors.HexColor('#d5f4e6')  # Light green
                else:
                    bg_color = colors.HexColor('#fadbd8')  # Light red
                table_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg_color))
            
            session_table.setStyle(TableStyle(table_style))
            story.append(session_table)
            
            doc.build(story)
            return filepath, None
        except Exception as e:
            return None, f"PDF Error: {str(e)}"

    # ──────────────────────────────────────────────────────────────────
    # LOAD INVESTMENT
    # ──────────────────────────────────────────────────────────────────
    def show_load_investments(self, e=None):
        rows = []
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, name, capital, inv_type FROM investments ORDER BY id DESC"
                )
                for inv_id, name, capital, inv_type in cursor.fetchall():
                    cap_txt = (f"{int(round(capital)):,} chips"
                               if (inv_type or 'FIAT') == 'CHIPS'
                               else f"${capital:.2f}")
                    cursor2 = conn.cursor()
                    cursor2.execute(
                        "SELECT mesa_name FROM investment_tables WHERE investment_id=?",
                        (inv_id,)
                    )
                    mesa_names = [r[0] for r in cursor2.fetchall()]
                    wins = losses = 0
                    for mn in mesa_names:
                        cursor2.execute(
                            "SELECT wins, losses FROM table_stats "
                            "WHERE investment_id=? AND mesa=?", (inv_id, mn)
                        )
                        s = cursor2.fetchone()
                        if s:
                            wins   += s[0] or 0
                            losses += s[1] or 0
                    total    = wins + losses
                    eff      = (wins / total * 100) if total > 0 else 0.0
                    color    = '#2ecc71' if (total == 0 or eff >= 50) else '#ff4444'
                    n_tables = len(mesa_names)
                    if total > 0:
                        txt = (f"{name}  |  {cap_txt}"
                               f"  |  {n_tables} tables  |  EFF:{eff:.0f}%")
                    else:
                        txt = f"{name}  |  {cap_txt}  |  {n_tables} tables"

                    def make_loader(iid):
                        def loader(ev):
                            self.show_investment_dashboard(iid)
                        return loader

                    def make_editor(iid):
                        def editor(ev):
                            self.show_edit_investment(iid)
                        return editor

                    rows.append(
                        ft.Row(
                            controls=[
                                ft.ElevatedButton(
                                    txt, on_click=make_loader(inv_id),
                                    expand=True, height=60,
                                    style=ft.ButtonStyle(bgcolor='#222222', color=color),
                                ),
                                ft.ElevatedButton(
                                    "EDIT", on_click=make_editor(inv_id),
                                    width=60, height=60,
                                    style=ft.ButtonStyle(bgcolor='#34495e',
                                                         color=ft.Colors.WHITE),
                                ),
                            ],
                            spacing=4,
                        )
                    )
            except Exception as ex:
                rows.append(ft.Text(f"Error: {ex}", color='#ff4444'))
            finally:
                conn.close()

        if not rows:
            rows.append(ft.Text("No investments saved.", color='#7f8c8d'))

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True,
                content=ft.Column(
                    expand=True,
                    controls=[
                        ft.Container(
                            bgcolor='#2c3e50',
                            padding=ft.padding.only(left=8, right=8, top=36, bottom=8),
                            content=ft.ElevatedButton(
                                "BACK", on_click=self.show_main_menu,
                                style=ft.ButtonStyle(bgcolor='#34495e',
                                                     color=ft.Colors.WHITE),
                            ),
                        ),
                        ft.ListView(controls=rows, expand=True, spacing=4, padding=10),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # EDIT / DELETE INVESTMENT
    # ──────────────────────────────────────────────────────────────────
    def show_edit_investment(self, inv_id):
        inv_name    = ""
        inv_capital = 0.0
        edit_inv_type = 'FIAT'
        tables_data = []  # list of (table_id, mesa_name, init_bank)
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, capital, inv_type FROM investments WHERE id=?", (inv_id,)
                )
                row = cursor.fetchone()
                if row:
                    inv_name, inv_capital, edit_inv_type = row[0], row[1], (row[2] or 'FIAT')
                cursor.execute(
                    "SELECT id, mesa_name, init_bank FROM investment_tables "
                    "WHERE investment_id=? ORDER BY id",
                    (inv_id,)
                )
                tables_data = cursor.fetchall()
            except Exception:
                pass
            finally:
                conn.close()

        name_field = ft.TextField(
            label="Investment Name", value=inv_name,
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=50,
        )
        capital_field = ft.TextField(
            label="Capital (chips)" if edit_inv_type == 'CHIPS' else "Capital ($)",
            value=str(inv_capital),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=50,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        # Table edit rows: (table_id, name_field, bank_field)
        table_rows_ui = []
        table_fields  = []
        for tid, mname, mbank in tables_data:
            nf = ft.TextField(
                value=mname,
                bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
                expand=2,
            )
            bf = ft.TextField(
                value=str(mbank),
                bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
                keyboard_type=ft.KeyboardType.NUMBER, expand=1,
            )
            table_fields.append((tid, nf, bf))
            table_rows_ui.append(ft.Row(controls=[nf, bf], spacing=6))

        def on_save(ev):
            conn2 = self._get_conn()
            if not conn2:
                return
            try:
                new_name    = name_field.value.strip().upper() or inv_name
                new_capital = float(capital_field.value or inv_capital)
                conn2.execute(
                    "UPDATE investments SET name=?, capital=? WHERE id=?",
                    (new_name, round(new_capital, 2), inv_id)
                )
                for tid, nf, bf in table_fields:
                    t_name = nf.value.strip().upper()
                    try:
                        t_bank = float(bf.value)
                    except Exception:
                        t_bank = 0.0
                    conn2.execute(
                        "UPDATE investment_tables SET mesa_name=?, init_bank=? WHERE id=?",
                        (t_name, round(t_bank, 2), tid)
                    )
                conn2.commit()
            except Exception:
                pass
            finally:
                conn2.close()
            self.show_load_investments()

        def on_delete(ev):
            dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

            def confirm_delete(ev2):
                dlg.open = False
                dlg.update()
                conn3 = self._get_conn()
                if conn3:
                    try:
                        conn3.execute(
                            "DELETE FROM investment_tables WHERE investment_id=?", (inv_id,)
                        )
                        conn3.execute(
                            "DELETE FROM investments WHERE id=?", (inv_id,)
                        )
                        conn3.commit()
                    except Exception:
                        pass
                    finally:
                        conn3.close()
                self.show_load_investments()

            def cancel_delete(ev2):
                dlg.open = False
                dlg.update()

            dlg.title = ft.Text("DELETE INVESTMENT", color='#ff4444',
                                size=16, weight=ft.FontWeight.BOLD,
                                text_align=ft.TextAlign.CENTER)
            dlg.content = ft.Text(
                f"Delete '{inv_name}'?\nThis cannot be undone.",
                color=ft.Colors.WHITE, size=14,
                text_align=ft.TextAlign.CENTER,
            )
            dlg.actions = [
                ft.ElevatedButton(
                    "CANCEL", on_click=cancel_delete, expand=1,
                    style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE),
                ),
                ft.ElevatedButton(
                    "DELETE", on_click=confirm_delete, expand=1,
                    style=ft.ButtonStyle(bgcolor='#ff4444', color=ft.Colors.WHITE),
                ),
            ]
            dlg.actions_alignment = ft.MainAxisAlignment.CENTER
            self.page.show_dialog(dlg)

        table_section = []
        if table_rows_ui:
            table_section = [
                ft.Container(height=12),
                ft.Text("TABLES", color='#7f8c8d', size=12, weight=ft.FontWeight.BOLD),
                ft.Row(controls=[
                    ft.Text("TABLE NAME", color='#7f8c8d', size=11, expand=2),
                    ft.Text("BANK", color='#7f8c8d', size=11, expand=1),
                ]),
            ] + table_rows_ui

        controls = [
            ft.ElevatedButton(
                "BACK", on_click=self.show_load_investments,
                style=ft.ButtonStyle(bgcolor='#34495e', color=ft.Colors.WHITE),
            ),
            ft.Container(height=12),
            ft.Text("EDIT INVESTMENT", color='#3498db', size=18,
                    weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            name_field,
            ft.Container(height=8),
            capital_field,
        ] + table_section + [
            ft.Container(height=20),
            ft.ElevatedButton(
                "SAVE CHANGES", on_click=on_save,
                height=60, expand=True,
                style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
            ),
            ft.Container(height=10),
            ft.ElevatedButton(
                "DELETE INVESTMENT", on_click=on_delete,
                height=50, expand=True,
                style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
            ),
        ]

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(expand=True, controls=controls),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # SESSION SETUP FORM
    # ──────────────────────────────────────────────────────────────────
    def render_setup_form(self, is_continue: bool):
        self.table_input = ft.TextField(
            value=str(self.nombre_mesa),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            read_only=True,
        )
        sug_bank      = self.banca_actual
        sug_max_loss  = getattr(self, 'last_max_loss', 2.0)
        # Per-table base chip: remembered from the last setup on THIS table,
        # falling back to the last-used chip in memory, then 0.1.
        sug_base_chip = self._load_base_chip(
            getattr(self, 'current_investment_id', 0), self.nombre_mesa,
            default=getattr(self, 'last_base_chip', 0.1))
        capital       = getattr(self, 'inv_capital', 0.0)
        # For CHIPS investments the bank, budget and capital are all in CHIPS,
        # so the percentages stay in one unit. We show the USD equivalent in
        # parenthesis using the loaded table's USD-per-chip rate.
        chips_mode    = (getattr(self, 'inv_type', 'FIAT') == 'CHIPS')
        usd_per_chip  = getattr(self, 'chip_usd_rate', 0.0)

        def _amt(v):
            """Budget amount: chips with USD in parens (CHIPS) or plain $ (FIAT)."""
            if chips_mode:
                return f"{v:.2f} chips (${v * usd_per_chip:.2f})"
            return f"${v:.2f}"

        def _round_up_chip(val):
            if val <= 0:
                return 0.0
            if val < 10:
                return math.floor(round(val * 10, 8)) / 10
            return float(math.floor(val / 10) * 10)

        # Initial chip denominations: budget-derived, floored to base_chip
        _sug_budget     = sug_bank * sug_max_loss / 100
        _sug_chip_denom = max(_round_up_chip(_sug_budget / 108), sug_base_chip)
        sug_fout        = max(_round_up_chip(_sug_budget / 18), sug_base_chip)

        def _f(val):
            try:
                return float(val)
            except Exception:
                return 0.0

        def _chip_label_text_prog(base_chip, bank, max_loss_pct):
            """CHIP IN label: progression breakdown then percentages."""
            try:
                b = _f(base_chip)
                total_1x = b * 18 * 1
                total_2x = b * 18 * 2
                total_3x = b * 18 * 3
                total    = total_1x + total_2x + total_3x
                pct_bank = (total / bank * 100) if bank > 0 else 0
                pct_cap  = (total / capital * 100) if capital > 0 else 0
                return (f"1x({total_1x:.2f}) + 2x({total_2x:.2f}) + 3x({total_3x:.2f})"
                        f" = {_amt(total)} · {pct_bank:.1f}% bank · {pct_cap:.1f}% capital")
            except Exception:
                return ""

        def _chip_label_text(chip_val, bank, max_loss_pct):
            """CHIP OUT label: 2 chips at 1x·3x·5x breakdown then percentages."""
            try:
                total_1x = chip_val * 2 * 1
                total_3x = chip_val * 2 * 3
                total_5x = chip_val * 2 * 5
                total    = total_1x + total_3x + total_5x   # chip_val × 18
                pct_bank = (total / bank * 100) if bank > 0 else 0
                pct_cap  = (total / capital * 100) if capital > 0 else 0
                return (f"1x({total_1x:.2f}) + 3x({total_3x:.2f}) + 5x({total_5x:.2f})"
                        f" = {_amt(total)} · {pct_bank:.1f}% bank · {pct_cap:.1f}% capital")
            except Exception:
                return ""

        self.fin_label  = ft.Text(
            _chip_label_text_prog(_sug_chip_denom, sug_bank, sug_max_loss),
            color='#27ae60',
        )
        self.fout_label = ft.Text(
            _chip_label_text(sug_fout, sug_bank, sug_max_loss),
            color='#f1c40f',
        )

        def _max_loss_info(bank, max_loss_pct):
            try:
                loss_amt = bank * max_loss_pct / 100
                cap_pct  = (loss_amt / capital * 100) if capital > 0 else 0
                return f"MAX LOSS %:  (= {_amt(loss_amt)} · {cap_pct:.1f}% of capital)"
            except Exception:
                return "MAX LOSS %:"

        def _refresh_labels(bank, base_chip_val, fout_val):
            ml = _f(self.max_loss_input.value)
            self.max_loss_label.value = _max_loss_info(bank, ml)
            self.fin_label.value  = _chip_label_text_prog(base_chip_val, bank, ml)
            self.fout_label.value = _chip_label_text(fout_val, bank, ml)
            try:
                self.max_loss_label.update()
                self.fin_label.update()
                self.fout_label.update()
            except Exception:
                pass

        _busy = [False]   # reentrancy guard for cross-field sync

        def _snap_to_base(val, base):
            """Largest multiple of base <= val, but at least one base chip."""
            if base <= 0:
                return max(val, 0.0)
            n = math.floor(round(val / base, 8))
            return max(n, 1) * base

        def _fmt(v):
            v = round(float(v), 4)
            return str(int(v)) if v == int(v) else f"{v:g}"

        def _fmt_pct(v):
            v = round(float(v), 2)
            return str(int(v)) if v == int(v) else f"{v:g}"

        # The four fields share one MAX-LOSS budget: B = bank * maxloss/100.
        # CHIP IN total = chip × 90, CHIP OUT total = chip × 18 — each equal to B.
        # Editing any field re-derives the others; chips stay multiples of the
        # base chip and are floored so the budget never exceeds MAX LOSS.
        def _recalc_fin(e=None):
            """Bank / Base Chip / Max Loss changed → re-derive both chips from budget."""
            if _busy[0]:
                return
            _busy[0] = True
            try:
                bk   = _f(self.banca_input.value)
                base = _f(self.fin_base_input.value)
                ml   = _f(self.max_loss_input.value)
                budget = bk * max(ml, 0) / 100
                if bk > 0 and budget > 0:
                    cin  = _snap_to_base(budget / 108, base)  # CHIP IN: 108 chips
                    cout = _snap_to_base(budget / 18, base)   # CHIP OUT: 18 chips
                else:
                    cin = cout = max(base, 0.0)
                self.fin_input.value  = _fmt(cin)
                self.fout_input.value = _fmt(cout)
                self.fin_input.update()
                self.fout_input.update()
                _refresh_labels(bk, cin, cout)
            except Exception:
                pass
            finally:
                _busy[0] = False

        def _sync_from_chip(chip_val, chips_per_total):
            """A chip was edited → back-solve the shared budget, push the implied
            MAX LOSS %, and return the re-derived chips. chips_per_total is
            108 (CHIP IN) or 18 (CHIP OUT)."""
            bk   = _f(self.banca_input.value)
            base = _f(self.fin_base_input.value)
            budget = max(chip_val, 0.0) * chips_per_total
            ml   = (budget / bk * 100) if bk > 0 else 0.0
            cin  = _snap_to_base(budget / 108, base) if budget > 0 else max(base, 0.0)
            cout = _snap_to_base(budget / 18, base) if budget > 0 else max(base, 0.0)
            self.max_loss_input.value = _fmt_pct(ml)
            self.max_loss_input.update()
            return bk, cin, cout

        def _on_chip_in_change(e=None):
            """CHIP IN typed → live-update MAX LOSS + CHIP OUT (leave CHIP IN as typed)."""
            if _busy[0]:
                return
            _busy[0] = True
            try:
                bk, _cin, cout = _sync_from_chip(_f(self.fin_input.value), 108)
                self.fout_input.value = _fmt(cout)
                self.fout_input.update()
                _refresh_labels(bk, _f(self.fin_input.value), cout)
            except Exception:
                pass
            finally:
                _busy[0] = False

        def _on_chip_out_change(e=None):
            """CHIP OUT typed → live-update MAX LOSS + CHIP IN (leave CHIP OUT as typed)."""
            if _busy[0]:
                return
            _busy[0] = True
            try:
                bk, cin, _cout = _sync_from_chip(_f(self.fout_input.value), 18)
                self.fin_input.value = _fmt(cin)
                self.fin_input.update()
                _refresh_labels(bk, cin, _f(self.fout_input.value))
            except Exception:
                pass
            finally:
                _busy[0] = False

        def _on_chip_in_blur(e=None):
            """Snap CHIP IN to a base-chip multiple on blur, then re-sync."""
            if _busy[0]:
                return
            base = _f(self.fin_base_input.value)
            self.fin_input.value = _fmt(_snap_to_base(_f(self.fin_input.value), base))
            self.fin_input.update()
            _on_chip_in_change()

        def _on_chip_out_blur(e=None):
            """Snap CHIP OUT to a base-chip multiple on blur, then re-sync."""
            if _busy[0]:
                return
            base = _f(self.fin_base_input.value)
            self.fout_input.value = _fmt(_snap_to_base(_f(self.fout_input.value), base))
            self.fout_input.update()
            _on_chip_out_change()

        def _on_bank_change(e):
            try:
                new_bank = float(self.banca_input.value or 0)
                if new_bank > 0:
                    self.banca_actual  = new_bank
                    self.banca_inicial = new_bank
            except ValueError:
                pass
            _recalc_fin()

        self.max_loss_label = ft.Text(
            _max_loss_info(sug_bank, sug_max_loss),
            color='#e74c3c',
        )
        self.max_loss_input = ft.TextField(
            value=str(sug_max_loss),
            bgcolor='#f1948a', color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: _recalc_fin(),
        )

        # CHIP IN Base Chip control
        self.fin_base_input = ft.TextField(
            value=str(sug_base_chip),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=40,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=_recalc_fin,
        )

        self.fin_input = ft.TextField(
            value=str(_sug_chip_denom),
            bgcolor='#82e0aa', color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=_on_chip_in_change,
            on_blur=_on_chip_in_blur,
        )
        self.fout_input = ft.TextField(
            value=str(sug_fout),
            bgcolor='#f7dc6f', color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=_on_chip_out_change,
            on_blur=_on_chip_out_blur,
        )
        self.banca_input = ft.TextField(
            value=str(sug_bank),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=_on_bank_change,
        )
        self.free_spin_mode = False
        _fs_lbl = ft.Text("FREE SPIN: OFF", color=ft.Colors.WHITE,
                          weight=ft.FontWeight.BOLD)
        _fs_ref = [None]   # forward ref so toggle can update the button

        def _toggle_free_spin(e):
            self.free_spin_mode = not self.free_spin_mode
            on = self.free_spin_mode
            _fs_lbl.value       = "FREE SPIN: ON" if on else "FREE SPIN: OFF"
            _fs_ref[0].style    = ft.ButtonStyle(
                bgcolor='#e67e22' if on else '#555555',
                color=ft.Colors.WHITE,
            )
            _fs_lbl.update()
            _fs_ref[0].update()

        free_spin_btn = ft.ElevatedButton(
            content=_fs_lbl,
            height=50, expand=True,
            style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE),
            on_click=_toggle_free_spin,
        )
        _fs_ref[0] = free_spin_btn

        self.live_table_mode = False
        _lt_lbl = ft.Text("LIVE TABLE: OFF", color=ft.Colors.WHITE,
                          weight=ft.FontWeight.BOLD)
        _lt_ref = [None]

        def _toggle_live_table(e):
            self.live_table_mode = not self.live_table_mode
            on = self.live_table_mode
            _lt_lbl.value    = "LIVE TABLE: ON" if on else "LIVE TABLE: OFF"
            _lt_ref[0].style = ft.ButtonStyle(
                bgcolor='#3498db' if on else '#555555',
                color=ft.Colors.WHITE,
            )
            if on and hasattr(self, 'cb_basic'):
                self.cb_basic.value = True
                self.cb_basic.update()
            _lt_lbl.update()
            _lt_ref[0].update()

        live_table_btn = ft.ElevatedButton(
            content=_lt_lbl,
            height=50, expand=True,
            style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE),
            on_click=_toggle_live_table,
        )
        _lt_ref[0] = live_table_btn

        vc = self.visible_cats
        self.cb_basic  = ft.Checkbox(label="Basic  (R N P I B A)", value=vc['basic'],
                                     fill_color='#555555', check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))
        self.cb_cols   = ft.Checkbox(label="Columns  (34 35 36)",  value=vc['cols'],
                                     fill_color=C_COL, check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))
        self.cb_docs   = ft.Checkbox(label="Dozens  (1a 2a 3a)",   value=vc['docs'],
                                     fill_color=C_DOC, check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))
        self.cb_secs   = ft.Checkbox(label="Sectors  (Z0 ZG ZP H)", value=vc['secs'],
                                     fill_color=C_SEC, check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))
        self.cb_thirds = ft.Checkbox(label="Thirds  (T1 T2 T3)",   value=vc['thirds'],
                                     fill_color=C_SET, check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))
        self.cb_wave   = ft.Checkbox(label="Wave  (W1 Lip · W2 Curls · W3 Through)",
                                     value=vc['wave'],
                                     fill_color=C_WAV, check_color=ft.Colors.WHITE,
                                     label_style=ft.TextStyle(color=ft.Colors.WHITE, size=13))

        btn_txt = "RESUME TABLE" if is_continue else "OPEN TABLE"
        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(
                    expand=True,
                    controls=[
                        ft.ElevatedButton(
                            "CANCEL", on_click=self._go_home,
                            style=ft.ButtonStyle(bgcolor='#c0392b',
                                                 color=ft.Colors.WHITE),
                        ),
                        ft.Container(height=10),
                        ft.Text("TABLE:", color=ft.Colors.WHITE),
                        self.table_input,
                        ft.Text("CAPITAL:", color=ft.Colors.WHITE),
                        ft.TextField(
                            value=(f"{capital:,.0f} chips (${capital * usd_per_chip:,.2f})"
                                   if chips_mode else f"${capital:.2f}"),
                            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
                            read_only=True,
                        ),
                        ft.Text("BANK:", color=ft.Colors.WHITE),
                        self.banca_input,
                        ft.Text("Base Chip:", color='#7f8c8d', size=11),
                        self.fin_base_input,
                        self.max_loss_label,
                        self.max_loss_input,
                        ft.Text("CHIP IN — investment of 18 chips (1x · 2x · 3x)", color='#27ae60', size=12,
                                weight=ft.FontWeight.BOLD),
                        self.fin_label,
                        self.fin_input,
                        ft.Text("CHIP OUT — 2 chips · progression (1x · 3x · 5x)", color='#f1c40f', size=12,
                                weight=ft.FontWeight.BOLD),
                        self.fout_label,
                        self.fout_input,
                        ft.Container(height=10),
                        free_spin_btn,
                        ft.Container(height=6),
                        live_table_btn,
                        ft.Container(height=10),
                        ft.Text("TABLE COLUMNS:", color='#7f8c8d', size=12,
                                weight=ft.FontWeight.BOLD),
                        self.cb_basic,
                        self.cb_cols,
                        self.cb_docs,
                        self.cb_secs,
                        self.cb_thirds,
                        self.cb_wave,
                        ft.Container(height=6),
                        ft.ElevatedButton(
                            btn_txt, on_click=self.iniciar_ciclo,
                            height=70, expand=True,
                            style=ft.ButtonStyle(bgcolor='#27ae60',
                                                 color=ft.Colors.WHITE),
                        ),
                    ],
                ),
            )
        )

    # ──────────────────────────────────────────────────────────────────
    # START SESSION
    # ──────────────────────────────────────────────────────────────────
    def iniciar_ciclo(self, e=None):
        try:
            # Fresh id for THIS play session so the bet log can separate sessions
            # (session_id is only assigned later, when the session is saved).
            try:
                self.play_session_id = datetime.now().strftime('%Y%m%d-%H%M%S')
            except Exception:
                self.play_session_id = str(len(getattr(self, 'history_nums', [])))
            self.nombre_mesa   = str(self.table_input.value).upper() or "TABLE 1"
            self.banca_inicial = float(self.banca_input.value or 100)
            self.banca_actual  = self.banca_inicial
            
            # CHIP IN is calculated from progression
            self.val_fin       = float(self.fin_input.value)  if self.fin_input.value  else 0.5
            self.val_fout      = float(self.fout_input.value) if self.fout_input.value else 0.5
            self.last_max_loss = float(self.max_loss_input.value) if self.max_loss_input.value else 2.0
            self.last_base_chip = float(self.fin_base_input.value) if self.fin_base_input.value else 0.1
            # Remember this base chip for THIS table specifically
            self._save_base_chip(getattr(self, 'current_investment_id', 0),
                                 self.nombre_mesa, self.last_base_chip)
        except Exception:
            pass
        # Read column visibility checkboxes
        try:
            self.visible_cats = {
                'basic':  bool(self.cb_basic.value),
                'cols':   bool(self.cb_cols.value),
                'docs':   bool(self.cb_docs.value),
                'secs':   bool(self.cb_secs.value),
                'thirds': bool(self.cb_thirds.value),
                'wave':   bool(self.cb_wave.value),
            }
        except Exception:
            pass
        self.show_game_screen()

    # ─────────────────────────────────────────────────────────────────
    # STOP LOSS — triggers at 45% loss of initial bank
    # ─────────────────────────────────────────────────────────────────
    def _check_stop_loss(self):
        if self.stop_loss_triggered:
            return
        if self.banca_inicial <= 0:
            return
        loss_pct = (self.banca_inicial - self.banca_actual) / self.banca_inicial
        if loss_pct < 0.45:
            return

        self.stop_loss_triggered = True
        self.activa = False

        profit = round(self.banca_actual - self.banca_inicial, 2)
        pl_pct = (profit / self.banca_inicial * 100) if self.banca_inicial != 0 else 0

        ok, err_msg    = self._guardar_sesion()
        self._update_table_stats(False)
        guardado_txt   = "Saved to history" if ok else f"Error: {err_msg}"
        guardado_color = '#2ecc71' if ok else '#ff4444'

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def cerrar(ev):
            dlg.open = False
            dlg.update()
            self._go_home()

        dlg.title = ft.Text(
            "STOP LOSS",
            color='#ff4444', size=18, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.content = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Divider(color='#444444'),
                ft.Text("45% loss limit reached.", color='#ff4444',
                        size=13, text_align=ft.TextAlign.CENTER),
                ft.Container(height=6),
                ft.Text(f"Initial bank:  {self._fmt_bank(self.banca_inicial)}",
                        color=ft.Colors.WHITE, size=14),
                ft.Text(f"Final bank:    {self._fmt_bank(self.banca_actual)}",
                        color=ft.Colors.WHITE, size=14),
                ft.Container(height=8),
                ft.Text(
                    f"P/L:  {self._fmt_bank(profit)}   ({pl_pct:.1f}%)",
                    color='#ff4444', size=20, weight=ft.FontWeight.BOLD,
                ),
                ft.Container(height=10),
                ft.Text(guardado_txt, color=guardado_color, size=13),
            ],
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("CLOSE TABLE", size=15, weight=ft.FontWeight.BOLD),
                on_click=cerrar,
                expand=True,
                style=ft.ButtonStyle(bgcolor='#ff4444', color=ft.Colors.WHITE),
            )
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)

    # ─────────────────────────────────────────────────────────────────
    # GOAL ACHIEVED — profit reached the MAX LOSS target (turned positive)
    # ─────────────────────────────────────────────────────────────────
    def _check_goal_achieved(self):
        if self.goal_achieved_shown or self.stop_loss_triggered:
            return
        if self.banca_inicial <= 0:
            return
        profit_pct = (self.banca_actual - self.banca_inicial) / self.banca_inicial
        goal_pct = getattr(self, 'last_max_loss', 2.0) / 100
        if profit_pct < goal_pct:
            return

        self.goal_achieved_shown = True

        profit = round(self.banca_actual - self.banca_inicial, 2)
        pl_pct = profit_pct * 100

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def exit_and_save(ev):
            dlg.open = False
            dlg.update()
            self.finalizar_sesion()

        def keep_playing(ev):
            dlg.open = False
            dlg.update()

        dlg.title = ft.Text(
            "CONGRATULATIONS",
            color='#2ecc71', size=18, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.content = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Divider(color='#444444'),
                ft.Text("Goal achieved!", color='#2ecc71',
                        size=15, weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER),
                ft.Container(height=6),
                ft.Text(f"Target:  +{goal_pct*100:.1f}%",
                        color=ft.Colors.WHITE, size=14),
                ft.Text(f"Current: +{pl_pct:.1f}%",
                        color='#2ecc71', size=14, weight=ft.FontWeight.BOLD),
                ft.Container(height=4),
                ft.Text(f"Profit:  {self._fmt_bank(profit)}",
                        color='#2ecc71', size=20, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                ft.Text("It's recommended to exit while ahead.",
                        color='#f39c12', size=12, italic=True,
                        text_align=ft.TextAlign.CENTER),
            ],
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("EXIT & SAVE", size=14, weight=ft.FontWeight.BOLD),
                on_click=exit_and_save, expand=1,
                style=ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.WHITE),
            ),
            ft.ElevatedButton(
                content=ft.Text("CONTINUE", size=14, weight=ft.FontWeight.BOLD),
                on_click=keep_playing, expand=1,
                style=ft.ButtonStyle(bgcolor='#f39c12', color=ft.Colors.WHITE),
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)

    # ─────────────────────────────────────────────────────────────────
    # FINALIZE SESSION
    # ─────────────────────────────────────────────────────────────────
    def _log_draw_sequence(self) -> bool:
        """Append this session's raw draw sequence to croupier_log.txt (next to
        the DB), in the '@ dealer' format used by croupier_data.txt, so every
        session we play is captured for the rhythm/pattern dataset.
        Best-effort — never blocks finishing a session."""
        try:
            nums = getattr(self, 'history_nums', [])
            if not self.db_path or len(nums) < 10:
                return False
            log_path = os.path.join(os.path.dirname(self.db_path), "croupier_log.txt")
            label = (str(self.nombre_mesa).strip() or "session")
            try:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            except Exception:
                stamp = ""
            line = " ".join(str(int(n)) for n in nums)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n@ {label} {stamp}\n{line}\n")
            return True
        except Exception:
            return False

    def finalizar_sesion(self, e=None):
        profit   = round(self.banca_actual - self.banca_inicial, 2)
        pl_pct   = (profit / self.banca_inicial * 100) if self.banca_inicial != 0 else 0
        positivo = profit >= 0
        color    = '#2ecc71' if positivo else '#ff4444'
        signo    = "+" if positivo else ""

        ok, err_msg    = self._guardar_sesion()
        self._update_table_stats(profit >= 0)
        draws_logged   = self._log_draw_sequence()
        guardado_txt   = "Saved to history" if ok else f"Error: {err_msg}"
        guardado_color = '#2ecc71' if ok else '#ff4444'

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def saltar(ev):
            dlg.open = False
            dlg.update()
            self._go_home()

        def guardar(ev):
            self._save_compound_session()
            dlg.open = False
            dlg.update()
            self._go_home()

        dlg.title = ft.Text(
            f"SUMMARY  {self.nombre_mesa}",
            color='#3498db', size=16, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.content = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Divider(color='#444444'),
                ft.Text(f"Initial bank:  {self._fmt_bank(self.banca_inicial)}",
                        color=ft.Colors.WHITE, size=14),
                ft.Text(f"Final bank:    {self._fmt_bank(self.banca_actual)}",
                        color=ft.Colors.WHITE, size=14),
                ft.Container(height=8),
                ft.Text(
                    f"P/L:  {signo}{self._fmt_bank(profit)}   ({signo}{pl_pct:.1f}%)",
                    color=color, size=20, weight=ft.FontWeight.BOLD,
                ),
                ft.Container(height=10),
                ft.Text(guardado_txt, color=guardado_color, size=13),
                ft.Text(f"{len(self.history_nums)} draws logged for AI dataset"
                        if draws_logged else "",
                        color='#9b59b6', size=11),
            ],
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("SKIP", size=14, weight=ft.FontWeight.BOLD),
                on_click=saltar, expand=1,
                style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE),
            ),
            ft.ElevatedButton(
                content=ft.Text("SAVE", size=14, weight=ft.FontWeight.BOLD),
                on_click=guardar, expand=1,
                style=ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.WHITE),
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)

    # ──────────────────────────────────────────────────────────────────
    # GAME SCREEN
    # ──────────────────────────────────────────────────────────────────
    def show_game_screen(self):
        self._on_game_screen = True

        # ── Investment bar (shown only when inside an investment) ───
        inv_bar_controls = []
        if self.current_investment_id and self.inv_name:
            init_pl = self.inv_other_pl + (self.banca_actual - self.banca_inicial)
            self.lbl_inv_pl = ft.Text(
                f"P/L: {init_pl:+.2f}",
                color='#2ecc71' if init_pl >= 0 else '#ff4444',
                weight=ft.FontWeight.BOLD, size=16,
                text_align=ft.TextAlign.RIGHT,
            )
            inv_bar_controls = [ft.Container(
                bgcolor='#0a0a0a',
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                content=ft.Row(controls=[
                    ft.Text(
                        self.inv_name,
                        color='#3498db', size=14, weight=ft.FontWeight.BOLD,
                        expand=True,
                    ),
                    self.lbl_inv_pl,
                ]),
            )]
        else:
            self.lbl_inv_pl = None

        self.lbl_bank = ft.Text(
            f"{self.nombre_mesa}  |  {self._fmt_bank(self.banca_actual)}",
            color='#2ecc71', weight=ft.FontWeight.BOLD, size=13, expand=True,
        )
        self.lbl_inv = ft.Text(
            "BET: $0.00",
            color='#f1c40f', weight=ft.FontWeight.BOLD, size=11, expand=True,
            text_align=ft.TextAlign.CENTER,
            no_wrap=True,
        )
        self.lbl_pl = ft.Text(
            "P/L: 0.0%",
            color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD, size=13, expand=True,
            text_align=ft.TextAlign.RIGHT,
        )
        stats_bar = ft.Container(
            bgcolor='#1e1e1e', padding=5,
            content=ft.Row(controls=[self.lbl_bank, self.lbl_inv, self.lbl_pl]),
        )

        # ── AI combination-coach bar ──────────────────────────────────────
        self.lbl_ai_info = ft.Text(
            self._get_ai_info_display(),
            color='#f1c40f', weight=ft.FontWeight.BOLD, size=16,
            text_align=ft.TextAlign.CENTER, no_wrap=False,
        )
        ai_bar = ft.Container(
            bgcolor='#2a2a3e', padding=4, content=self.lbl_ai_info,
        ) if getattr(self, 'ai_ok', False) else None

        # ── Progression ON/OFF + fixed multiplier bar ─────────────────────
        self.prog_on     = True
        self.fixed_multi = 1

        _PROG_ON_COLOR    = '#2ecc71'     # green
        _PROG_OFF_COLOR   = '#e67e22'     # orange
        _SNIPER_ON_COLOR  = '#2ecc71'     # green (harmonized with prog ON)
        _SNIPER_OFF_COLOR = '#e67e22'     # orange (harmonized with prog OFF)
        _MULTI_ACT        = '#f39c12'
        _MULTI_INACT      = '#3a3a3a'

        _prog_lbl   = ft.Text("PROG: ON", color=ft.Colors.WHITE,
                               weight=ft.FontWeight.BOLD, size=11)
        _sniper_lbl = ft.Text("SNIPER: ON", color=ft.Colors.WHITE,
                               weight=ft.FontWeight.BOLD, size=11)
        _prog_ref   = [None]
        _sniper_ref = [None]
        _multi_refs: dict = {}   # multiplier int → button ref

        def _refresh_prog_ui():
            on = self.prog_on
            m  = self.fixed_multi
            _prog_lbl.value = "PROG: ON" if on else "PROG: OFF"
            _prog_ref[0].style = ft.ButtonStyle(
                bgcolor=_PROG_ON_COLOR if on else _PROG_OFF_COLOR,
                color=ft.Colors.WHITE,
            )
            _prog_ref[0].update()
            _prog_lbl.update()
            for mx, btn in _multi_refs.items():
                btn.visible = not on
                btn.style = ft.ButtonStyle(
                    bgcolor=_MULTI_ACT if mx == m else _MULTI_INACT,
                    color=ft.Colors.WHITE,
                )
                btn.update()
            self.update_inv_label()
            if self.lbl_inv:
                self.lbl_inv.update()

        def _toggle_prog(_e):
            self.prog_on = not self.prog_on
            if self.prog_on:   # turning ON = fresh start from the beginning
                self.idx_fibo_out         = 0
                self.idx_fibo_in          = 0
                self.nivel_martingala_out = 0
                self.nivel_martingala_in  = 0
            _refresh_prog_ui()

        def _toggle_sniper(_e):
            self.sniper_mode = not self.sniper_mode
            _sniper_lbl.value = "SNIPER: ON" if self.sniper_mode else "SNIPER: OFF"
            _sniper_ref[0].style = ft.ButtonStyle(
                bgcolor=_SNIPER_ON_COLOR if self.sniper_mode else _SNIPER_OFF_COLOR,
                color=ft.Colors.WHITE,
            )
            _sniper_ref[0].update()
            _sniper_lbl.update()
            self._refresh_mixer_colors()
            self.update_inv_label()
            if self.lbl_inv:
                self.lbl_inv.update()

        def _make_multi_handler(mx):
            def handler(_e):
                self.fixed_multi = mx
                _refresh_prog_ui()
            return handler

        _prog_btn = ft.ElevatedButton(
            content=_prog_lbl, height=30, expand=2,
            style=ft.ButtonStyle(bgcolor=_PROG_ON_COLOR, color=ft.Colors.WHITE),
            on_click=_toggle_prog,
        )
        _prog_ref[0] = _prog_btn

        _sniper_btn = ft.ElevatedButton(
            content=_sniper_lbl, height=30, expand=2,
            style=ft.ButtonStyle(bgcolor=_SNIPER_ON_COLOR, color=ft.Colors.WHITE),
            on_click=_toggle_sniper,
        )
        _sniper_ref[0] = _sniper_btn

        _multi_btn_list = []
        for _mx in (1, 2, 3, 4, 5):
            _mb = ft.ElevatedButton(
                content=ft.Text(f"{_mx}x", size=10,
                                weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                height=30, expand=1, visible=False,
                style=ft.ButtonStyle(
                    bgcolor=_MULTI_ACT if _mx == 1 else _MULTI_INACT,
                    color=ft.Colors.WHITE,
                ),
                on_click=_make_multi_handler(_mx),
            )
            _multi_refs[_mx] = _mb
            _multi_btn_list.append(_mb)

        prog_bar = ft.Container(
            bgcolor='#161616', padding=ft.padding.symmetric(horizontal=4, vertical=3),
            content=ft.Row(controls=[_prog_btn, _sniper_btn] + _multi_btn_list, spacing=3),
        )
        # ──────────────────────────────────────────────────────────────────

        self.sug_row = ft.Row(
            controls=[
                ft.ElevatedButton(
                    content=self._txt("---", size=12),
                    expand=True, height=35,
                    style=ft.ButtonStyle(bgcolor='#34495e', color=ft.Colors.WHITE),
                )
                for _ in range(4)
            ],
            spacing=2,
        )
        sug_bar = ft.Container(
            bgcolor='#2c3e50', padding=4, height=50,
            content=self.sug_row,
        )

        # ── Live Table filter panel (only when live_table_mode is ON) ──────
        self.live_filter = None
        rb_bar = None
        if self.live_table_mode:
            _INACTIVE = '#3a3a3a'
            _ACTIVE_COLOR = {
                'R': '#c0392b', 'B': '#222222',
                '1-18': '#555577', 'Even': '#446644',
                'Odd': '#664444', '19-36': '#445566',
            }
            # All buttons stored as (opt, btn) pairs so R/B can appear in both rows
            _all_filter_btns: list = []   # list of (opt, btn)

            def _apply_filter(new_f):
                self.live_filter = new_f
                # Re-map any already-selected live groups to the new filter variant
                updated = []
                for g in self.grupos_activos:
                    base = self._to_display_name(g)
                    if base in ('1a', '2a', '3a'):
                        updated.append(f'{base}{_DOC_SFX.get(new_f, "_L")}')
                    elif base in ('34', '35', '36'):
                        sfx = _COL_SFX.get(new_f, '')
                        updated.append(f'{base}{sfx}' if sfx else base)
                    else:
                        updated.append(g)
                self.grupos_activos = updated
                for opt, btn in _all_filter_btns:
                    btn.style = ft.ButtonStyle(
                        bgcolor=_ACTIVE_COLOR[opt] if opt == new_f else _INACTIVE,
                        color=ft.Colors.WHITE,
                    )
                    btn.update()
                self._refresh_mixer_colors()
                self.update_inv_label()
                if self.lbl_inv:
                    self.lbl_inv.update()
                self.actualizar_sugerencias()

            def _filter_btn(opt, label, height=34, size=11):
                def _click(e, o=opt):
                    _apply_filter(None if self.live_filter == o else o)
                btn = ft.ElevatedButton(
                    content=self._txt(label, size=size),
                    expand=True, height=height,
                    style=ft.ButtonStyle(bgcolor=_INACTIVE, color=ft.Colors.WHITE),
                    on_click=_click,
                )
                _all_filter_btns.append((opt, btn))
                return btn

            row2 = ft.Row(controls=[
                _filter_btn('1-18',  '1-18',  height=28, size=9),
                _filter_btn('Even',  'Even',  height=28, size=9),
                _filter_btn('R',     'RED',   height=28, size=9),
                _filter_btn('B',     'BLACK', height=28, size=9),
                _filter_btn('Odd',   'Odd',   height=28, size=9),
                _filter_btn('19-36', '19-36', height=28, size=9),
            ], spacing=2, tight=True)
            rb_bar = ft.Container(
                bgcolor='#1a2a3a',
                padding=ft.padding.symmetric(horizontal=6, vertical=4),
                content=ft.Column(controls=[row2], spacing=3),
            )

        self.mixer_btns = {}
        vc = self.visible_cats
        all_cats = [
            ('cols',   ['34', '35', '36'],               C_COL),
            ('docs',   ['1a', '2a', '3a'],               C_DOC),
            ('secs',   ['Z0', 'ZG', 'ZP', 'H'],          C_SEC),
            ('thirds', ['T1', 'T2', 'T3'],               C_SET),
            ('wave',   ['W1', 'W2', 'W3'],               C_WAV),
        ]
        # Regular categories
        cats = [(grps, col) for key, grps, col in all_cats if vc.get(key, True)]
        mixer_rows = []
        for grps, col in cats:
            row_btns = []
            for g in grps:
                btn = ft.ElevatedButton(
                    content=self._txt(g),
                    data={'name': g, 'color': col},
                    on_click=self.seleccionar_mixer,
                    expand=True, height=40,
                    style=ft.ButtonStyle(
                        bgcolor=col, color=ft.Colors.WHITE,
                        animation_duration=400,
                        overlay_color={
                            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.4, ft.Colors.WHITE),
                        },
                    ),
                )
                self.mixer_btns[g] = btn
                row_btns.append(btn)
            mixer_rows.append(ft.Row(controls=row_btns, spacing=2))
        
        # Filter buttons with roulette table layout and individual colors
        if vc.get('filters', True):
            # Color map for filter buttons
            filter_colors = {
                'R': '#cc0000',      # Red
                'B': '#aaaaaa',      # Black - lighter gray when not pressed
                '1-18': '#aaaaaa',   # Lighter gray
                'Even': '#aaaaaa',   # Lighter gray
                'Odd': '#aaaaaa',    # Lighter gray
                '19-36': '#aaaaaa',  # Lighter gray
            }
            # Roulette table layout: 1-18 | Even | Red | Black | Odd | 19-36
            filter_order = ['1-18', 'Even', 'R', 'B', 'Odd', '19-36']
            filter_row_btns = []
            for g in filter_order:
                btn_color = filter_colors[g]
                # Use smaller text for longer labels to fit single line
                text_size = 11 if g in ('1-18', '19-36') else 12
                # For black button, use dark overlay to go really black when pressed
                # For others, use light overlay
                overlay = {
                    ft.ControlState.PRESSED: ft.Colors.with_opacity(0.7, '#000000') if g == 'B'
                                            else ft.Colors.with_opacity(0.4, ft.Colors.WHITE),
                }
                btn = ft.ElevatedButton(
                    content=self._txt(g, size=text_size),
                    data={'name': g, 'color': btn_color},
                    on_click=self.seleccionar_mixer,
                    expand=True, height=40,
                    style=ft.ButtonStyle(
                        bgcolor=btn_color, color=ft.Colors.WHITE,
                        animation_duration=400,
                        overlay_color=overlay,
                    ),
                )
                self.mixer_btns[g] = btn
                filter_row_btns.append(btn)
            mixer_rows.append(ft.Row(controls=filter_row_btns, spacing=2))

        mixer_box = ft.Container(
            padding=ft.padding.symmetric(horizontal=2),
            content=ft.Column(controls=mixer_rows, spacing=2),
        )

        self.btn_inv = ft.ElevatedButton(
            content=self._txt("INVEST"),
            on_click=self.confirmar_manual,
            expand=2, height=45,
            style=ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.WHITE,
                                 animation_duration=400),
        )
        btn_corr = ft.ElevatedButton(
            content=self._txt("UNDO"),
            on_click=self.corregir_ultimo,
            expand=1, height=45,
            style=ft.ButtonStyle(bgcolor='#f39c12', color=ft.Colors.WHITE,
                                 animation_duration=400),
        )
        btn_fin = ft.ElevatedButton(
            content=self._txt("FINISH"),
            on_click=self.finalizar_sesion,
            expand=1, height=45,
            style=ft.ButtonStyle(bgcolor='#ff4444', color=ft.Colors.WHITE,
                                 animation_duration=400),
        )
        ctrl_bar = ft.Container(
            padding=ft.padding.symmetric(horizontal=4, vertical=4),
            content=ft.Row(controls=[self.btn_inv, btn_corr, btn_fin], spacing=4),
        )

        teclado_controls = [
            ft.Row(controls=[
                ft.ElevatedButton(
                    content=self._txt("0"),
                    data=0, on_click=self.process_number,
                    height=45, expand=True,
                    style=ft.ButtonStyle(
                        bgcolor='#27ae60', color=ft.Colors.WHITE,
                        animation_duration=400,
                        overlay_color={
                            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.4, ft.Colors.WHITE),
                        },
                    ),
                )
            ])
        ]
        for i in range(12):
            row_btns = []
            for j in range(1, 4):
                n = (i * 3) + j
                row_btns.append(
                    ft.ElevatedButton(
                        content=self._txt(str(n)),
                        data=n, on_click=self.process_number,
                        expand=True, height=40,
                        style=ft.ButtonStyle(
                            bgcolor='#cc0000' if n in ROJOS else '#222222',
                            color=ft.Colors.WHITE,
                            animation_duration=400,
                            overlay_color={
                                ft.ControlState.PRESSED: ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
                            },
                        ),
                    )
                )
            teclado_controls.append(ft.Row(controls=row_btns, spacing=2))

        teclado = ft.Container(
            bgcolor='#0e3d24', padding=5, height=620,
            content=ft.Column(controls=teclado_controls, spacing=2),
        )

        self.reg_header_row = ft.Row(controls=[], spacing=0)
        self.reg_rows_box   = ft.ListView(controls=[], spacing=0, scroll=ft.ScrollMode.AUTO)
        self._rebuild_table_header()

        bitacora = ft.Container(
            height=170, bgcolor='#0d0d0d',
            content=ft.Column(
                spacing=0,
                controls=[
                    self.reg_header_row,
                    ft.Container(
                        expand=True,
                        content=self.reg_rows_box,
                    ),
                ],
            ),
        )

        self._set_view(
            ft.Container(
                bgcolor='#121212', expand=True,
                content=ft.Column(
                    expand=True, spacing=0,
                    controls=inv_bar_controls + [
                        stats_bar,
                    ] + ([ai_bar] if ai_bar else []) + [
                        prog_bar, sug_bar,
                    ] + ([rb_bar] if rb_bar else []) + [
                        mixer_box, ctrl_bar,
                        ft.Container(
                            expand=True,
                            content=ft.ListView(expand=True, controls=[teclado]),
                        ),
                        bitacora,
                    ],
                ),
            )
        )

        self.actualizar_sugerencias()

    # ──────────────────────────────────────────────────────────────────
    # LOG TABLE
    # ──────────────────────────────────────────────────────────────────
    def _table_specs(self):
        """Return list of (header, color) pairs based on visible_cats."""
        vc = getattr(self, 'visible_cats', {k: True for k in ['basic','cols','docs','secs','thirds','wave']})
        W  = ft.Colors.WHITE
        specs = [("N", '#f1c40f')]
        if vc.get('basic',  True): specs += [("R",'#ff4d4d'),("N",W),("P",'#3498db'),("I",'#f39c12'),("B",W),("A",W)]
        if vc.get('cols',   True): specs += [("34",C_COL),("35",C_COL),("36",C_COL)]
        if vc.get('docs',   True): specs += [("1a",C_DOC),("2a",C_DOC),("3a",C_DOC)]
        if vc.get('secs',   True): specs += [("Z0",C_SEC),("ZG",C_SEC),("ZP",C_SEC),("H",C_SEC)]
        if vc.get('thirds', True): specs += [("T1",C_SET),("T2",C_SET),("T3",C_SET)]
        if vc.get('wave',   True): specs += [("W1",C_WAV),("W2",C_WAV),("W3",C_WAV)]
        return specs

    def _rebuild_table_header(self):
        cw    = self._col_width()
        specs = self._table_specs()
        self.reg_header_row.controls = [
            ft.Text(h, width=cw, color=c,
                    text_align=ft.TextAlign.CENTER,
                    size=7, weight=ft.FontWeight.BOLD)
            for h, c in specs
        ]

    def update_registration_table(self):
        if self.reg_rows_box is None:
            return
        cw = self._col_width()
        self._rebuild_table_header()
        self.reg_rows_box.controls.clear()
        vc = getattr(self, 'visible_cats', {k: True for k in ['basic','cols','docs','secs','thirds','wave']})
        s  = "■"
        W  = ft.Colors.WHITE
        for n in self.history_nums[-9:]:
            cells = [(str(n), '#f1c40f')]
            if vc.get('basic', True):
                cells += [
                    (s if n in ROJOS else "",                '#ff4d4d'),
                    (s if (n != 0 and n not in ROJOS) else "", W),
                    (s if (n != 0 and n % 2 == 0) else "",  '#3498db'),
                    (s if (n % 2 != 0) else "",              '#f39c12'),
                    (s if (1 <= n <= 18) else "",            W),
                    (s if (19 <= n <= 36) else "",           W),
                ]
            live = getattr(self, 'live_table_mode', False)
            for key, grps, col in [
                ('cols',   ['34','35','36'],       C_COL),
                ('docs',   ['1a','2a','3a'],        C_DOC),
                ('secs',   ['Z0','ZG','ZP','H'],   C_SEC),
                ('thirds', ['T1','T2','T3'],        C_SET),
                ('wave',   ['W1','W2','W3'],        C_WAV),
            ]:
                if vc.get(key, True):
                    if live and key == 'docs':
                        # In live mode show ■ in every dozen whose live set contains n
                        cells += [(s if n in GRUPOS_MAESTROS[f'{g}_L'] else "", col) for g in grps]
                    else:
                        cells += [(s if n in GRUPOS_MAESTROS[g] else "", col) for g in grps]
            self.reg_rows_box.controls.append(
                ft.Row(
                    controls=[
                        ft.Text(txt, width=cw, color=col,
                                text_align=ft.TextAlign.CENTER,
                                size=8, weight=ft.FontWeight.BOLD)
                        for txt, col in cells
                    ],
                    spacing=0,
                )
            )
        self.reg_header_row.update()
        self.reg_rows_box.update()

    # ──────────────────────────────────────────────────────────────────
    # VISUAL FEEDBACK
    # ──────────────────────────────────────────────────────────────────
    def _darken_color(self, hex_color, factor=0.7):
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return f'#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}'
        return hex_color

    def _flash_button(self, btn, original_color, duration_ms=300):
        flash_color = self._darken_color(original_color, 0.6)
        async def _animate():
            btn.style.bgcolor = flash_color
            self.page.update()
            await asyncio.sleep(duration_ms / 1000)
            btn.style.bgcolor = original_color
            self.page.update()
        asyncio.create_task(_animate())

    # ──────────────────────────────────────────────────────────────────
    # GAME LOGIC
    # ──────────────────────────────────────────────────────────────────

    GRUPOS_STRAIGHT = {'Z0', 'ZG', 'ZP', 'H', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3'}
    PROG_2_OUT = [2, 6, 18, 54]          # 2 lines/dozens: 1,3,9,27 per line (4 attempts)
    PROG_2_IN  = [1, 3, 5, 9, 17]        # 2 sectors/zones progression

    def _is_outside(self):
        return all(g not in self.GRUPOS_STRAIGHT and g not in GRUPOS_LIVE_INSIDE
                   for g in self.grupos_activos)

    def _is_simple_outside_bet(self):
        """Check if current selection is a simple outside bet (single type, 1-2 groups).
        Simple outside bets: 1-2 dozens, 1-2 columns, 1-2 filters.
        Returns True for: 1a, 2a, 34+35, R, Even+Odd, etc.
        Returns False for: mixed types like 1a+34, 3+ same type, or any Z/T/W (sectors/thirds/wave).
        Z, T, W are treated as inside bets (intersection mode).
        """
        if not self.grupos_activos:
            return False
        
        n = len(self.grupos_activos)
        columns = {'34', '35', '36'}
        dozens = {'1a', '2a', '3a'}
        filters = {'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        outside_types = columns | dozens | filters
        inside_types = {'Z0', 'ZG', 'ZP', 'H', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3'}  # Always inside bets
        
        # Categorize active groups (use display names to handle live variants)
        active_display = [self._to_display_name(g) for g in self.grupos_activos]
        col_groups = [g for g in active_display if g in columns]
        doc_groups = [g for g in active_display if g in dozens]
        flt_groups = [g for g in active_display if g in filters]
        inside_grps = [g for g in active_display if g in inside_types]
        other_groups = [g for g in active_display if g not in outside_types and g not in inside_types]
        
        # If ANY Z/T/W groups present, treat as inside bet
        if inside_grps:
            return False
        
        # Count how many outside types are represented
        types_used = sum([1 for x in [col_groups, doc_groups, flt_groups, other_groups] if x])
        
        # Simple outside: only ONE type, and max 2 groups of that type
        return types_used == 1 and n <= 2

    def _group_cost(self, g):
        if g in self.GRUPOS_STRAIGHT or g in GRUPOS_LIVE_INSIDE:
            return self.val_fin * len(GRUPOS_MAESTROS[g])
        return self.val_fout

    def _progression_for_N(self, N: int) -> list:
        """
        Build chip progression for N numbers played.
        Rule: iterate n=1,2,3,... Include n if GR > 0, skip if GR <= 0.
        Acum only accumulates from included steps.
        GR = n * val_fin * (36-N) - acum
        """
        chip = self.val_fin
        if N <= 0 or chip <= 0 or N >= 36:
            return list(range(1, 21))
        margin_per_chip = chip * (36 - N)
        if margin_per_chip <= 0:
            return list(range(1, 21))
        progression, acum, n = [], 0.0, 1
        while len(progression) < 20 and n <= 1000:
            gr = n * margin_per_chip - acum
            if gr > 0:
                progression.append(n)
                acum += n * chip * N
            n += 1
        return progression or [1]

    def _sniper_inside_multi(self, N: int) -> int:
        """Chip multiplier for the current inside-sniper progression level."""
        if not self.prog_on:
            return self.fixed_multi
        n_groups = len(self.grupos_activos)
        level = self.idx_fibo_in if n_groups == 1 else self.nivel_martingala_in
        prog  = self._progression_for_N(N)
        return prog[min(level, len(prog) - 1)]

    def _current_multi(self, is_out: bool) -> int:
        """Return per-group multiplier.
        For outside n>1 with prog ON, PROG_2_OUT stores TOTAL chips, so we
        divide by n to get the per-group value (consistent with prog OFF)."""
        if not self.prog_on:
            return self.fixed_multi
        n = len(self.grupos_activos)
        if is_out:
            if n == 1:
                return PROG_FIBO[self.idx_fibo_out]
            idx = min(self.nivel_martingala_out, len(self.PROG_2_OUT) - 1)
            return self.PROG_2_OUT[idx] // max(n, 1)
        # Non-sniper inside fallback: linear
        if n == 1:
            return self.idx_fibo_in + 1
        return self.nivel_martingala_in + 1

    def _compute_bet(self):
        n = len(self.grupos_activos)
        if n == 0:
            return 0.0, 0.0, 0

        # Define outside bet types
        columns = {'34', '35', '36'}
        dozens = {'1a', '2a', '3a'}
        filters = {'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        outside_types = columns | dozens | filters
        inside_types = {'Z0', 'ZG', 'ZP', 'H', 'T1', 'T2', 'T3', 'W1', 'W2', 'W3'}  # Always inside bets
        
        # Categorize active groups (use display names to handle live variants)
        active_display = [self._to_display_name(g) for g in self.grupos_activos]
        col_groups = [g for g in active_display if g in columns]
        doc_groups = [g for g in active_display if g in dozens]
        flt_groups = [g for g in active_display if g in filters]
        inside_grps = [g for g in active_display if g in inside_types]
        other_groups = [g for g in active_display if g not in outside_types and g not in inside_types]
        
        # Count how many types are represented (include inside groups in type count)
        types_used = sum([1 for x in [col_groups, doc_groups, flt_groups, inside_grps, other_groups] if x])
        
        total = 0.0
        win_payout = 0.0
        num_chips = 0
        
        # Simple outside bet: single type with max 2 groups, NO Z/T/W (inside types)
        is_simple_outside = (types_used == 1 and n <= 2 and not inside_grps)
        
        if is_simple_outside:
            multi_out = self._current_multi(is_out=True)
            n_out = len(self.grupos_activos)
            num_chips = n_out  # For outside bets, num_chips = number of groups
            if n_out == 1:
                total = self.val_fout * multi_out
                win_payout = total * 3
            else:
                total = self.val_fout * multi_out * n_out
                win_payout = self.val_fout * multi_out * 3
        else:
            # Mixed types or 3+ groups = inside bet
            multi_in = self._current_multi(is_out=False)

            if self.sniper_mode:
                intersection = self._compute_intersection()
                num_chips = len(intersection) if intersection else 1
                if self.prog_on:
                    multi_in = self._sniper_inside_multi(num_chips)
                total = self.val_fin * num_chips * multi_in
                win_payout = self.val_fin * 36 * multi_in
            else:
                # Sniper OFF: use sum of safety levels (total chips wagered)
                safety_levels = self._compute_safety_levels()
                # Only count numbers that are covered (safety level > 0)
                num_chips = sum(v for v in safety_levels.values() if v > 0) if safety_levels else 1
                total = self.val_fin * num_chips * multi_in
                win_payout = self.val_fin * 36 * multi_in
        
        return total, win_payout, num_chips

    def process_number(self, e):
        try:
            btn = e.control
            try:
                self._flash_button(btn, btn.style.bgcolor, 300)
            except Exception:
                pass

            num = int(e.control.data)
            _acted, _bet_groups, _is_win, _cost = False, [], None, 0.0
            if self.activa:
                n                     = len(self.grupos_activos)
                is_simple_outside     = self._is_simple_outside_bet()
                self.last_bet_outside = is_simple_outside
                self.last_prog_state  = self.prog_on   # save for undo
                total_cost, win_py, _ = self._compute_bet()
                self.banca_actual    -= total_cost

                # Sniper mode: check intersection only; regular mode: check if in any group
                is_win = False
                if self.sniper_mode and not is_simple_outside:
                    intersection = self._compute_intersection()
                    is_win = num in intersection
                else:
                    is_win = any(num in GRUPOS_MAESTROS[g] for g in self.grupos_activos)

                if is_win:
                    self.banca_actual += win_py
                    self.last_bank_delta = win_py - total_cost
                    # Only reset progression counters when progression is active
                    if self.prog_on:
                        if is_simple_outside:
                            self.idx_fibo_out         = 0
                            self.nivel_martingala_out = 0
                        else:
                            self.idx_fibo_in         = 0
                            self.nivel_martingala_in = 0
                else:
                    self.last_bank_delta = -total_cost
                    # Only advance progression counters when progression is active
                    if self.prog_on:
                        if n == 1:
                            if is_simple_outside:
                                if self.idx_fibo_out < len(PROG_FIBO) - 1:
                                    self.idx_fibo_out += 1
                            else:
                                if self.idx_fibo_in < len(PROG_FIBO) - 1:
                                    self.idx_fibo_in += 1
                        else:
                            if is_simple_outside:
                                self.nivel_martingala_out += 1
                            else:
                                self.nivel_martingala_in += 1
                _acted, _bet_groups, _is_win, _cost = (
                    True, list(self.grupos_activos), is_win, total_cost)
                self.activa         = False
                self.grupos_activos = []
                self.limpiar_seleccion_visual()

                # AI: grade the captured choice now that the result is known,
                # and incrementally train the combination-choice model.
                if getattr(self, 'ai_ok', False) and self.current_choice:
                    try:
                        self.strategy_model.record_outcome(
                            self.current_choice, won=is_win,
                            profit=self.last_bank_delta)
                        # This board was a line-up the player ENTERED on.
                        self.strategy_model.record_observation(
                            self.history_nums, acted=True)
                        # Learn how long the player waited before this entry.
                        self.strategy_model.record_entry_wait(self.spins_since_entry)
                        self.spins_since_entry = 0
                        if getattr(self, 'decision_tracker', None) and self.current_decision_id:
                            self.decision_tracker.record_outcome(
                                decision_id=self.current_decision_id,
                                spin_result=num,
                                outcome='win' if is_win else 'loss',
                                profit_loss=self.last_bank_delta)
                    except Exception:
                        pass
                    finally:
                        self.current_choice = None
                        self.current_decision_id = None
            else:
                if self.free_spin_mode:
                    # Red + Black uses the BASE chip (not CHIP IN): net 0 unless
                    # 0 falls, in which case both chips are lost.
                    base_chip = getattr(self, 'last_base_chip', self.val_fin)
                    delta = -2 * base_chip if num == 0 else 0.0
                else:
                    delta = self.val_fin * (1 if num in ROJOS else -1)
                self.banca_actual      += delta
                self.last_bank_delta    = delta
                self.last_bet_outside   = None

                # AI: no combo bet — the player is WAITING (lining up) for a
                # better entry. Record this board as a skipped setup.
                if getattr(self, 'ai_ok', False):
                    try:
                        self.strategy_model.record_observation(
                            self.history_nums, acted=False)
                    except Exception:
                        pass

            # Real-bet logging: record the AI suggestion the player saw, their
            # actual entry decision (enter/pass), and the outcome — the dataset
            # for learning WHEN the player enters. Uses history BEFORE this spin
            # is appended, matching what was on screen at decision time.
            try:
                self._log_real_bet(num, _acted, _bet_groups, _is_win, _cost)
            except Exception:
                pass

            self.history_nums.append(num)
            self.sliding_window.append(num)
            if getattr(self, 'ai_ok', False):
                self.spins_since_entry += 1   # one more spin in the line-up
                # Feed the live B/R predictors (green/0 is skipped inside each).
                if getattr(self, 'rhythm_model', None):
                    try:
                        self.rhythm_model.observe_num(num)
                    except Exception:
                        pass
                if getattr(self, 'pattern_model', None):
                    try:
                        self.pattern_model.observe_num(num)
                    except Exception:
                        pass
            self.update_registration_table()   # buffers row/header updates
            self.actualizar_sugerencias()       # buffers sug_row update
            self.update_ui()                    # single page.update() flushes all
        except Exception as _err:
            import traceback
            with open("/tmp/linup_error.log", "a") as _f:
                _f.write(f"[process_number] {type(_err).__name__}: {_err}\n")
                traceback.print_exc(file=_f)

    def _current_suggestion(self):
        """The live dozen+colour the app is suggesting right now, as (dozen,
        colour) — reproduces what the player sees before entering. Uses the
        pre-spin sliding window (sector affinity) + the RVS colour regime."""
        try:
            sw = list(self.sliding_window)
            if len(sw) < 6:
                return (None, None)
            def _sc(g):
                return sum(DOZEN_SECTOR_AFFINITY[g].get(SECTOR_OF.get(n), 0.0)
                           for n in sw) / 6.0
            stats = sorted(((_sc(g), g) for g in ('1a', '2a', '3a')), reverse=True)
            if stats[0][0] <= 0 or abs(stats[0][0] - stats[1][0]) < 1e-9:
                return (None, None)   # no data / WAIT tie
            return (stats[0][1], regime_color(self.history_nums))
        except Exception:
            return (None, None)

    def _all_suggestions(self) -> dict:
        """Reproduce the suggestion shown for EVERY category this spin, as
        {category: [group_keys]} (the groups a tap would bet). [] = no
        suggestion / WAIT. Mirrors actualizar_sugerencias; used for the bet-eval
        scoreboard so we can score every option, not just the one played."""
        out = {}
        try:
            sw = list(self.sliding_window)
            if len(sw) < 6:
                return out
            live = getattr(self, 'live_table_mode', False)
            lf = getattr(self, 'live_filter', None)
            cats = [('cols', ['34', '35', '36']), ('docs', ['1a', '2a', '3a']),
                    ('secs', ['Z0', 'ZG', 'ZP', 'H']), ('thirds', ['T1', 'T2', 'T3']),
                    ('wave', ['W1', 'W2', 'W3'])]
            PAIR_BLOQUEADO = {'ZG', 'ZP'}
            for key, grupos in cats:
                def _score(g, _key=key):
                    if live and _key == 'docs':
                        return sum(DOZEN_SECTOR_AFFINITY[g].get(SECTOR_OF.get(n), 0.0)
                                   for n in sw) / 6
                    return sum(1 for n in sw if n in GRUPOS_MAESTROS[g]) / 6
                stats = sorted(({'g': g, 'p': _score(g)} for g in grupos),
                               key=lambda x: x['p'], reverse=True)
                if live and key == 'docs':
                    tie = (len(stats) > 1 and stats[0]['p'] > 0
                           and abs(stats[0]['p'] - stats[1]['p']) < 1e-9)
                    if tie or stats[0]['p'] <= 0:
                        out[key] = []
                    else:
                        top = stats[0]['g']
                        rcol = regime_color(self.history_nums) if (
                            lf is None and getattr(self, 'ai_ok', False)) else None
                        eff = lf if lf is not None else rcol
                        out[key] = [f'{top}{_DOC_SFX.get(eff, "_L")}']
                    continue
                cand = {stats[0]['g'], stats[1]['g']}
                if (stats[1]['p'] > stats[2 if len(stats) > 2 else 1]['p']
                        and cand != PAIR_BLOQUEADO):
                    out[key] = [stats[0]['g'], stats[1]['g']]
                else:
                    out[key] = []
        except Exception:
            pass
        return out

    def _log_real_bet(self, num, acted, bet_groups, is_win, cost):
        """Append one per-spin JSONL record: the AI suggestion, the player's
        entry decision, and the outcome. Best-effort; never blocks a spin."""
        if not getattr(self, 'db_path', None):
            return
        import json
        hist = list(self.history_nums)      # BEFORE this spin is appended
        pred, kind, d = _regime(hist)
        sug_dozen, sug_color = self._current_suggestion()
        sug_combo = f'{sug_dozen}{_DOC_SFX.get(sug_color, "_L")}' if sug_dozen else None
        disp = [self._to_display_name(g) for g in bet_groups]
        try:
            ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            ts = ''
        rec = {
            'ts': ts,
            'table': str(getattr(self, 'nombre_mesa', '')),
            'session': (getattr(self, 'play_session_id', None)
                        or getattr(self, 'session_id', None)),
            'spin': len(hist),
            'num': int(num),
            'live': bool(getattr(self, 'live_table_mode', False)),
            'acted': bool(acted),
            'bet': disp,
            'followed_suggestion': bool(sug_dozen and sug_dozen in disp),
            'suggested': {'dozen': sug_dozen, 'color': sug_color, 'combo': sug_combo},
            'suggestions': self._all_suggestions(),
            'regime': {
                'kind': kind,
                'color': 'R' if pred == 1 else ('B' if pred == 0 else None),
                'run': d.get('run'),
                'frac_red': round(d['frac'], 3) if d.get('frac') is not None else None,
                'prep': round(d['prep'], 3) if d.get('prep') is not None else None,
                'n': d.get('n'),
            },
            'is_win': is_win,
            'delta': round(float(getattr(self, 'last_bank_delta', 0.0)), 3),
            'cost': round(float(cost), 3),
            'bank_after': round(float(getattr(self, 'banca_actual', 0.0)), 2),
            'spins_since_entry': getattr(self, 'spins_since_entry', None),
        }
        path = os.path.join(os.path.dirname(self.db_path), 'bet_log.jsonl')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')

    @staticmethod
    def _to_display_name(g):
        """Strip live/filter suffixes to get the mixer button key."""
        for sfx in ('_LR', '_LB', '_L', '_R', '_B'):
            if g.endswith(sfx):
                return g[:-len(sfx)]
        return g

    def _refresh_mixer_colors(self):
        has_sel = bool(self.grupos_activos)
        active_display = {self._to_display_name(g) for g in self.grupos_activos}
        # Identify outside bet types
        outside_groups = {'34', '35', '36', '1a', '2a', '3a', 'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        
        for g, btn in self.mixer_btns.items():
            base_color = btn.data['color']
            is_outside = g in outside_groups
            
            if g in active_display:
                if is_outside:
                    # Outside bets: yellow text (like inside bets) to indicate selection
                    btn.style = ft.ButtonStyle(
                        bgcolor=base_color, color='#ffdd00',
                        animation_duration=400,
                        overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(0.4, ft.Colors.WHITE)},
                    )
                else:
                    # Inside bets: yellow text + original background
                    btn.style = ft.ButtonStyle(
                        bgcolor=base_color, color='#ffdd00',
                        animation_duration=400,
                        overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(0.4, ft.Colors.WHITE)},
                    )
            elif has_sel:
                # Deselected (others selected): dimmed base color + white text for visibility
                dimmed_color = ft.Colors.with_opacity(0.5, base_color)
                btn.style = ft.ButtonStyle(
                    bgcolor=dimmed_color, color=ft.Colors.WHITE,
                    animation_duration=400,
                )
            else:
                # Unselected (no active): full color with white text
                btn.style = ft.ButtonStyle(
                    bgcolor=base_color, color=ft.Colors.WHITE,
                    animation_duration=400,
                    overlay_color={ft.ControlState.PRESSED: ft.Colors.with_opacity(0.4, ft.Colors.WHITE)},
                )
            btn.update()
        # Live-grade the new selection in the AI coach bar.
        self._refresh_ai_label()

    def _live_norm(self, g):
        """In live table mode, map a bare dozen/column to its live (wheel-spread)
        variant so coverage always uses the live set — e.g. '3a' -> '3a_L', which
        includes 0. No-op outside live mode or for already-suffixed groups."""
        if not getattr(self, 'live_table_mode', False):
            return g
        name = self._to_display_name(g)
        if g != name:          # already a live/filtered variant — leave as-is
            return g
        f = getattr(self, 'live_filter', None)
        if name in ('1a', '2a', '3a'):
            return f'{name}{_DOC_SFX.get(f, "_L")}'
        if name in ('34', '35', '36') and f:
            return f'{name}{_COL_SFX.get(f, "")}'
        return g

    def _compute_safety_levels(self):
        """Compute safety level for each number (count of groups that contain it).
        Returns dict {num: count} where count is 0-5."""
        levels = {}
        # Use ALL active groups, not just straight ones
        active_groups = [self._live_norm(g) for g in self.grupos_activos]
        active_groups = [g for g in active_groups
                        if g in GRUPOS_MAESTROS]  # make sure group exists
        for num in range(0, 37):
            count = sum(1 for g in active_groups if num in GRUPOS_MAESTROS[g])
            levels[num] = count
        return levels

    def _compute_intersection(self):
        """Sniper mode: smart intersection across group types, union within types.
        
        Examples:
        - Z0 + ZG (both sectors): UNION of sectors
        - Z0 + ZG + R (sectors + color): (Z0 ∪ ZG) ∩ R
        - Z0 + ZG + 1a + Even: (Z0 ∪ ZG) ∩ (1a) ∩ (Even)
        - 1a + 2a + R: (1a ∪ 2a) ∩ R
        """
        active_groups = [self._live_norm(g) for g in self.grupos_activos]
        active_groups = [g for g in active_groups
                        if g in GRUPOS_MAESTROS]
        if not active_groups:
            return set()
        
        # Categorize groups by type
        def get_group_type(g):
            if g in {'Z0', 'ZG', 'ZP', 'H'}:
                return 'SECTOR'
            elif g in {'T1', 'T2', 'T3'}:
                return 'WHEEL'
            elif g in {'W1', 'W2', 'W3'}:
                return 'WAVE'
            elif g.startswith(('34', '35', '36')):
                return 'COLUMN'
            elif g.startswith(('1a', '2a', '3a')):
                return 'DOZEN'
            elif g in {'R', 'B'}:
                return 'COLOR'
            elif g in {'Even', 'Odd'}:
                return 'PARITY'
            elif g in {'1-18', '19-36'}:
                return 'RANGE'
            else:
                return 'FILTER'
        
        # Group by type
        by_type = {}
        for g in active_groups:
            gtype = get_group_type(g)
            if gtype not in by_type:
                by_type[gtype] = []
            by_type[gtype].append(g)
        
        # Compute union for each type
        type_unions = {}
        for gtype, groups in by_type.items():
            union = set()
            for g in groups:
                union |= GRUPOS_MAESTROS[g]
            type_unions[gtype] = union
        
        # Intersect across types
        result = None
        for gtype, union_set in type_unions.items():
            if result is None:
                result = union_set.copy()
            else:
                result &= union_set

        # 0 has no colour/parity/range, so those filters must not drop it when it
        # belongs to a base selection (e.g. 3a's wheel-spread, or the Z0 sector).
        # Mirrors the group design where every 3a_L* variant re-adds 0.
        base_types   = {'DOZEN', 'COLUMN', 'SECTOR', 'WHEEL', 'WAVE'}
        only_filters = {'COLOR', 'PARITY', 'RANGE'}
        present_base   = [u for t, u in type_unions.items() if t in base_types]
        present_filter = [t for t in type_unions if t in only_filters]
        if (result is not None and 0 not in result
                and present_base and present_filter
                and all(0 in u for u in present_base)):
            result.add(0)

        return result if result is not None else set()

    def seleccionar_mixer(self, e):
        g = e.control.data['name']
        # In Live Table mode, map dozens/columns to their live/filtered variants
        actual_g = g
        if self.live_table_mode:
            f = self.live_filter
            if g in ('1a', '2a', '3a'):
                actual_g = f'{g}{_DOC_SFX.get(f, "_L")}'
            elif g in ('34', '35', '36') and f:
                actual_g = f'{g}{_COL_SFX.get(f, "")}'
        # Toggle: check by display name to handle live variants
        if g in {self._to_display_name(x) for x in self.grupos_activos}:
            self.grupos_activos = [x for x in self.grupos_activos
                                   if self._to_display_name(x) != g]
        else:
            # Always allow unlimited selections
            self.grupos_activos.append(actual_g)
        self._refresh_mixer_colors()
        self.update_inv_label()
        self.lbl_inv.update()

    def _build_outside_bet_sections(self, highlight=True):
        """Build real roulette table layout with bets positioned around the grid.
        Returns dict with sections for layout organization.
        left1 = dozens, left2 = filters (both on left side in two columns)
        highlight: if True, selected fields get yellow; if False, all fields are gray (for inside bet popups)
        """
        result = {'left1': [], 'left2': [], 'right': [], 'bottom': []}
        
        # Extract base names
        def get_base_name(g):
            for sfx in ('_LR', '_LB', '_L', '_R', '_B', '_18', '_E', '_O', '_36', '_L18', '_LE', '_LO', '_L36'):
                if g.endswith(sfx):
                    return g[:-len(sfx)]
            return g
        
        base_names = {get_base_name(g) for g in self.grupos_activos}
        columns = {'34', '35', '36'}
        dozens = {'1a', '2a', '3a'}
        filters = {'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        
        col_base = base_names & columns
        doc_base = base_names & dozens
        flt_base = base_names & filters
        
        # Each dozen spans 4 rows of the grid (1-12, 13-24, 25-36)
        # Height = 4 rows × (50px cell + 2px gap) - 2px for last gap = 206px
        row_height = 50 + 2  # cell + gap
        dozens_height = row_height * 4 - 2  # 4 rows for each dozen
        
        # LEFT SIDE COLUMN 1: Dozens (1a, 2a, 3a) - tall cells spanning 4 rows each
        if doc_base or not highlight:  # Always show dozens section if we're showing outside fields
            for doc in ['1a', '2a', '3a']:
                is_selected = highlight and (doc in doc_base)
                bg_color = '#ffdd00' if is_selected else '#333333'
                text_color = '#000000' if is_selected else ft.Colors.WHITE
                cell = ft.Container(
                    bgcolor=bg_color,
                    border_radius=2, padding=4,
                    content=ft.Text(doc, color=text_color, size=10,
                                  weight=ft.FontWeight.BOLD,
                                  text_align=ft.TextAlign.CENTER),
                    width=50, height=dozens_height,
                    alignment=ft.Alignment(0, 0),
                )
                result['left1'].append(cell)
        
        # LEFT SIDE COLUMN 2: Filters (1-18, Even, R, B, Odd, 19-36)
        if flt_base or not highlight:  # Always show filters section if we're showing outside fields
            filter_order = ['1-18', 'Even', 'R', 'B', 'Odd', '19-36']
            filter_labels = {'1-18': '1-18', 'Even': 'E', 'R': 'R', 
                            'B': 'B', 'Odd': 'O', '19-36': '19-36'}
            # Each filter cell = grid height / 6 ≈ 26px
            filter_height = (dozens_height / 2)  # Roughly 2 filters per dozen row
            for filt in filter_order:
                is_selected = highlight and (filt in flt_base)
                bg_color = '#ffdd00' if is_selected else '#333333'
                text_color = '#000000' if is_selected else ft.Colors.WHITE
                cell = ft.Container(
                    bgcolor=bg_color,
                    border_radius=2, padding=2,
                    content=ft.Text(filter_labels[filt], color=text_color, size=8,
                                  weight=ft.FontWeight.BOLD,
                                  text_align=ft.TextAlign.CENTER),
                    width=50, height=int(filter_height),
                )
                result['left2'].append(cell)
        
        # BOTTOM: Columns (34, 35, 36) aligned with grid columns
        bottom_columns = []
        if col_base or not highlight:  # Always show columns section if we're showing outside fields
            for col in ['34', '35', '36']:
                is_selected = highlight and (col in col_base)
                bg_color = '#ffdd00' if is_selected else '#333333'
                text_color = '#000000' if is_selected else ft.Colors.WHITE
                cell = ft.Container(
                    bgcolor=bg_color,
                    border_radius=2, padding=4,
                    content=ft.Text(col, color=text_color, size=8,
                                  weight=ft.FontWeight.BOLD,
                                  text_align=ft.TextAlign.CENTER),
                    width=50, height=28,
                )
                bottom_columns.append(cell)
            result['bottom'].append(('columns', bottom_columns))
        
        return result

    def _show_roulette_chip_popup(self, on_ready_cb):
        """Show popup based on bet type:
        - For simple outside bets: show full table with selected groups (1a, 2a, etc.) highlighted with yellow borders
        - For inside bets: show full table with intersection numbers highlighted in yellow
        """
        # Check if this is a simple outside bet
        is_simple_outside = self._is_simple_outside_bet()
        
        multi        = self._current_multi(is_out=is_simple_outside)
        chip_per_num = self.val_fin * multi
        
        total_cost, _, _ = self._compute_bet()   # exact amount that will hit the bank
        
        # For outside bets, highlight selected groups; for inside bets, highlight intersection
        if is_simple_outside:
            return self._show_outside_bet_popup(on_ready_cb)
        else:
            return self._show_inside_bet_popup(on_ready_cb)
    
    def _show_outside_bet_popup(self, on_ready_cb):
        """Show popup with full table: outside field buttons highlighted yellow, NO grid highlighting."""
        total_cost, _, _ = self._compute_bet()
        multi        = self._current_multi(is_out=True)
        chip_per_num = self.val_fout * multi
        
        def grp_color(g):
            if g in {'Z0', 'ZG', 'ZP', 'H'}:                   return C_SEC
            if g in {'W1', 'W2', 'W3'}:                         return C_WAV
            if self._to_display_name(g) in ('1a', '2a', '3a'):  return C_DOC
            if self._to_display_name(g) in ('34', '35', '36'):  return C_COL
            return C_SET

        def grp_label(g):
            """Human-readable label for chip popup header."""
            for sfx, tag in [('_LR','·R'),('_LB','·B'),('_L18','·1-18'),
                              ('_LE','·Even'),('_LO','·Odd'),('_L36','·19-36'),
                              ('_L',''), ('_R','·R'),('_B','·B'),('_18','·1-18'),
                              ('_E','·Even'),('_O','·Odd'),('_36','·19-36')]:
                if g.endswith(sfx):
                    return self._to_display_name(g) + tag
            return g

        title_chips = [
            ft.Container(
                bgcolor=grp_color(g), border_radius=5,
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                content=ft.Text(grp_label(g), color=ft.Colors.WHITE, size=14,
                                weight=ft.FontWeight.BOLD),
            )
            for g in self.grupos_activos
        ]

        CELL = 25   # zero cell size
        CN   = 50   # number cell size (double, -10%)
        GAP  = 2
        
        def num_bg(num):
            """Original roulette colors: red for ROJOS, black for others, green for zero"""
            if num == 0:
                return '#27ae60'
            else:
                return '#c0392b' if num in ROJOS else '#2c3e50'
        
        def make_cell(num):
            # For outside bets, NO highlighting on grid numbers - all gray borders
            return ft.Container(
                width=CN, height=CN,
                bgcolor=num_bg(num),
                border=ft.Border.all(1, '#333'),
                border_radius=6,
                content=ft.Column(
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                    controls=[ft.Text(str(num), size=14, color=ft.Colors.WHITE,
                                     weight=ft.FontWeight.BOLD,
                                     text_align=ft.TextAlign.CENTER)],
                ),
            )

        ROW_W = CN * 3 + GAP * 2   # exact pixel width of a number row

        # Zero row: green background, gray border (no highlighting for outside bets)
        zero_row = ft.Container(
            width=ROW_W, height=CELL * 2,
            bgcolor='#27ae60',
            border=ft.Border.all(1, '#333'),
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            content=ft.Text("0", size=14, color=ft.Colors.WHITE,
                          weight=ft.FontWeight.BOLD,
                          text_align=ft.TextAlign.CENTER),
        )

        num_rows = []
        for i in range(12):
            base = i * 3
            a, b, c = base + 1, base + 2, base + 3
            num_rows.append(
                ft.Row([make_cell(a), make_cell(b), make_cell(c)],
                       spacing=GAP, tight=True)
            )

        grid = ft.Container(
            width=ROW_W,
            content=ft.Column(
                controls=[zero_row] + num_rows,
                spacing=GAP,
                tight=True,
            ),
        )

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def on_cancel(_ev):
            dlg.open = False
            dlg.update()

        def cerrar(_ev):
            dlg.open = False
            dlg.update()
            on_ready_cb()

        _chip_lbl = ft.Text(
            f"${chip_per_num:.2f}/num",
            color='#f1c40f', size=13,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.title = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    wrap=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=title_chips,
                ),
                _chip_lbl,
            ],
        )

        # For outside bets: show only total (no breakdown)
        _total_lbl = ft.Text(
            f"Total: ${total_cost:.2f}",
            color='#ecf0f1', size=12, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )

        # When progression is OFF, show live multiplier picker inside the popup
        popup_extra: list = []
        if not self.prog_on:
            _pmx_refs: dict = {}

            def _make_pmx(mx):
                def handler(_ev):
                    self.fixed_multi = mx
                    _c  = _outside_chip * mx
                    _t  = len(self.grupos_activos) * _c  # num groups × chip_per_group
                    _chip_lbl.value  = f"${_c:.2f}/num"
                    _total_lbl.value = f"Total: ${_t:.2f}"
                    for k, b in _pmx_refs.items():
                        b.style = ft.ButtonStyle(
                            bgcolor='#f39c12' if k == mx else '#3a3a3a',
                            color=ft.Colors.WHITE,
                        )
                        b.update()
                    _chip_lbl.update()
                    _total_lbl.update()
                    self.update_inv_label()
                    if self.lbl_inv:
                        self.lbl_inv.update()
                return handler

            mx_row = ft.Row(spacing=3, tight=True)
            for _mx in (1, 2, 3, 4, 5):
                _mb = ft.ElevatedButton(
                    content=ft.Text(f"{_mx}x", size=11,
                                    weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    expand=True, height=34,
                    style=ft.ButtonStyle(
                        bgcolor='#f39c12' if _mx == self.fixed_multi else '#3a3a3a',
                        color=ft.Colors.WHITE,
                    ),
                    on_click=_make_pmx(_mx),
                )
                _pmx_refs[_mx] = _mb
                mx_row.controls.append(_mb)

            popup_extra = [
                ft.Container(height=6),
                ft.Text("MULTIPLIER", color='#aaaaaa', size=10,
                        text_align=ft.TextAlign.CENTER),
                mx_row,
            ]

        # Build outside betting table sections - with highlighting enabled for outside bets
        outside_sections = self._build_outside_bet_sections(highlight=True)
        
        # Extract betting table components for layout
        left1_bets = outside_sections.get('left1', [])     # Dozens
        left2_bets = outside_sections.get('left2', [])     # Filters
        right_bets = outside_sections.get('right', [])     # (empty)
        bottom_sections = outside_sections.get('bottom', [])  # List of (type, controls) tuples
        
        # Build the table layout: left side (2 columns) / grid / bottom
        if left1_bets or left2_bets or bottom_sections:
            # Left side: TWO COLUMNS - Dozens (left1) and Filters (left2)
            # Shift down 52px (zero row 50px + gap 2px) so cells start at row 1
            left_panels = []
            
            if left1_bets:
                left1_panel = ft.Container(
                    width=50,
                    padding=ft.padding.only(top=52),
                    content=ft.Column(controls=left1_bets, spacing=2, tight=True,
                                     horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                )
                left_panels.append(left1_panel)
            
            if left2_bets:
                left2_panel = ft.Container(
                    width=50,
                    padding=ft.padding.only(top=52),
                    content=ft.Column(controls=left2_bets, spacing=2, tight=True,
                                     horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                )
                left_panels.append(left2_panel)
            
            # Combined left side (both columns in a row)
            left_side = ft.Row(controls=left_panels, spacing=2, tight=True) if left_panels else None
            
            # Center: Roulette grid with left side
            middle_row_controls = []
            if left_side:
                middle_row_controls.append(left_side)
            middle_row_controls.append(grid)
            
            middle_row = ft.Row(
                controls=middle_row_controls,
                spacing=2, tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            
            # Bottom sections: columns (34, 35, 36)
            bottom_panels = []
            for section_type, section_controls in bottom_sections:
                if section_type == 'columns':
                    # Columns as compact row - no expand, just 3x50px
                    panel = ft.Row(controls=section_controls, spacing=2, tight=True)
                    bottom_panels.append(panel)
            
            # Combine middle and bottom
            table_layout_controls = [middle_row]
            if bottom_panels:
                table_layout_controls.append(ft.Container(height=4))
                for panel in bottom_panels:
                    table_layout_controls.append(panel)
            
            main_content = ft.Column(controls=table_layout_controls, spacing=0, tight=True,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            # No outside bets, just show roulette grid centered
            main_content = grid
        
        dlg.content = ft.Column(
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(height=4),
                main_content,
                ft.Container(height=8),
                _total_lbl,
            ] + popup_extra,
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("CANCEL", size=13, weight=ft.FontWeight.BOLD),
                on_click=on_cancel, expand=1,
                style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
            ),
            ft.ElevatedButton(
                content=ft.Text("READY", size=13, weight=ft.FontWeight.BOLD),
                on_click=cerrar, expand=1,
                style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)
    
    def _show_inside_bet_popup(self, on_ready_cb):
        """Show popup with roulette grid and outside betting table for inside bets."""
        intersection = self._compute_intersection()

        if self.sniper_mode:
            all_nums    = intersection
            safety_levels = {n: 1 for n in all_nums}
            total_chips = len(all_nums)
        else:
            all_nums: set = set()
            for g in self.grupos_activos:
                g = self._live_norm(g)
                if g in GRUPOS_MAESTROS:
                    all_nums |= GRUPOS_MAESTROS[g]
            safety_levels = self._compute_safety_levels()
            total_chips = sum(v for v in safety_levels.values() if v > 0)
            max_safety = max((v for v in safety_levels.values() if v > 0), default=0)

        # Sniper ON: use GR-based progression for the intersection count
        if self.sniper_mode and self.prog_on and total_chips > 0:
            multi = self._sniper_inside_multi(total_chips)
        else:
            multi = self._current_multi(is_out=False)

        chip_per_num = self.val_fin * multi
        total_cost   = total_chips * chip_per_num

        def grp_color(g):
            if g in {'Z0', 'ZG', 'ZP', 'H'}:                   return C_SEC
            if g in {'W1', 'W2', 'W3'}:                         return C_WAV
            if self._to_display_name(g) in ('1a', '2a', '3a'):  return C_DOC
            if self._to_display_name(g) in ('34', '35', '36'):  return C_COL
            return C_SET

        def grp_label(g):
            """Human-readable label for chip popup header."""
            for sfx, tag in [('_LR','·R'),('_LB','·B'),('_L18','·1-18'),
                              ('_LE','·Even'),('_LO','·Odd'),('_L36','·19-36'),
                              ('_L',''), ('_R','·R'),('_B','·B'),('_18','·1-18'),
                              ('_E','·Even'),('_O','·Odd'),('_36','·19-36')]:
                if g.endswith(sfx):
                    return self._to_display_name(g) + tag
            return g

        title_chips = [
            ft.Container(
                bgcolor=grp_color(g), border_radius=5,
                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                content=ft.Text(grp_label(g), color=ft.Colors.WHITE, size=14,
                                weight=ft.FontWeight.BOLD),
            )
            for g in self.grupos_activos
        ]

        CELL = 25   # zero cell size
        CN   = 50   # number cell size (double, -10%)
        GAP  = 2
        
        # When sniper OFF: use safety_levels to show border colors and multiplier text
        # When sniper ON: yellow border only for intersection
        max_safety = max(safety_levels.values()) if safety_levels else 1
        
        # Color map for safety level borders - higher safety = brighter/more important color
        SAFETY_COLORS = {
            1: '#666666',  # Gray for numbers in only 1 group (low priority)
            2: '#ff00ff',  # Magenta for 2 groups
            3: '#ff6600',  # Orange for 3 groups
            4: '#ffdd00',  # Yellow for 4 groups (high multiplicity)
            5: '#ffff00',  # Bright yellow for 5 groups (max)
        }
        
        def should_show_number(num):
            """Check if number is in the active selection."""
            if self.sniper_mode:
                return num in all_nums
            else:
                return num in safety_levels and safety_levels[num] > 0
        
        def get_border_color(num):
            """Return border color based on safety level."""
            if self.sniper_mode:
                return '#ffdd00'  # Yellow for sniper ON intersection
            else:
                # Sniper OFF: color by safety level
                sl = safety_levels.get(num, 0)
                return SAFETY_COLORS.get(sl, '#ffdd00')
        
        def get_border_width(num):
            """Return border width based on visibility."""
            if self.sniper_mode:
                return 3
            else:
                # Sniper OFF: thicker border for higher safety
                return 2 if safety_levels.get(num, 0) > 1 else 1
        
        def num_bg(num):
            """Original roulette colors: red for ROJOS, black for others, green for zero"""
            if num == 0:
                return '#27ae60'
            else:
                return '#c0392b' if num in ROJOS else '#2c3e50'
        
        def make_cell(num):
            # Always show the number with its roulette color
            is_selected = should_show_number(num)
            
            # Build cell content: number on first line, safety multiplier on second
            cell_controls = [
                ft.Text(str(num), size=14, color=ft.Colors.WHITE,
                       weight=ft.FontWeight.BOLD,
                       text_align=ft.TextAlign.CENTER)
            ]
            
            # Add safety level text only if in selection and has safety > 1
            if is_selected and not self.sniper_mode and safety_levels.get(num, 0) > 1:
                safety = safety_levels[num]
                cell_controls.append(
                    ft.Text(f'{safety}x', size=9, color='#ffdd00',
                           weight=ft.FontWeight.BOLD,
                           text_align=ft.TextAlign.CENTER)
                )
            
            # If selected, add border; if not selected, no border
            if is_selected:
                border_color = get_border_color(num)
                border_width = get_border_width(num)
                border = ft.Border.all(border_width, border_color)
            else:
                border = None
            
            return ft.Container(
                width=CN, height=CN,
                bgcolor=num_bg(num),
                border=border,
                border_radius=6,
                content=ft.Column(
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                    controls=cell_controls,
                ),
            )

        ROW_W = CN * 3 + GAP * 2   # exact pixel width of a number row

        # Zero row: always show with color, add border only if selected
        is_zero_selected = should_show_number(0)
        
        # Zero cell content: number and optional safety multiplier
        zero_controls = [ft.Text("0", size=14, color=ft.Colors.WHITE,
                                 weight=ft.FontWeight.BOLD,
                                 text_align=ft.TextAlign.CENTER)]
        if is_zero_selected and not self.sniper_mode and safety_levels.get(0, 0) > 1:
            safety = safety_levels[0]
            zero_controls.append(
                ft.Text(f'{safety}x', size=9, color='#ffdd00',
                       weight=ft.FontWeight.BOLD,
                       text_align=ft.TextAlign.CENTER)
            )
        
        # Add border only if selected
        if is_zero_selected:
            zero_border_color = get_border_color(0)
            zero_border_width = get_border_width(0)
            zero_border = ft.Border.all(zero_border_width, zero_border_color)
        else:
            zero_border = None
        
        zero_row = ft.Container(
            width=ROW_W, height=CELL * 2,
            bgcolor='#27ae60',
            border=zero_border,
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                controls=zero_controls,
            ),
        )

        num_rows = []
        for i in range(12):
            base = i * 3
            a, b, c = base + 1, base + 2, base + 3
            num_rows.append(
                ft.Row([make_cell(a), make_cell(b), make_cell(c)],
                       spacing=GAP, tight=True)
            )

        grid = ft.Container(
            width=ROW_W,
            content=ft.Column(
                controls=[zero_row] + num_rows,
                spacing=GAP,
                tight=True,
            ),
        )

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def on_cancel(_ev):
            dlg.open = False
            dlg.update()

        def cerrar(_ev):
            dlg.open = False
            dlg.update()
            on_ready_cb()

        _chip_lbl = ft.Text(
            f"${chip_per_num:.2f}/num",
            color='#f1c40f', size=13,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.title = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    wrap=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=title_chips,
                ),
                _chip_lbl,
            ],
        )

        # For inside bets: show total + breakdown with total chips count
        _total_lbl = ft.Text(
            f"Total: ${total_cost:.2f}  ({total_chips} × ${chip_per_num:.2f})",
            color='#ecf0f1', size=12, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )

        # Multiplier picker - always show, but enabled only when progression is OFF
        _pmx_refs: dict = {}

        def _make_pmx(mx):
            def handler(_ev):
                self.fixed_multi = mx
                _c  = self.val_fin * mx
                _t  = total_chips * _c
                _chip_lbl.value  = f"${_c:.2f}/num"
                _total_lbl.value = f"Total: ${_t:.2f}  ({total_chips} × ${_c:.2f})"
                for k, b in _pmx_refs.items():
                    b.style = ft.ButtonStyle(
                        bgcolor='#f39c12' if k == mx else '#3a3a3a',
                        color=ft.Colors.WHITE,
                    )
                    b.update()
                _chip_lbl.update()
                _total_lbl.update()
                self.update_inv_label()
                if self.lbl_inv:
                    self.lbl_inv.update()
            return handler

        mx_row = ft.Row(spacing=3, tight=True)
        for _mx in (1, 2, 3, 4, 5):
            _mb = ft.ElevatedButton(
                content=ft.Text(f"{_mx}x", size=11,
                                weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                expand=True, height=34,
                style=ft.ButtonStyle(
                    bgcolor='#f39c12' if _mx == self.fixed_multi else '#3a3a3a',
                    color=ft.Colors.WHITE,
                ),
                on_click=_make_pmx(_mx),
                disabled=self.prog_on,  # Disabled when progression is ON
            )
            _pmx_refs[_mx] = _mb
            mx_row.controls.append(_mb)

        popup_extra = [
            ft.Container(height=6),
            ft.Text("MULTIPLIER", color='#aaaaaa', size=10,
                    text_align=ft.TextAlign.CENTER),
            mx_row,
        ]

        # Build outside betting table sections - with highlighting DISABLED for inside bets
        # (only highlight grid intersection numbers, not the outside field buttons)
        outside_sections = self._build_outside_bet_sections(highlight=False)
        
        # Extract betting table components for layout
        left1_bets = outside_sections.get('left1', [])     # Dozens
        left2_bets = outside_sections.get('left2', [])     # Filters
        right_bets = outside_sections.get('right', [])     # (empty)
        bottom_sections = outside_sections.get('bottom', [])  # List of (type, controls) tuples
        
        # Build the table layout: left side (2 columns) / grid / bottom
        if left1_bets or left2_bets or bottom_sections:
            # Left side: TWO COLUMNS - Dozens (left1) and Filters (left2)
            # Shift down 52px (zero row 50px + gap 2px) so cells start at row 1
            left_panels = []
            
            if left1_bets:
                left1_panel = ft.Container(
                    width=50,
                    padding=ft.padding.only(top=52),
                    content=ft.Column(controls=left1_bets, spacing=2, tight=True,
                                     horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                )
                left_panels.append(left1_panel)
            
            if left2_bets:
                left2_panel = ft.Container(
                    width=50,
                    padding=ft.padding.only(top=52),
                    content=ft.Column(controls=left2_bets, spacing=2, tight=True,
                                     horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                )
                left_panels.append(left2_panel)
            
            # Combined left side (both columns in a row)
            left_side = ft.Row(controls=left_panels, spacing=2, tight=True) if left_panels else None
            
            # Center: Roulette grid with left side
            middle_row_controls = []
            if left_side:
                middle_row_controls.append(left_side)
            middle_row_controls.append(grid)
            
            middle_row = ft.Row(
                controls=middle_row_controls,
                spacing=2, tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            
            # Bottom sections: columns (34, 35, 36)
            bottom_panels = []
            for section_type, section_controls in bottom_sections:
                if section_type == 'columns':
                    # Columns as compact row - no expand, just 3x50px
                    panel = ft.Row(controls=section_controls, spacing=2, tight=True)
                    bottom_panels.append(panel)
            
            # Combine middle and bottom
            table_layout_controls = [middle_row]
            if bottom_panels:
                table_layout_controls.append(ft.Container(height=4))
                for panel in bottom_panels:
                    table_layout_controls.append(panel)
            
            main_content = ft.Column(controls=table_layout_controls, spacing=0, tight=True,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        else:
            # No outside bets, just show roulette grid centered
            main_content = grid
        
        dlg.content = ft.Column(
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(height=4),
                main_content,
                ft.Container(height=8),
                _total_lbl,
            ] + popup_extra,
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("CANCEL", size=13, weight=ft.FontWeight.BOLD),
                on_click=on_cancel, expand=1,
                style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
            ),
            ft.ElevatedButton(
                content=ft.Text("READY", size=13, weight=ft.FontWeight.BOLD),
                on_click=cerrar, expand=1,
                style=ft.ButtonStyle(bgcolor='#27ae60', color=ft.Colors.WHITE),
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)

    def _activate_bet(self):
        self.activa = True
        self.btn_inv.style = ft.ButtonStyle(bgcolor='#3498db', color=ft.Colors.WHITE,
                                            animation_duration=400)
        self.btn_inv.update()
        self.update_inv_label()
        self.lbl_inv.update()
        self.update_ui()   # immediately reflect pending bet in P/L

        # AI: snapshot the board setup + the combination the player chose, so we
        # can grade it once the spin result is in (see process_number).
        if getattr(self, 'ai_ok', False) and self.grupos_activos:
            try:
                self.current_choice = self.strategy_model.capture_choice(
                    self.history_nums, self.grupos_activos)
                if getattr(self, 'decision_tracker', None):
                    total_cost, _, _ = self._compute_bet()
                    self.current_decision_id = str(uuid.uuid4())
                    self.decision_tracker.record_decision(Decision(
                        decision_id=self.current_decision_id,
                        session_id=str(self.session_id or 0),
                        spin_number=len(self.history_nums),
                        bet_target=self.current_choice['combo'],
                        bet_type='group' if len(self.grupos_activos) > 1 else 'number',
                        bet_amount=total_cost,
                        decision_context={
                            'signature': self.current_choice['signature'],
                            'features': self.current_choice['features'],
                        },
                        source='manual',
                        decision_time=datetime.now(),
                        spin_result=None,
                        outcome='pending',
                        profit_loss=None,
                    ))
            except Exception:
                self.current_choice = None

    def _check_pre_bet_warning(self, on_confirm):
        """Show warning if losing this bet would breach the configured MAX LOSS."""
        if self.stop_loss_triggered or self.banca_inicial <= 0:
            on_confirm()
            return
        # MAX LOSS is dynamic — driven by the value the user set in setup.
        max_loss_frac = getattr(self, 'last_max_loss', 2.0) / 100
        total_cost, _, _ = self._compute_bet()
        potential_bank = self.banca_actual - total_cost
        loss_pct = (self.banca_inicial - potential_bank) / self.banca_inicial
        if loss_pct < max_loss_frac:
            on_confirm()
            return

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def continuar(ev):
            dlg.open = False
            dlg.update()
            on_confirm()

        def volver(ev):
            dlg.open = False
            dlg.update()

        dlg.title = ft.Text(
            "WARNING",
            color='#f39c12', size=16, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        dlg.content = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Divider(color='#444444'),
                ft.Text("If you lose this bet:", color=ft.Colors.WHITE, size=13),
                ft.Container(height=4),
                ft.Text(f"Bank: ${potential_bank:.2f}", color='#ff4444',
                        size=18, weight=ft.FontWeight.BOLD),
                ft.Text(f"Loss: {loss_pct*100:.1f}%  (MAX LOSS {max_loss_frac*100:.1f}%)",
                        color='#ff4444', size=13),
            ],
        )
        dlg.actions = [
            ft.ElevatedButton(
                content=ft.Text("BACK", size=14, weight=ft.FontWeight.BOLD),
                on_click=volver, expand=1,
                style=ft.ButtonStyle(bgcolor='#555555', color=ft.Colors.WHITE),
            ),
            ft.ElevatedButton(
                content=ft.Text("CONTINUE", size=14, weight=ft.FontWeight.BOLD),
                on_click=continuar, expand=1,
                style=ft.ButtonStyle(bgcolor='#e67e22', color=ft.Colors.WHITE),
            ),
        ]
        dlg.actions_alignment = ft.MainAxisAlignment.CENTER
        self.page.show_dialog(dlg)

    def _has_straight(self):
        return any(g in self.GRUPOS_STRAIGHT or g in GRUPOS_LIVE_INSIDE
                   for g in self.grupos_activos)

    def _is_outside_bet_type(self):
        """Check if current selection is an outside bet type (same category only)."""
        if not self.grupos_activos:
            return False
        
        columns = {'34', '35', '36'}
        dozens = {'1a', '2a', '3a'}
        filters = {'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        outside_types = columns | dozens | filters
        
        col_groups = [g for g in self.grupos_activos if g in columns]
        doc_groups = [g for g in self.grupos_activos if g in dozens]
        flt_groups = [g for g in self.grupos_activos if g in filters]
        other_groups = [g for g in self.grupos_activos if g not in outside_types]
        
        types_used = sum([1 for x in [col_groups, doc_groups, flt_groups, other_groups] if x])
        return types_used <= 1

    def _proceed_bet(self):
        # Warning first, then the chip/table setup popup, then activate the bet.
        self._check_pre_bet_warning(
            lambda: self._show_roulette_chip_popup(self._activate_bet)
        )

    def confirmar_manual(self, e=None):
        if not self.grupos_activos:
            return
        # Warning popup before the chip/table setup popup
        self._proceed_bet()

    def auto_invertir_sug(self, grupos):
        self.limpiar_seleccion_visual()
        self.grupos_activos = list(grupos)
        self._refresh_mixer_colors()
        # Warning popup before the chip/table setup popup
        self._proceed_bet()

    # ──────────────────────────────────────────────────────────────────
    # AI COMBINATION COACH
    # ──────────────────────────────────────────────────────────────────
    def _get_ai_info_display(self) -> str:
        """One-line coach text: learning progress, live bet grade, or a tip."""
        if not getattr(self, 'ai_ok', False):
            return "AI: off"
        # In live table mode the RVS colour-regime read is the headline —
        # this is the overlay that actually colours the dozen suggestion.
        if getattr(self, 'live_table_mode', False):
            try:
                txt = regime_status(self.history_nums)
                if getattr(self, 'entry_policy', None):
                    kind = _regime(self.history_nums)[1]
                    txt = ("[ENTER] " if kind in self.entry_policy
                           else "[SKIP] ") + txt
                return "AI 🧠 " + txt
            except Exception:
                pass
        try:
            obs = self.strategy_model.total_observations()
            if obs < MIN_TRAINED_OBS:
                remaining = MIN_TRAINED_OBS - obs
                return (f"AI 🧠 learning your style — {remaining} more graded "
                        f"bets ({obs}/{MIN_TRAINED_OBS})")

            ready = len(self.history_nums) >= 6
            # Live grade of the combination currently selected.
            if ready and self.grupos_activos:
                res = self.strategy_model.score(self.history_nums, self.grupos_activos)
                if res.get('win_prob') is not None:
                    return (f"AI 🧠 {res['combo']}: {res['win_prob']:.0%} "
                            f"· {res['verdict']}")
            # No selection yet → is this board a line-up you usually enter on?
            if ready:
                setup = self.strategy_model.setup_readiness(self.history_nums)
                rec = self.strategy_model.recommend(self.history_nums)
                rec_txt = ""
                if rec and rec.get('win_prob') is not None:
                    rec_txt = f" · {rec['combo']} {rec['win_prob']:.0%}"
                # Adaptive wait hint: how long you usually line up vs now.
                avg_wait = self.strategy_model.typical_wait()
                wait_txt = ""
                if avg_wait is not None:
                    wait_txt = f" · waited {self.spins_since_entry}/~{avg_wait:.0f}"
                if setup.get('status') == 'ok':
                    return f"AI 🧠 {setup['label']}{rec_txt}{wait_txt}"
                if rec_txt:
                    return f"AI 🧠 try{rec_txt.replace(' · ', ' ', 1)}{wait_txt}"
                if wait_txt:
                    return f"AI 🧠 lining up{wait_txt}"
            a = self.strategy_model.analyze()
            if a.get('status') == 'ok':
                return (f"AI 🧠 your combo win rate {a['overall_win_rate']:.0%} "
                        f"over {a['total']} bets")
            return "AI 🧠 active"
        except Exception:
            return "AI 🧠 active"

    def _refresh_ai_label(self):
        """Update the AI coach bar in place (safe to call anytime)."""
        if not getattr(self, 'ai_ok', False):
            return
        lbl = getattr(self, 'lbl_ai_info', None)
        if lbl is None:
            return
        try:
            lbl.value = self._get_ai_info_display()
            lbl.update()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────
    # SUGGESTIONS
    # ──────────────────────────────────────────────────────────────────
    def _make_sug_handler(self, g_par):
        def handler(ev):
            if getattr(self, 'live_table_mode', False):
                # Live mode: just select the group — user presses INVEST to confirm
                self.limpiar_seleccion_visual()
                self.grupos_activos = list(g_par)
                self._refresh_mixer_colors()
                self.update_inv_label()
                if self.lbl_inv:
                    self.lbl_inv.update()
            else:
                self.auto_invertir_sug(g_par)
        return handler

    def actualizar_sugerencias(self):
        vc = getattr(self, 'visible_cats', {k: True for k in ['cols','docs','secs','thirds','wave']})
        all_cats = [
            ('cols',   ['34', '35', '36'],       C_COL),
            ('docs',   ['1a', '2a', '3a'],        C_DOC),
            ('secs',   ['Z0', 'ZG', 'ZP', 'H'],  C_SEC),
            ('thirds', ['T1', 'T2', 'T3'],        C_SET),
            ('wave',   ['W1', 'W2', 'W3'],        C_WAV),
        ]
        cats = [(key, grps, col) for key, grps, col in all_cats if vc.get(key, True)]
        n_cats = max(len(cats), 1)

        if len(self.sliding_window) < 6:
            self.sug_row.controls = [
                ft.ElevatedButton(
                    content=self._txt("×", size=16),
                    expand=True, height=40,
                    style=ft.ButtonStyle(bgcolor='#34495e', color='#7f8c8d'),
                )
                for _ in range(n_cats)
            ]
            self.sug_row.update()
            self._refresh_ai_label()   # keep "watching N/6" counting up
            return

        def _sug_content(label):
            if '+' in label:
                a, b = label.split('+', 1)
                return ft.Column(
                    [ft.Text(a, size=11, weight=ft.FontWeight.BOLD,
                             color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
                     ft.Text(b, size=11, weight=ft.FontWeight.BOLD,
                             color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER)],
                    spacing=0, tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            return self._txt(label, size=12)

        live = getattr(self, 'live_table_mode', False)
        lf   = getattr(self, 'live_filter', None)   # e.g. None, 'R', 'B', '1-18', …

        _FILTER_LABELS = {
            'R': 'R', 'B': 'B', '1-18': '1-18',
            'Even': 'Ev', 'Odd': 'Od', '19-36': '19-36',
        }

        new_btns = []
        PAIR_BLOQUEADO = {'ZG', 'ZP'}
        for key, grupos, color in cats:
            # Live dozens: score by wheel-SECTOR affinity (which dozen's zone best
            # covers the sectors the last 6 spins came from) instead of raw zone
            # membership. Other categories: plain frequency over the last 6 spins.
            def _score(g):
                if live and key == 'docs':
                    return sum(DOZEN_SECTOR_AFFINITY[g].get(SECTOR_OF.get(n), 0.0)
                               for n in self.sliding_window) / 6
                return sum(1 for n in self.sliding_window
                           if n in GRUPOS_MAESTROS[g]) / 6
            stats = sorted(
                [{'g': g, 'p': _score(g)} for g in grupos],
                key=lambda x: x['p'], reverse=True,
            )

            if live and key == 'docs':
                # Top dozen by sector affinity. If the top two are tied, don't
                # guess — show WAIT and let the next spin break the tie naturally.
                tie = (len(stats) > 1 and stats[0]['p'] > 0
                       and abs(stats[0]['p'] - stats[1]['p']) < 1e-9)
                if tie:
                    label = "WAIT"
                    bg    = '#34495e'
                    click = None
                else:
                    top = stats[0]['g']
                    # AI colour overlay: when no manual filter is set, colour the
                    # dozen with the croupier's current colour regime (RVS:
                    # bias / streak / rhythm — see regime_color). Best risk-adjusted
                    # picker under the 1x-2x-3x combo progression + 2% cap
                    # (ai_combo_eval.py). cond_color_for(top, self.history_nums) is
                    # the retired COND fallback, kept for A/B comparison.
                    rcol = None
                    if lf is None and getattr(self, 'ai_ok', False):
                        try:
                            rcol = regime_color(self.history_nums)
                        except Exception:
                            rcol = None
                    eff_filter = lf if lf is not None else rcol
                    actual_g = f'{top}{_DOC_SFX.get(eff_filter, "_L")}'
                    ftag     = _FILTER_LABELS[eff_filter] if eff_filter else ''
                    label    = f'{top}+{ftag}' if ftag else top
                    bg       = color if stats[0]['p'] > 0 else '#34495e'
                    click    = self._make_sug_handler([actual_g])
                new_btns.append(
                    ft.ElevatedButton(
                        content=_sug_content(label),
                        expand=True, height=40,
                        on_click=click,
                        style=ft.ButtonStyle(bgcolor=bg, color=ft.Colors.WHITE),
                    )
                )
                continue

            if live and key == 'cols' and lf:
                # Column pair with active filter applied
                if stats[1]['p'] > stats[2 if len(stats) > 2 else 1]['p']:
                    g_par  = [stats[0]['g'], stats[1]['g']]
                    col_sfx = _COL_SFX.get(lf, '')
                    actual  = [f'{g}{col_sfx}' if col_sfx else g for g in g_par]
                    ftag    = _FILTER_LABELS[lf]
                    label   = f'{g_par[0]}·{ftag}+{g_par[1]}·{ftag}'
                    bg      = color
                    click   = self._make_sug_handler(actual)
                else:
                    label = "---"
                    bg    = '#34495e'
                    click = None
                new_btns.append(
                    ft.ElevatedButton(
                        content=_sug_content(label),
                        expand=True, height=40,
                        on_click=click,
                        style=ft.ButtonStyle(bgcolor=bg, color=ft.Colors.WHITE),
                    )
                )
                continue

            # Standard suggestion logic (pair)
            g_par_candidato = {stats[0]['g'], stats[1]['g']}
            es_par_bloqueado = g_par_candidato == PAIR_BLOQUEADO

            if stats[1]['p'] > stats[2 if len(stats) > 2 else 1]['p'] and not es_par_bloqueado:
                g_par = [stats[0]['g'], stats[1]['g']]
                label = f"{g_par[0]}+{g_par[1]}"
                bg    = color
                click = self._make_sug_handler(g_par)
            else:
                label = "---"
                bg    = '#34495e'
                click = None

            new_btns.append(
                ft.ElevatedButton(
                    content=_sug_content(label),
                    expand=True, height=40,
                    on_click=click,
                    style=ft.ButtonStyle(bgcolor=bg, color=ft.Colors.WHITE),
                )
            )

        self.sug_row.controls = new_btns
        self.sug_row.update()
        self._refresh_ai_label()

    # ──────────────────────────────────────────────────────────────────

    def limpiar_seleccion_visual(self):
        if self.btn_inv:
            self.btn_inv.style = ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.WHITE,
                                                animation_duration=400)
            self.btn_inv.update()
        self.grupos_activos = []
        self._refresh_mixer_colors()
        self.update_inv_label()
        if self.lbl_inv:
            self.lbl_inv.update()

    def update_inv_label(self):
        if not self.lbl_inv:
            return
        if self.activa or self.grupos_activos:
            total, _, num_chips = self._compute_bet()
            is_simple_outside = self._is_simple_outside_bet()
            multi  = self._current_multi(is_simple_outside)
            
            # Outside bets: show only total cost, no chip breakdown
            if is_simple_outside:
                self.lbl_inv.value = f"BET: ${total:.2f}"
            else:
                # Inside bets: show chip breakdown with actual per-number cost
                if self.sniper_mode and self.prog_on and num_chips > 0:
                    effective_multi = self._sniper_inside_multi(num_chips)
                else:
                    effective_multi = multi
                chip_val = self.val_fin * effective_multi
                prog_tag = "" if self.prog_on else f" [{multi}x]"
                self.lbl_inv.value = f"BET: ${total:.2f} ({num_chips}x${chip_val:.4g}){prog_tag}"
        else:
            self.lbl_inv.value = "BET: $0.00"

    def update_ui(self):
        if not self.lbl_bank:
            return
        pl = self.banca_actual - self.banca_inicial
        # When a bet is active, immediately reflect the pending cost in bank + P/L
        displayed_bank = self.banca_actual
        if self.activa:
            pending_cost, _, _ = self._compute_bet()
            pl -= pending_cost
            displayed_bank -= pending_cost
        pl_pct = (pl / self.banca_inicial * 100) if self.banca_inicial != 0 else 0
        self.lbl_bank.value = f"{self.nombre_mesa}  |  {self._fmt_bank(displayed_bank)}"
        self.lbl_pl.value   = f"P/L: {pl_pct:+.1f}%"
        self.lbl_pl.color   = '#2ecc71' if pl >= 0 else '#ff4444'
        self.update_inv_label()
        if self.lbl_inv_pl:
            total_pl = self.inv_other_pl + pl
            self.lbl_inv_pl.value = f"P/L: {total_pl:+.2f}"
            self.lbl_inv_pl.color = '#2ecc71' if total_pl >= 0 else '#ff4444'
        self.page.update()
        self._check_stop_loss()
        self._check_goal_achieved()

    def corregir_ultimo(self, e=None):
        # First press while bet is active: cancel the pending bet, restore display
        if self.activa:
            self.activa = False
            self.limpiar_seleccion_visual()
            self.update_ui()
            return
        if self.history_nums:
            self.history_nums.pop()
            if self.sliding_window:
                self.sliding_window.pop()
            # Predictors are incremental — rebuild them from the corrected history.
            if getattr(self, 'ai_ok', False):
                if getattr(self, 'rhythm_model', None):
                    try:
                        self.rhythm_model.observe_sequence(self.history_nums)
                    except Exception:
                        pass
                if getattr(self, 'pattern_model', None):
                    try:
                        self.pattern_model.observe_sequence(self.history_nums)
                    except Exception:
                        pass
            # Reverse bank
            self.banca_actual -= self.last_bank_delta
            self.last_bank_delta = 0.0
            # Reverse progression only if that bet was running with progression on
            if getattr(self, 'last_prog_state', True):
                if self.last_bet_outside is True:
                    if self.idx_fibo_out > 0:
                        self.idx_fibo_out -= 1
                    if self.nivel_martingala_out > 0:
                        self.nivel_martingala_out -= 1
                elif self.last_bet_outside is False:
                    if self.idx_fibo_in > 0:
                        self.idx_fibo_in -= 1
                    if self.nivel_martingala_in > 0:
                        self.nivel_martingala_in -= 1
            self.last_bet_outside = None
            self.last_prog_state  = True
            self.update_registration_table()
            self.update_ui()


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────
def main(page: ft.Page):
    LinupApp(page)


ft.app(main, assets_dir="assets")
