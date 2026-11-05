"""Run: python -I tests/test_sync.py   (from repo root, linup env). No network."""
import os, sys, sqlite3, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import linup_sync as ls

SCHEMA = """
CREATE TABLE investments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, capital REAL, created_at TEXT, inv_type TEXT DEFAULT 'FIAT');
CREATE TABLE investment_tables (id INTEGER PRIMARY KEY AUTOINCREMENT, investment_id INTEGER, mesa_name TEXT, init_bank REAL, token_symbol TEXT DEFAULT '', token_balance REAL DEFAULT 0, token_price REAL DEFAULT 0, chips_per_token REAL DEFAULT 0, table_type TEXT DEFAULT '');
CREATE TABLE compound_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, investment_id INTEGER NOT NULL DEFAULT 0, session_num INTEGER, date TEXT, mesa TEXT, bank_start REAL, bank_end REAL, profit REAL, profit_pct REAL);
CREATE TABLE table_stats (investment_id INTEGER NOT NULL DEFAULT 0, mesa TEXT NOT NULL, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, last_bank REAL DEFAULT 0, base_chip REAL DEFAULT 0, PRIMARY KEY (investment_id, mesa));
"""

class FakeStore:
    def __init__(self): self.rows = {}
    def list_index(self): return [dict(id=k, updated_at=v["updated_at"], deleted=v["deleted"]) for k, v in self.rows.items()]
    def get_docs(self, ids): return {i: dict(data=self.rows[i]["data"], updated_at=self.rows[i]["updated_at"]) for i in ids if i in self.rows}
    def upsert(self, id, data, updated_at, deleted=False): self.rows[id] = dict(data=data, updated_at=updated_at, deleted=deleted)

def device():
    d = tempfile.mkdtemp(); p = os.path.join(d, "linup_data.db")
    c = sqlite3.connect(p); c.executescript(SCHEMA); c.commit(); c.close()
    ls.ensure_sync_schema(p); return p

def q(p, sql, *a):
    c = sqlite3.connect(p); r = c.execute(sql, a).fetchall(); c.commit(); c.close(); return r

def create_inv(p, name):
    c = sqlite3.connect(p)
    cur = c.execute("INSERT INTO investments (name,capital,created_at,inv_type) VALUES (?,?,?,?)", (name, 100.0, "2026-01-01", "FIAT"))
    i = cur.lastrowid
    c.execute("INSERT INTO investment_tables (investment_id,mesa_name,init_bank) VALUES (?,?,?)", (i, "T1", 50))
    c.execute("INSERT INTO compound_sessions (investment_id,session_num,date,mesa,bank_start,bank_end,profit,profit_pct) VALUES (?,?,?,?,?,?,?,?)", (i, 1, "d", "T1", 50, 60, 10, 20))
    c.execute("INSERT INTO table_stats (investment_id,mesa,wins,losses,last_bank) VALUES (?,?,?,?,?)", (i, "T1", 3, 1, 60))
    c.commit(); c.close(); return i

cloud = FakeStore(); A, B = device(), device()
ls.ensure_sync_schema(A)  # idempotent

# 1. uuid assigned automatically; push from A, pull to B
i = create_inv(A, "Alpha")
assert q(A, "SELECT uuid FROM investments")[0][0], "uuid missing"
r = ls.SyncEngine(A, cloud).sync(); assert r["pushed"] == 1, r
r = ls.SyncEngine(B, cloud).sync(); assert r["pulled"] == 1, r
assert q(B, "SELECT name,capital FROM investments") == [("Alpha", 100.0)]
assert q(B, "SELECT mesa_name FROM investment_tables") == [("T1",)]
assert q(B, "SELECT wins,losses FROM table_stats") == [(3, 1)]
assert q(B, "SELECT COUNT(*) FROM compound_sessions")[0][0] == 1
# pulling must not look like a local edit -> second sync is a no-op both ways
assert ls.SyncEngine(B, cloud).sync() == dict(pushed=0, pulled=0, deleted_remote=0, deleted_local=0)
assert ls.SyncEngine(A, cloud).sync() == dict(pushed=0, pulled=0, deleted_remote=0, deleted_local=0)

assert q(B, "SELECT table_type FROM investment_tables") == [('',)]
q(A, "UPDATE investment_tables SET table_type='CHIPS'"); ls.SyncEngine(A, cloud).sync(); ls.SyncEngine(B, cloud).sync()
assert q(B, "SELECT table_type FROM investment_tables") == [('CHIPS',)], 'table_type not synced'

# 2. child-row edit on B (a new session) bumps parent -> propagates to A
time.sleep(0.01)
bi = q(B, "SELECT id FROM investments")[0][0]
q(B, "INSERT INTO compound_sessions (investment_id,session_num,date,mesa,bank_start,bank_end,profit,profit_pct) VALUES (?,2,'d2','T1',60,70,10,16)", bi)
assert ls.SyncEngine(B, cloud).sync()["pushed"] == 1
assert ls.SyncEngine(A, cloud).sync()["pulled"] == 1
assert q(A, "SELECT COUNT(*) FROM compound_sessions")[0][0] == 2

# 3. conflict: both edit; later write wins
q(A, "UPDATE investments SET name='A-edit'"); time.sleep(0.02)
q(B, "UPDATE investments SET name='B-edit'")
ls.SyncEngine(A, cloud).sync(); ls.SyncEngine(B, cloud).sync(); ls.SyncEngine(A, cloud).sync()
assert q(A, "SELECT name FROM investments") == q(B, "SELECT name FROM investments") == [("B-edit",)]

# 4. delete on A propagates to B; no resurrection
q(A, "DELETE FROM investment_tables"); q(A, "DELETE FROM investments")
assert q(A, "SELECT COUNT(*) FROM sync_tombstones")[0][0] == 1
r = ls.SyncEngine(A, cloud).sync(); assert r["deleted_remote"] == 1, r
r = ls.SyncEngine(B, cloud).sync(); assert r["deleted_local"] == 1, r
assert q(B, "SELECT COUNT(*) FROM investments")[0][0] == 0
ls.SyncEngine(A, cloud).sync()
assert q(A, "SELECT COUNT(*) FROM investments")[0][0] == 0

# 5. existing pre-sync data is backfilled with uuids
P = device(); q(P, "DROP TRIGGER trg_inv_uuid"); q(P, "DROP TRIGGER trg_inv_ins")
q(P, "INSERT INTO investments (name,capital) VALUES ('Old',1)")
assert q(P, "SELECT uuid FROM investments")[0][0] is None
ls.ensure_sync_schema(P); assert q(P, "SELECT uuid FROM investments")[0][0]

# 6. account switch stashes and clears
bak = ls.stash_and_clear_local(P)
assert os.path.exists(bak) and q(P, "SELECT COUNT(*) FROM investments")[0][0] == 0
print("all sync tests passed")
