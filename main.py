import flet as ft
from collections import deque
import sqlite3
import os
import math
import random
from datetime import datetime
import asyncio
import uuid

# AI Learning System imports
from ai_sessions import SessionRepository
from ai_patterns import PatternDetector
from ai_analysis import PatternAnalyzer
from ai_recommendations import RecommendationEngine
from ai_decision_tracker import DecisionTracker, Decision
from ai_learning_engine import LearningEngine
from ai_adaptive_recommender import AdaptiveRecommender

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

        self.page.title      = "LinupOSAI v17.1.0-AI"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor    = '#1a1a1a'
        self.page.padding    = 0
        self.page.scroll     = None
        self.page.on_resized = self._on_resize

        # Desktop-only window sizing (Android/iOS fill screen natively)
        _mobile = self.page.platform in (
            ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
        if not _mobile:
            self.page.window.width      = 420
            self.page.window.height     = 860
            self.page.window.min_width  = 380
            self.page.window.min_height = 700

        self.root = ft.Container(expand=True, bgcolor='#1a1a1a')
        self.page.add(self.root)
        self.page.update()

        self.show_splash()
        self.init_db()
        self.reset_variables()
        self._init_ai_systems()  # Initialize AI learning system
        self.page.run_task(self._after_splash)

    def _init_ai_systems(self):
        """Initialize AI decision tracking and learning system."""
        try:
            # Initialize session repository for pattern storage
            self.session_repo = SessionRepository(db_path=self.db_path)
            
            # Initialize decision tracker for learning
            self.decision_tracker = DecisionTracker(db_path=self.db_path)
            
            # Initialize pattern detection
            self.pattern_detector = PatternDetector(GRUPOS_MAESTROS, WHEEL_NEIGHBORS)
            self.pattern_analyzer = PatternAnalyzer(self.session_repo)
            self.recommendation_engine = RecommendationEngine(
                self.pattern_detector, self.pattern_analyzer, GRUPOS_MAESTROS
            )
            
            # Initialize learning engine
            self.learning_engine = LearningEngine(self.decision_tracker)
            
            # Initialize adaptive recommender
            self.adaptive_recommender = AdaptiveRecommender(
                self.recommendation_engine, self.learning_engine, self.decision_tracker
            )
            
            # Tracking variables
            self.current_decision_id = None
            self.current_spin_number = 0
            self.ai_init_success = True
        except Exception as e:
            print(f"AI initialization warning: {e}")
            self.ai_init_success = False
            # App continues without AI if init fails

    async def _after_splash(self):
        await asyncio.sleep(2.0)
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
                ]:
                    try:
                        conn.execute(_col)
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

    def _get_conn(self):
        if not self.db_path:
            return None
        try:
            return sqlite3.connect(self.db_path)
        except Exception:
            return None

    def _count_total_investments(self) -> int:
        """Count total investments created by user."""
        conn = self._get_conn()
        if not conn:
            return 0
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM investments")
            count = cursor.fetchone()[0] or 0
            return count
        except Exception:
            return 0
        finally:
            conn.close()

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
            return False, "No database connection"
        
        error_msg = None
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
            return True, None
        except Exception as e:
            error_msg = str(e)
            import traceback
            with open("/tmp/linup_session_save_error.log", "a") as f:
                f.write(f"Session save error: {error_msg}\n")
                traceback.print_exc(file=f)
            return False, error_msg
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
        self.val_fin              = 0.10
        self.val_fout             = 0.30
        self.nombre_mesa          = "TABLE 1"
        self.session_id           = None
        self.inv_name             = ""
        self.inv_capital          = 0.0
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
        ('BNB',  'BNB – BNB Chain', 'binancecoin'),
        ('XRP',  'XRP – XRP',       'ripple'),
        ('ADA',  'ADA – Cardano',   'cardano'),
        ('DOGE', 'DOGE – Dogecoin', 'dogecoin'),
        ('USDT', 'USDT – Tether',   None),
        ('USDC', 'USDC – USD Coin', None),
    ]

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
                        ft.Text("LinupOSAI", color='#3498db', size=64,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(height=8),
                        ft.Text("v17.1.0-AI", color='#7f8c8d', size=18),
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
            name_fields, bank_fields, rows = [], [], []
            for i in range(num_tables):
                nf = ft.TextField(
                    value=f"TABLE {i + 1}",
                    bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
                    expand=2,
                )
                bf = ft.TextField(
                    value=str(bank_per_table),
                    bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
                    keyboard_type=ft.KeyboardType.NUMBER, expand=1,
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
                ft.Row(controls=[
                    ft.Text("TABLE NAME", color='#7f8c8d', size=12, expand=2),
                    ft.Text("BANK ($)", color='#7f8c8d', size=12, expand=1),
                ]),
                ft.Container(height=4),
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
                    value="0.0004", label="= tokens",
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
                            ct    = float(ctf.value or 0.0004)
                            cpt   = cc / ct if ct > 0 else 0
                            chips = int(bal * cpt)
                            usd   = bal * price
                            clbl.value = f"{chips:,} chips  |  ${usd:,.2f}"
                        except Exception:
                            clbl.value = "—"
                        try:
                            clbl.update()
                        except Exception:
                            pass
                    return update

                upd = _make_updater(bal_f, price_f, cc_f, ct_f, chip_lbl)
                bal_f.on_change   = upd
                price_f.on_change = upd
                cc_f.on_change    = upd
                ct_f.on_change    = upd

                def _make_fetch_handler(dd, pf, slbl, upd_fn):
                    async def _do_fetch():
                        sym = dd.value or 'SOL'
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

                fetch_handler = _make_fetch_handler(token_dd, price_f, status_lbl, upd)
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
                total_usd   = 0.0
                for idx, (dd, bf, pf, ccf, ctf) in enumerate(chip_rows_refs):
                    t_name = dd.value or f"TABLE {idx + 1}"
                    try:
                        bal   = float(bf.value  or 0)
                        price = float(pf.value  or 0)
                        cc    = float(ccf.value or 10)
                        ct    = float(ctf.value or 0.0004)
                        cpt   = cc / ct if ct > 0 else 0
                        chips = round(bal * cpt, 2)
                    except Exception:
                        bal = price = cpt = chips = 0.0
                    tables_data.append((t_name, chips, t_name, bal, price, cpt))
                    total_usd += bal * price
                self._create_investment(inv_name, total_usd, tables_data, 'CHIPS')

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
                ft.Container(height=20),
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
        error_msg = None
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
            except Exception as e:
                error_msg = str(e)
                import traceback
                with open("/tmp/linup_investment_error.log", "a") as f:
                    f.write(f"Investment creation error: {error_msg}\n")
                    traceback.print_exc(file=f)
                inv_id = None
            finally:
                conn.close()
        
        # Show result to user
        if inv_id:
            # Show success confirmation
            dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
            def go_to_dashboard(e):
                dlg.open = False
                dlg.update()
                self.show_investment_dashboard(inv_id)
            
            dlg.title = ft.Text("✅ Investment Created", color='#2ecc71', 
                               weight=ft.FontWeight.BOLD)
            dlg.content = ft.Column(tight=True, controls=[
                ft.Text(f"Investment '{inv_name}' saved successfully!", 
                       color=ft.Colors.WHITE),
                ft.Container(height=8),
                ft.Text(f"Capital: ${capital:,.2f}", 
                       color='#2ecc71', weight=ft.FontWeight.BOLD, size=13),
                ft.Container(height=12),
                ft.Text(f"Tables: {len(tables_data)}", 
                       color='#cccccc', size=11),
            ])
            dlg.actions = [
                ft.ElevatedButton("Start Trading", on_click=go_to_dashboard, 
                                style=ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.BLACK),
                                expand=True)
            ]
            dlg.actions_alignment = ft.MainAxisAlignment.CENTER
            self.page.show_dialog(dlg)
        else:
            if error_msg:
                dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
                def close_dlg(e):
                    dlg.open = False
                    dlg.update()
                    self.show_main_menu()
                
                dlg.title = ft.Text("Error Creating Investment", color='#ff4444', 
                                   weight=ft.FontWeight.BOLD)
                dlg.content = ft.Column(tight=True, controls=[
                    ft.Text("Investment could not be saved:", color=ft.Colors.WHITE),
                    ft.Container(height=8),
                    ft.Text(error_msg, color='#ff9999', size=12, 
                           text_align=ft.TextAlign.CENTER),
                    ft.Container(height=12),
                    ft.Text("Check that database is writable.", 
                           color='#cccccc', size=11),
                ])
                dlg.actions = [
                    ft.ElevatedButton("Back", on_click=close_dlg, 
                                    style=ft.ButtonStyle(bgcolor='#555', color=ft.Colors.WHITE))
                ]
                dlg.actions_alignment = ft.MainAxisAlignment.CENTER
                self.page.show_dialog(dlg)
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

                for i, (mesa_name, init_bank, wins, losses, last_bank) in enumerate(all_tdata):
                    # P/L from all OTHER tables (used in game screen bar)
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

                    def make_loader(m, bk, has_hist, opl, itype=db_inv_type):
                        def loader(ev):
                            self.reset_variables()
                            self.current_investment_id = investment_id
                            self.inv_name      = inv_name
                            self.inv_capital   = float(inv_capital)
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

                total_pl   = sum(d[4] - d[1] for d in all_tdata)
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
                                        f"{inv_name}  |  ${inv_capital:.2f}",
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
    # ACTUAL GROWTH GRAPH
    # ──────────────────────────────────────────────────────────────────
    def show_actual_graph_view(self, investment_id: int, inv_name: str,
                               inv_capital: float, inv_type: str = 'FIAT',
                               mesa_usd_rate: dict = None, usd_capital: float = 0.0):
        import flet.canvas as cv, inspect
        # cv.Text uses 'value' in Flet ≥0.83, 'text' in older versions
        _tv = ('value' if 'value' in inspect.signature(cv.Text.__init__).parameters
               else 'text')

        def _cv_text(x, y, txt, color='#888888', size=8):
            return cv.Text(x=x, y=y,
                           style=ft.TextStyle(color=color, size=size),
                           **{_tv: str(txt)})

        sessions = []  # list of (profit, mesa)
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT profit, mesa FROM compound_sessions "
                    "WHERE investment_id=? ORDER BY id",
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

        # Always display in USD for the graph
        def _fv(v):
            return f"${v:.2f}"

        # Build (x, y) pairs — point 0 is starting capital
        start_y = usd_capital if chips_mode else float(inv_capital)
        pts = [(0, start_y)]
        running = start_y
        for profit, mesa in sessions:
            delta = (profit * mesa_usd_rate.get(mesa, 0.0)) if chips_mode else profit
            running += delta
            pts.append((len(pts), running))

        controls: list = [
            ft.ElevatedButton(
                "←  BACK", on_click=go_back,
                style=ft.ButtonStyle(bgcolor='#c0392b', color=ft.Colors.WHITE),
            ),
            ft.Container(height=12),
            ft.Text(f"{inv_name}  —  ACTUAL GROWTH",
                    color='#3498db', size=14, weight=ft.FontWeight.BOLD),
            ft.Text(f"Start: {_fv(start_y)}  ·  {len(sessions)} sessions",
                    color='#7f8c8d', size=12),
            ft.Container(height=10),
        ]

        if len(pts) < 2:
            controls.append(
                ft.Text("No sessions saved yet — play and save sessions first.",
                        color='#7f8c8d', size=12,
                        text_align=ft.TextAlign.CENTER)
            )
        else:
            yvals  = [p[1] for p in pts]
            data_range = max(max(yvals) - min(yvals), abs(inv_capital * 0.01), 1.0)
            mid    = (max(yvals) + min(yvals)) / 2
            half   = data_range * 1.5 / 2
            min_y  = mid - half
            max_y  = mid + half
            y_span = max_y - min_y
            max_xi = len(pts) - 1
            line_color = '#2ecc71' if running >= inv_capital else '#ff4444'

            # Canvas layout constants (px)
            ML, MR, MT, MB = 62, 8, 8, 22
            CH = 270  # total canvas height

            def _build_shapes(cw):
                pw = max(cw - ML - MR, 1.0)
                ph = float(CH - MT - MB)

                def sx(xi): return ML + (xi / max_xi) * pw if max_xi else ML
                def sy(yv): return MT + (1.0 - (yv - min_y) / y_span) * ph

                shapes = []

                # Background
                shapes.append(cv.Rect(
                    x=ML, y=MT, width=pw, height=ph,
                    paint=ft.Paint(color='#1a2535',
                                   style=ft.PaintingStyle.FILL)
                ))

                # Horizontal grid lines + Y labels
                for i in range(5):
                    gy  = MT + i * ph / 4
                    val = max_y - i * y_span / 4
                    shapes.append(cv.Line(
                        x1=ML, y1=gy, x2=ML + pw, y2=gy,
                        paint=ft.Paint(color='#2a2a2a', stroke_width=1)
                    ))
                    shapes.append(_cv_text(0, gy - 6, _fv(val)))

                # Break-even dashed line
                bey = sy(inv_capital)
                if MT <= bey <= MT + ph:
                    x = ML
                    while x < ML + pw:
                        shapes.append(cv.Line(
                            x1=x, y1=bey,
                            x2=min(x + 4, ML + pw), y2=bey,
                            paint=ft.Paint(color='#666666', stroke_width=1)
                        ))
                        x += 8

                # Fill under data line
                fill = [cv.Path.MoveTo(x=sx(pts[0][0]), y=sy(pts[0][1]))]
                for xi, yi in pts[1:]:
                    fill.append(cv.Path.LineTo(x=sx(xi), y=sy(yi)))
                fill.append(cv.Path.LineTo(x=sx(pts[-1][0]), y=MT + ph))
                fill.append(cv.Path.LineTo(x=sx(0), y=MT + ph))
                fill.append(cv.Path.Close())
                shapes.append(cv.Path(
                    elements=fill,
                    paint=ft.Paint(color=line_color + '33',
                                   style=ft.PaintingStyle.FILL)
                ))

                # Data line
                line = [cv.Path.MoveTo(x=sx(pts[0][0]), y=sy(pts[0][1]))]
                for xi, yi in pts[1:]:
                    line.append(cv.Path.LineTo(x=sx(xi), y=sy(yi)))
                shapes.append(cv.Path(
                    elements=line,
                    paint=ft.Paint(color=line_color, stroke_width=2,
                                   style=ft.PaintingStyle.STROKE)
                ))

                # Dots (only when few sessions)
                if len(pts) <= 25:
                    for xi, yi in pts:
                        shapes.append(cv.Circle(
                            x=sx(xi), y=sy(yi), radius=3,
                            paint=ft.Paint(color=line_color,
                                           style=ft.PaintingStyle.FILL)
                        ))

                # X-axis labels
                x_step = max(1, round(max_xi / 5))
                for i in range(0, len(pts), x_step):
                    shapes.append(_cv_text(sx(i) - 4, MT + ph + 4, str(i)))

                # Axes border
                shapes.append(cv.Line(
                    x1=ML, y1=MT, x2=ML, y2=MT + ph,
                    paint=ft.Paint(color='#444444', stroke_width=1)
                ))
                shapes.append(cv.Line(
                    x1=ML, y1=MT + ph, x2=ML + pw, y2=MT + ph,
                    paint=ft.Paint(color='#444444', stroke_width=1)
                ))

                return shapes

            canvas_ctrl = cv.Canvas(
                shapes=[],
                expand=True,
                height=CH,
                resize_interval=0,
                on_resize=lambda e: (
                    setattr(canvas_ctrl, 'shapes', _build_shapes(e.width))
                    or canvas_ctrl.update()
                ),
            )

            controls.append(
                ft.Container(
                    bgcolor='#0d0d0d', border_radius=8,
                    padding=0,
                    content=canvas_ctrl,
                    height=CH,
                )
            )

            # Summary bar
            final_pl = running - start_y
            pl_pct   = (final_pl / start_y * 100) if start_y else 0
            pl_sign  = "+" if final_pl >= 0 else ""
            pl_col   = '#2ecc71' if final_pl >= 0 else '#ff4444'
            controls += [
                ft.Container(height=10),
                ft.Container(
                    bgcolor='#1e2d1e' if final_pl >= 0 else '#2d1e1e',
                    padding=10, border_radius=6,
                    content=ft.Text(
                        f"Current: {_fv(running)}  |  "
                        f"P/L: {pl_sign}{_fv(final_pl)} ({pl_sign}{pl_pct:.1f}%)",
                        color=pl_col, size=13, weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ),
            ]

        self._set_view(
            ft.Container(
                bgcolor='#1a1a1a', expand=True, padding=20,
                content=ft.ListView(expand=True, controls=controls),
            )
        )

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
                    "SELECT id, name, capital FROM investments ORDER BY id DESC"
                )
                for inv_id, name, capital in cursor.fetchall():
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
                        txt = (f"{name}  |  ${capital:.2f}"
                               f"  |  {n_tables} tables  |  EFF:{eff:.0f}%")
                    else:
                        txt = f"{name}  |  ${capital:.2f}  |  {n_tables} tables"

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
        tables_data = []  # list of (table_id, mesa_name, init_bank)
        conn = self._get_conn()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, capital FROM investments WHERE id=?", (inv_id,)
                )
                row = cursor.fetchone()
                if row:
                    inv_name, inv_capital = row
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
            label="Capital ($)", value=str(inv_capital),
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
        sug_bank     = self.banca_actual
        sug_max_loss = 33.0    # default: 3 losses = 33% bank

        def _round_up_chip(val):
            if val <= 0:
                return 0.0
            if val < 10:
                return math.floor(round(val * 10, 8)) / 10
            return float(math.floor(val / 10) * 10)

        sug_fin  = _round_up_chip(sug_bank * (sug_max_loss / 100) / 225)
        sug_fout = sug_fin * 10

        def _f(val):
            try:
                return float(val)
            except Exception:
                return 0.0

        def _chips_from(bk, loss_pct):
            """Return (fin, fout) given bank and max-loss %."""
            factor = bk * max(loss_pct, 0) / 100
            fin = _round_up_chip(factor / 225)
            return fin, fin * 10

        def _chip_label_text(chip_val, bank, multiplier_sum, max_loss_pct):
            """chip_val × multiplier_sum = total 3-loss cost; % relative to bank"""
            try:
                pct      = (chip_val / bank * 100) if bank > 0 else 0
                loss     = chip_val * multiplier_sum
                loss_pct = (loss / bank * 100) if bank > 0 else 0
                return (f"({pct:.4f}% bank · 3 losses = ${loss:.2f}"
                        f" = {loss_pct:.1f}% / {max_loss_pct:.0f}% bank)")
            except Exception:
                return ""

        self.fin_label  = ft.Text(
            f"CHIP IN {_chip_label_text(sug_fin,  sug_bank, 225, sug_max_loss)}:",
            color=ft.Colors.WHITE,
        )
        self.fout_label = ft.Text(
            f"CHIP OUT {_chip_label_text(sug_fout, sug_bank, 26,  sug_max_loss)}:",
            color=ft.Colors.WHITE,
        )

        def _refresh_labels(bank, fin_val, fout_val):
            ml = _f(self.max_loss_input.value)
            self.fin_label.value  = f"CHIP IN {_chip_label_text(fin_val,  bank, 225, ml)}:"
            self.fout_label.value = f"CHIP OUT {_chip_label_text(fout_val, bank, 26,  ml)}:"
            try:
                self.fin_label.update()
                self.fout_label.update()
            except Exception:
                pass

        def _recalc(e=None):
            try:
                bk  = _f(self.banca_input.value)
                ml  = _f(self.max_loss_input.value)
                fin_val, fout_val = _chips_from(bk, ml)
                self.fin_input.value  = str(fin_val)
                self.fout_input.value = str(fout_val)
                self.fin_input.update()
                self.fout_input.update()
                _refresh_labels(bk, fin_val, fout_val)
            except Exception:
                pass

        def _on_bank_change(e):
            _recalc()

        self.max_loss_input = ft.TextField(
            value=str(sug_max_loss),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda e: _recalc(),
        )

        self.fin_input = ft.TextField(
            value=str(sug_fin),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda _e: _refresh_labels(
                _f(self.banca_input.value),
                _f(self.fin_input.value),
                _f(self.fout_input.value),
            ),
        )
        self.fout_input = ft.TextField(
            value=str(sug_fout),
            bgcolor=ft.Colors.WHITE, color=ft.Colors.BLACK, height=45,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=lambda _e: _refresh_labels(
                _f(self.banca_input.value),
                _f(self.fin_input.value),
                _f(self.fout_input.value),
            ),
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
                        ft.Text("BANK:", color=ft.Colors.WHITE),
                        self.banca_input,
                        ft.Text("MAX LOSS %:", color=ft.Colors.WHITE),
                        self.max_loss_input,
                        self.fin_label,
                        self.fin_input,
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
            self.nombre_mesa   = str(self.table_input.value).upper() or "TABLE 1"
            self.banca_inicial = float(self.banca_input.value or 100)
            self.banca_actual  = self.banca_inicial
            self.val_fin       = float(self.fin_input.value)  if self.fin_input.value  else round(self.banca_inicial / 225, 6)
            self.val_fout      = float(self.fout_input.value) if self.fout_input.value else round(self.banca_inicial / 26, 4)
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
    # FINALIZE SESSION
    # ─────────────────────────────────────────────────────────────────
    def finalizar_sesion(self, e=None):
        profit   = round(self.banca_actual - self.banca_inicial, 2)
        pl_pct   = (profit / self.banca_inicial * 100) if self.banca_inicial != 0 else 0
        positivo = profit >= 0
        color    = '#2ecc71' if positivo else '#ff4444'
        signo    = "+" if positivo else ""

        ok, err_msg    = self._guardar_sesion()
        self._update_table_stats(profit >= 0)
        guardado_txt   = "Saved to history" if ok else f"Error: {err_msg}"
        guardado_color = '#2ecc71' if ok else '#ff4444'

        dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')

        def saltar(ev):
            dlg.open = False
            dlg.update()
            self._go_home()

        def guardar(ev):
            ok, err = self._save_compound_session()
            dlg.open = False
            dlg.update()
            
            if not ok:
                # Show error dialog
                err_dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
                def close_err(e):
                    err_dlg.open = False
                    err_dlg.update()
                    self._go_home()
                
                err_dlg.title = ft.Text("⚠️ Save Error", color='#ff4444', weight=ft.FontWeight.BOLD)
                err_dlg.content = ft.Column(tight=True, controls=[
                    ft.Text("Session could not be saved:", color=ft.Colors.WHITE),
                    ft.Container(height=8),
                    ft.Text(err or "Unknown error", color='#ff9999', size=11),
                ])
                err_dlg.actions = [
                    ft.ElevatedButton("Back", on_click=close_err,
                                    style=ft.ButtonStyle(bgcolor='#555', color=ft.Colors.WHITE),
                                    expand=True)
                ]
                err_dlg.actions_alignment = ft.MainAxisAlignment.CENTER
                self.page.show_dialog(err_dlg)
            else:
                # Record investment outcome for learning
                if self.current_investment_id and self.learning_engine and hasattr(self.learning_engine.tracker, 'conn'):
                    try:
                        self.learning_engine.record_investment_outcome(
                            investment_id=self.current_investment_id,
                            profit_loss=profit,
                            capital=self.banca_inicial,
                            mesa_types=[self.nombre_mesa]
                        )
                    except Exception:
                        pass  # Learning failure shouldn't affect session save
                
                # Show success
                suc_dlg = ft.AlertDialog(modal=True, bgcolor='#1e1e1e')
                def close_suc(e):
                    suc_dlg.open = False
                    suc_dlg.update()
                    self._go_home()
                
                suc_dlg.title = ft.Text("✅ Session Saved", color='#2ecc71', weight=ft.FontWeight.BOLD)
                suc_dlg.content = ft.Column(tight=True, controls=[
                    ft.Text("Investment session registered successfully!", color=ft.Colors.WHITE),
                    ft.Container(height=8),
                    ft.Text(f"P/L: {signo}{self._fmt_bank(profit)} ({signo}{pl_pct:.1f}%)",
                           color=color, weight=ft.FontWeight.BOLD),
                ])
                suc_dlg.actions = [
                    ft.ElevatedButton("Back to Dashboard", on_click=close_suc,
                                    style=ft.ButtonStyle(bgcolor='#2ecc71', color=ft.Colors.BLACK),
                                    expand=True)
                ]
                suc_dlg.actions_alignment = ft.MainAxisAlignment.CENTER
                self.page.show_dialog(suc_dlg)

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
        
        # ── AI Info display ────────────────────────────────────────────
        self.lbl_ai_info = ft.Text(
            self._get_ai_info_display(),
            color='#9b59b6', weight=ft.FontWeight.BOLD, size=10,
            text_align=ft.TextAlign.CENTER,
        )
        ai_bar = ft.Container(
            bgcolor='#2a2a3e', padding=4,
            content=self.lbl_ai_info,
        ) if self.ai_init_success else None

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
                'B': '#888888',      # Black - gray when not pressed
                '1-18': '#888888',   # Gray
                'Even': '#888888',   # Gray
                'Odd': '#888888',    # Gray
                '19-36': '#888888',  # Gray
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
                        stats_bar, prog_bar, sug_bar,
                    ] + ([ai_bar] if ai_bar else []) + ([rb_bar] if rb_bar else []) + [
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

    def _group_cost(self, g):
        if g in self.GRUPOS_STRAIGHT or g in GRUPOS_LIVE_INSIDE:
            return self.val_fin * len(GRUPOS_MAESTROS[g])
        return self.val_fout

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
            return self.PROG_2_OUT[idx] // max(n, 1)   # per-group: [1,3,9,27] for n=2
        if n == 1:
            return PROG_FIBO[self.idx_fibo_in]
        return self.PROG_2_IN[min(self.nivel_martingala_in, len(self.PROG_2_IN) - 1)]

    def _compute_bet(self):
        n = len(self.grupos_activos)
        if n == 0:
            return 0.0, 0.0

        # Define outside bet types
        columns = {'34', '35', '36'}
        dozens = {'1a', '2a', '3a'}
        filters = {'R', 'B', 'Even', 'Odd', '1-18', '19-36'}
        outside_types = columns | dozens | filters
        
        # Categorize active groups
        col_groups = [g for g in self.grupos_activos if g in columns]
        doc_groups = [g for g in self.grupos_activos if g in dozens]
        flt_groups = [g for g in self.grupos_activos if g in filters]
        other_groups = [g for g in self.grupos_activos if g not in outside_types]
        
        # Count how many types are represented
        types_used = sum([1 for x in [col_groups, doc_groups, flt_groups, other_groups] if x])
        
        total = 0.0
        win_payout = 0.0
        
        # If only ONE type is used, it's an outside bet
        if types_used <= 1:
            is_out = True
            multi_out = self._current_multi(is_out)
            n_out = len(self.grupos_activos)
            if n_out == 1:
                total = self.val_fout * multi_out
                win_payout = total * 3
            else:
                total = self.val_fout * multi_out * n_out
                win_payout = self.val_fout * multi_out * 3
        else:
            # Mixed types = inside bet with intersection
            multi_in = self._current_multi(is_out=False)
            
            # Calculate all numbers covered by each type
            type_nums = []
            
            if col_groups:
                col_nums = set()
                for g in col_groups:
                    col_nums |= GRUPOS_MAESTROS[g]
                type_nums.append(col_nums)
            
            if doc_groups:
                doc_nums = set()
                for g in doc_groups:
                    doc_nums |= GRUPOS_MAESTROS[g]
                type_nums.append(doc_nums)
            
            if flt_groups:
                flt_nums = set()
                for g in flt_groups:
                    flt_nums |= GRUPOS_MAESTROS[g]
                type_nums.append(flt_nums)
            
            if other_groups:
                oth_nums = set()
                for g in other_groups:
                    if g in GRUPOS_MAESTROS:
                        oth_nums |= GRUPOS_MAESTROS[g]
                type_nums.append(oth_nums)
            
            # Intersection of all types
            if type_nums:
                intersection = type_nums[0]
                for nums_set in type_nums[1:]:
                    intersection &= nums_set
            else:
                intersection = set()
            
            num_chips = len(intersection) if intersection else 1
            total = self.val_fin * num_chips * multi_in
            win_payout = self.val_fin * 36 * multi_in
        
        return total, win_payout

    def process_number(self, e):
        try:
            btn = e.control
            try:
                self._flash_button(btn, btn.style.bgcolor, 300)
            except Exception:
                pass

            num = int(e.control.data)
            if self.activa:
                n                     = len(self.grupos_activos)
                is_out                = self._is_outside()
                self.last_bet_outside = is_out
                self.last_prog_state  = self.prog_on   # save for undo
                total_cost, win_py    = self._compute_bet()
                self.banca_actual    -= total_cost

                # Sniper mode: check intersection only; regular mode: check if in any group
                is_win = False
                if self.sniper_mode and not is_out:
                    intersection = self._compute_intersection()
                    is_win = num in intersection
                else:
                    is_win = any(num in GRUPOS_MAESTROS[g] for g in self.grupos_activos)

                if is_win:
                    self.banca_actual += win_py
                    self.last_bank_delta = win_py - total_cost
                    # Only reset progression counters when progression is active
                    if self.prog_on:
                        if is_out:
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
                            if is_out:
                                if self.idx_fibo_out < len(PROG_FIBO) - 1:
                                    self.idx_fibo_out += 1
                            else:
                                if self.idx_fibo_in < len(PROG_FIBO) - 1:
                                    self.idx_fibo_in += 1
                        else:
                            if is_out:
                                self.nivel_martingala_out += 1
                            else:
                                self.nivel_martingala_in += 1
                self.activa         = False
                self.grupos_activos = []
                self.limpiar_seleccion_visual()
                
                # Record decision outcome for learning system
                if self.ai_init_success and self.current_decision_id:
                    try:
                        outcome = 'win' if is_win else 'loss'
                        profit_loss = self.last_bank_delta
                        self.decision_tracker.record_outcome(
                            decision_id=self.current_decision_id,
                            spin_result=num,
                            outcome=outcome,
                            profit_loss=profit_loss
                        )
                        self.current_decision_id = None
                    except Exception:
                        pass  # Silently fail if tracking fails
            else:
                if self.free_spin_mode:
                    # Red + Black: net 0 unless 0 falls (lose both)
                    delta = -2 * self.val_fin if num == 0 else 0.0
                else:
                    delta = self.val_fin * (1 if num in ROJOS else -1)
                self.banca_actual      += delta
                self.last_bank_delta    = delta
                self.last_bet_outside   = None

            self.history_nums.append(num)
            self.sliding_window.append(num)
            self.update_registration_table()   # buffers row/header updates
            self.actualizar_sugerencias()       # buffers sug_row update
            self.update_ui()                    # single page.update() flushes all
        except Exception as _err:
            import traceback
            with open("/tmp/linup_error.log", "a") as _f:
                _f.write(f"[process_number] {type(_err).__name__}: {_err}\n")
                traceback.print_exc(file=_f)

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
        for g, btn in self.mixer_btns.items():
            base_color = btn.data['color']
            if g in active_display:
                # Selected: yellow text (#ffdd00) + bright background
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

    def _compute_safety_levels(self):
        """Compute safety level for each number (count of groups that contain it).
        Returns dict {num: count} where count is 0-5."""
        levels = {}
        # Use ALL active groups, not just straight ones
        active_groups = [g for g in self.grupos_activos
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
        active_groups = [g for g in self.grupos_activos
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
            else:  # R, B, Even, Odd, 1-18, 19-36
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

    def _show_roulette_chip_popup(self, on_ready_cb):
        """Show vertical roulette chip placement popup for all active straight groups.
        Calls on_ready_cb() when the user dismisses with READY.
        If sniper_mode: show only intersection of all groups
        If not sniper_mode: show safety levels (1-5 based on group count per number)"""
        multi        = self._current_multi(is_out=False)
        chip_per_num = self.val_fin * multi

        # Sniper mode: show intersection only (no fallback)
        if self.sniper_mode:
            intersection = self._compute_intersection()
            all_nums = intersection  # Show only intersection, never fallback to union
            safety_levels = {n: 1 for n in all_nums}  # all shown numbers have same "safety"
            min_safety_filter = 1
        else:
            # Show all possible numbers from all active groups with multiplicity
            all_nums: set = set()
            for g in self.grupos_activos:
                if g in GRUPOS_MAESTROS:
                    all_nums |= GRUPOS_MAESTROS[g]
            safety_levels = self._compute_safety_levels()
            min_safety_filter = 0  # Show all numbers, no filtering
            # Calculate max safety level for highlighting with yellow in sniper OFF mode
            max_safety = max(safety_levels.values()) if safety_levels else 0

        total_cost, _ = self._compute_bet()   # exact amount that will hit the bank
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

        # Multiplicity colors for border: 1x=red, 2x=orange, 3x=cyan, 4x=blue; max level always yellow
        SAFETY_COLORS = {
            1: '#c0392b',    # deep red - lowest multiplicity
            2: '#e67e22',    # orange
            3: '#1abc9c',    # cyan/turquoise - distinctive
            4: '#3498db',    # bright blue
            5: '#3498db',    # bright blue (max is yellow, so this is fallback)
        }
        
        def num_bg(num):
            """Original roulette colors: red for ROJOS, black for others, green for zero"""
            if num == 0:
                return '#27ae60'
            else:
                return '#c0392b' if num in ROJOS else '#2c3e50'
        
        def get_border_color(num, safety):
            """Border color based on safety level or sniper mode"""
            if self.sniper_mode:
                # In sniper mode: yellow border for intersection, dim gray for non-intersection
                return '#ffdd00' if (num in all_nums) else '#444'
            else:
                # Show safety level color as border; gray if doesn't meet filter
                if safety >= min_safety_filter:
                    return SAFETY_COLORS.get(safety, '#888')
                else:
                    return '#222'  # very dark for filtered-out numbers

        def make_cell(num):
            # Cell is lit if in intersection (sniper mode) or always when sniper OFF
            if self.sniper_mode:
                lit = num in all_nums
                border_color = '#ffdd00' if lit else '#444'
            else:
                # Sniper OFF: show all numbers with multiplicity label
                lit = True  # always lit in sniper OFF
                safety = safety_levels.get(num, 0)
                # Use yellow for the highest multiplicity level, otherwise use SAFETY_COLORS
                if safety == max_safety and max_safety > 0:
                    border_color = '#ffdd00'
                else:
                    border_color = SAFETY_COLORS.get(safety, '#888')
            
            # Add multiplicity label when sniper OFF
            multiplicity_text = None
            if not self.sniper_mode:
                safety = safety_levels.get(num, 0)
                if safety > 0:
                    multiplicity_text = f"{safety}x"
            
            content_controls = [ft.Text(str(num), size=14, color=ft.Colors.WHITE,
                                      weight=ft.FontWeight.BOLD,
                                      text_align=ft.TextAlign.CENTER)]
            if multiplicity_text:
                content_controls.append(ft.Text(multiplicity_text, size=10, color=ft.Colors.WHITE,
                                              weight=ft.FontWeight.BOLD,
                                              text_align=ft.TextAlign.CENTER))
            
            return ft.Container(
                width=CN, height=CN,
                bgcolor=num_bg(num),
                border=ft.Border.all(3 if lit else 0.5, border_color),
                border_radius=6,
                content=ft.Column(
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=0,
                    controls=content_controls,
                ),
            )


        ROW_W = CN * 3 + GAP * 2   # exact pixel width of a number row

        # Zero row: green background, border color based on mode
        if self.sniper_mode:
            zero_lit = 0 in all_nums
            zero_border_color = '#ffdd00' if zero_lit else '#444'
            zero_content = ft.Text("0", size=14, color=ft.Colors.WHITE,
                                  weight=ft.FontWeight.BOLD,
                                  text_align=ft.TextAlign.CENTER)
        else:
            # Sniper OFF: always lit, show multiplicity
            zero_lit = True
            zero_safety = safety_levels.get(0, 0)
            # Use yellow for the highest multiplicity level, otherwise use SAFETY_COLORS
            if zero_safety == max_safety and max_safety > 0:
                zero_border_color = '#ffdd00'
            else:
                zero_border_color = SAFETY_COLORS.get(zero_safety, '#888')
            zero_content = ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                controls=[ft.Text("0", size=14, color=ft.Colors.WHITE,
                                 weight=ft.FontWeight.BOLD),
                         ft.Text(f"{zero_safety}x", size=10, color=ft.Colors.WHITE,
                                weight=ft.FontWeight.BOLD) if zero_safety > 0 else ft.Container(height=0)]
            )
        
        zero_row = ft.Container(
            width=ROW_W, height=CELL * 2,
            bgcolor='#27ae60',
            border=ft.Border.all(3 if zero_lit else 0.5, zero_border_color),
            border_radius=6,
            alignment=ft.Alignment(0, 0),
            content=zero_content,
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

        dlg.title = ft.Column(
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=title_chips + [ft.Container(width=6)] + [
                        ft.Text(f"${chip_per_num:.2f}/num",
                                color='#f1c40f', size=13,
                                weight=ft.FontWeight.BOLD),
                    ],
                ),
            ],
        )
        _total_lbl = ft.Text(
            f"Total: ${total_cost:.2f}  ({len(all_nums)} × ${chip_per_num:.2f})",
            color='#ecf0f1', size=12, weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        _chip_lbl = dlg.title.controls[0].controls[-1]  # the $/num text in title row

        # When progression is OFF, show live multiplier picker inside the popup
        popup_extra: list = []
        if not self.prog_on:
            _pmx_refs: dict = {}

            def _make_pmx(mx):
                def handler(_ev):
                    self.fixed_multi = mx
                    _c  = self.val_fin * mx
                    _t  = len(all_nums) * _c
                    _chip_lbl.value  = f"${_c:.2f}/num"
                    _total_lbl.value = f"Total: ${_t:.2f}  ({len(all_nums)} × ${_c:.2f})"
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

        dlg.content = ft.Column(
            tight=True,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(height=4),
                grid,
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
        
        # Record decision for learning system
        if self.ai_init_success and self.grupos_activos:
            try:
                self.current_spin_number = len(self.history_nums)
                self.current_decision_id = str(uuid.uuid4())
                
                total_cost, _ = self._compute_bet()
                bet_targets = ', '.join(self.grupos_activos)
                bet_type = 'group' if len(self.grupos_activos) > 1 else 'number'
                
                decision = Decision(
                    decision_id=self.current_decision_id,
                    session_id=self.session_id or 0,
                    spin_number=self.current_spin_number,
                    bet_target=bet_targets,
                    bet_type=bet_type,
                    bet_amount=total_cost,
                    decision_context={
                        'confidence': 0.6,
                        'reason': 'Manual decision by player',
                        'groups_count': len(self.grupos_activos),
                    },
                    source='manual',
                    decision_time=datetime.now(),
                )
                self.decision_tracker.record_decision(decision)
            except Exception as e:
                pass  # Silently fail if tracking fails

    def _check_pre_bet_warning(self, on_confirm):
        """Show warning if losing this bet would breach 45% stop loss."""
        if self.stop_loss_triggered or self.banca_inicial <= 0:
            on_confirm()
            return
        total_cost, _ = self._compute_bet()
        potential_bank = self.banca_actual - total_cost
        loss_pct = (self.banca_inicial - potential_bank) / self.banca_inicial
        if loss_pct < 0.3:
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
                ft.Text(f"Loss: {loss_pct*100:.1f}%  (limit 45%)",
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
        self._check_pre_bet_warning(self._activate_bet)

    def confirmar_manual(self, e=None):
        if not self.grupos_activos:
            return
        # Skip popup for outside bets, show it for inside/straight bets
        if self._is_outside_bet_type():
            self._proceed_bet()
        else:
            self._show_roulette_chip_popup(self._proceed_bet)

    def auto_invertir_sug(self, grupos):
        self.limpiar_seleccion_visual()
        self.grupos_activos = list(grupos)
        self._refresh_mixer_colors()
        # Skip popup for outside bets
        if self._is_outside_bet_type():
            self._proceed_bet()
        else:
            self._show_roulette_chip_popup(self._proceed_bet)

    def _get_ai_info_display(self) -> str:
        """Get AI recommendations and player profile for display with training progress."""
        if not self.ai_init_success:
            return "AI: Initializing..."
        
        try:
            # Get total investments created
            total_investments = self._count_total_investments()
            
            # Minimum investments needed for reliable AI recommendations
            MIN_INVESTMENTS = 20
            
            if total_investments < MIN_INVESTMENTS:
                # Show training progress
                progress_pct = int((total_investments / MIN_INVESTMENTS) * 100)
                remaining = max(0, MIN_INVESTMENTS - total_investments)
                return f"AI 🧠 Training: {progress_pct}% ({remaining} more investments)"
            
            # Enough data - show recommendations
            profile = self.learning_engine.get_player_profile()
            win_rate = profile.get('statistics', {}).get('win_rate', 0)
            best_targets = profile.get('best_targets', [])
            
            if best_targets:
                best_bet = best_targets[0] if isinstance(best_targets, list) else best_targets
                rate_str = f"{best_bet.get('target', '?')}: {best_bet.get('win_rate', 0):.0%}" if isinstance(best_bet, dict) else str(best_bet)
            else:
                rate_str = "Learning..."
                
            return f"AI 🧠 {rate_str} | WR:{win_rate:.0%}"
        except Exception:
            return "AI: Active"

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
            # In live mode, dozens frequency is measured against expanded live sets
            stats = sorted(
                [{'g': g,
                  'p': sum(1 for n in self.sliding_window
                           if n in GRUPOS_MAESTROS[f'{g}_L' if (live and key == 'docs') else g]) / 6}
                 for g in grupos],
                key=lambda x: x['p'], reverse=True,
            )

            if live and key == 'docs':
                # Single most-frequent dozen using live (wheel-expanded) group + active filter
                top      = stats[0]['g']
                actual_g = f'{top}{_DOC_SFX.get(lf, "_L")}'
                ftag     = _FILTER_LABELS[lf] if lf else ''
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
            total, _ = self._compute_bet()
            is_out = self._is_outside()
            multi  = self._current_multi(is_out)
            if is_out:
                chip_val  = self.val_fout
                n_grp     = len(self.grupos_activos)
                num_chips = multi * n_grp   # per-group × number of groups
            else:
                chip_val  = self.val_fin
                # Sniper mode: use intersection size; regular mode: use multiplicity-weighted sum
                if self.sniper_mode:
                    intersection = self._compute_intersection()
                    num_chips = len(intersection) * multi
                else:
                    num_chips = sum(len(GRUPOS_MAESTROS[g]) for g in self.grupos_activos) * multi
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
            pending_cost, _ = self._compute_bet()
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
        
        # Update AI info display (every few spins to avoid slowdown)
        if self.ai_init_success and hasattr(self, 'lbl_ai_info') and len(self.history_nums) % 5 == 0:
            try:
                self.lbl_ai_info.value = self._get_ai_info_display()
            except Exception:
                pass
        
        self.page.update()
        self._check_stop_loss()

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


ft.app(main)
