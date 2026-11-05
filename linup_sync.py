"""
Local side of cloud sync for Linup.

Design
------
* The local SQLite DB stays the primary store (offline-first).
* Each *investment* is the unit of sync. It is serialised, together with its
  tables, compound sessions and table stats, into one JSON document keyed by a
  UUID that is stable across devices. (Local integer ids are per-device.)
* Conflict rule: last write wins, per investment, by `updated_at` (UTC).
* main.py needs no changes at its many write sites: SQLite triggers bump
  `investments.updated_at` whenever an investment or one of its child rows
  changes, and record a tombstone when an investment is deleted.

The cloud side is any object with the three methods used in `SyncEngine`
(`list_index`, `get_docs`, `upsert`) - see linup_cloud.SupabaseStore. This
keeps the logic testable without a network.
"""
import os
import shutil
import sqlite3
from datetime import datetime, timezone

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
_NOT_APPLYING = "(SELECT value FROM sync_state WHERE key='applying') IS NOT '1'"
_UUID_EXPR = (
    "lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-4'||"
    "substr(lower(hex(randomblob(2))),2)||'-'||"
    "substr('89ab',abs(random())%4+1,1)||substr(lower(hex(randomblob(2))),2)"
    "||'-'||lower(hex(randomblob(6)))"
)

# child table -> columns that make up the synced payload
_CHILDREN = {
    "investment_tables": ("mesa_name", "init_bank", "token_symbol",
                          "token_balance", "token_price", "chips_per_token"),
    "compound_sessions": ("session_num", "date", "mesa", "bank_start",
                          "bank_end", "profit", "profit_pct"),
    "table_stats": ("mesa", "wins", "losses", "last_bank", "base_chip"),
}
_INV_COLS = ("name", "capital", "created_at", "inv_type")


def _parse_ts(s):
    """Parse local ('...Z') or Postgres ('...+00:00') timestamps to aware UTC."""
    if not s:
        return datetime.min.replace(tzinfo=timezone.utc)
    s = str(s).replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _has_col(conn, table, col):
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


def ensure_sync_schema(db_path):
    """Idempotent. Call once after the app's own init_db()."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sync_state "
                     "(key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR REPLACE INTO sync_state VALUES ('applying','0')")
        conn.execute("CREATE TABLE IF NOT EXISTS sync_tombstones "
                     "(uuid TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)")
        for col, decl in (("uuid", "TEXT"), ("updated_at", "TEXT")):
            if not _has_col(conn, "investments", col):
                conn.execute(f"ALTER TABLE investments ADD COLUMN {col} {decl}")
        conn.execute(f"UPDATE investments SET uuid={_UUID_EXPR} WHERE uuid IS NULL")
        conn.execute(f"UPDATE investments SET updated_at={_NOW} "
                     "WHERE updated_at IS NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_investments_uuid "
                     "ON investments(uuid)")

        conn.execute("DROP TRIGGER IF EXISTS trg_inv_uuid")
        conn.execute(
            "CREATE TRIGGER trg_inv_uuid AFTER INSERT ON investments "
            f"WHEN NEW.uuid IS NULL BEGIN UPDATE investments SET uuid={_UUID_EXPR} "
            "WHERE id=NEW.id; END")

        def touch(inv_expr):
            return (f"UPDATE investments SET updated_at={_NOW} "
                    f"WHERE id={inv_expr};")

        conn.execute("DROP TRIGGER IF EXISTS trg_inv_ins")
        conn.execute(
            "CREATE TRIGGER trg_inv_ins AFTER INSERT ON investments "
            f"WHEN {_NOT_APPLYING} BEGIN {touch('NEW.id')} END")
        conn.execute("DROP TRIGGER IF EXISTS trg_inv_upd")
        conn.execute(
            "CREATE TRIGGER trg_inv_upd AFTER UPDATE OF name, capital, "
            f"created_at, inv_type ON investments WHEN {_NOT_APPLYING} "
            f"BEGIN {touch('NEW.id')} END")
        conn.execute("DROP TRIGGER IF EXISTS trg_inv_del")
        conn.execute(
            "CREATE TRIGGER trg_inv_del AFTER DELETE ON investments "
            f"WHEN {_NOT_APPLYING} AND OLD.uuid IS NOT NULL BEGIN "
            "INSERT OR REPLACE INTO sync_tombstones(uuid, deleted_at) "
            f"VALUES (OLD.uuid, {_NOW}); END")

        for table in _CHILDREN:
            for ev, ref in (("ins", "NEW"), ("upd", "NEW"), ("del", "OLD")):
                name = f"trg_{table}_{ev}"
                verb = {"ins": "INSERT", "upd": "UPDATE", "del": "DELETE"}[ev]
                conn.execute(f"DROP TRIGGER IF EXISTS {name}")
                conn.execute(
                    f"CREATE TRIGGER {name} AFTER {verb} ON {table} "
                    f"WHEN {_NOT_APPLYING} BEGIN {touch(ref + '.investment_id')} END")
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────
# Serialise / apply one investment
# ──────────────────────────────────────────────────────────────────────
def export_investment(conn, inv_id):
    row = conn.execute(
        f"SELECT {','.join(_INV_COLS)} FROM investments WHERE id=?",
        (inv_id,)).fetchone()
    doc = dict(zip(_INV_COLS, row))
    for table, cols in _CHILDREN.items():
        cur = conn.execute(
            f"SELECT {','.join(cols)} FROM {table} WHERE investment_id=? ORDER BY id"
            if table != "table_stats" else
            f"SELECT {','.join(cols)} FROM {table} WHERE investment_id=? ORDER BY mesa",
            (inv_id,))
        doc[table] = [dict(zip(cols, r)) for r in cur.fetchall()]
    return doc


def _set_applying(conn, on):
    conn.execute("INSERT OR REPLACE INTO sync_state VALUES ('applying', ?)",
                 ("1" if on else "0",))


def apply_investment(conn, uuid, doc, updated_at):
    """Insert/replace a local investment from a cloud document."""
    _set_applying(conn, True)
    try:
        r = conn.execute("SELECT id FROM investments WHERE uuid=?", (uuid,)).fetchone()
        vals = [doc.get(c) for c in _INV_COLS]
        if r:
            inv_id = r[0]
            conn.execute(
                "UPDATE investments SET name=?, capital=?, created_at=?, inv_type=?, "
                "updated_at=? WHERE id=?", (*vals, updated_at, inv_id))
            for table in _CHILDREN:
                conn.execute(f"DELETE FROM {table} WHERE investment_id=?", (inv_id,))
        else:
            cur = conn.execute(
                "INSERT INTO investments (name, capital, created_at, inv_type, "
                "uuid, updated_at) VALUES (?,?,?,?,?,?)", (*vals, uuid, updated_at))
            inv_id = cur.lastrowid
        for table, cols in _CHILDREN.items():
            for item in doc.get(table, []):
                conn.execute(
                    f"INSERT INTO {table} (investment_id,{','.join(cols)}) "
                    f"VALUES (?,{','.join('?' * len(cols))})",
                    (inv_id, *[item.get(c) for c in cols]))
        conn.execute("DELETE FROM sync_tombstones WHERE uuid=?", (uuid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _set_applying(conn, False)
        conn.commit()


def delete_local(conn, uuid):
    _set_applying(conn, True)
    try:
        r = conn.execute("SELECT id FROM investments WHERE uuid=?", (uuid,)).fetchone()
        if r:
            for table in _CHILDREN:
                conn.execute(f"DELETE FROM {table} WHERE investment_id=?", (r[0],))
            conn.execute("DELETE FROM investments WHERE id=?", (r[0],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _set_applying(conn, False)
        conn.commit()


# ──────────────────────────────────────────────────────────────────────
# Device ownership (so user B never inherits/pushes user A's local data)
# ──────────────────────────────────────────────────────────────────────
def get_owner(db_path):
    conn = sqlite3.connect(db_path)
    try:
        r = conn.execute("SELECT value FROM sync_state WHERE key='owner'").fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def set_owner(db_path, user_id):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT OR REPLACE INTO sync_state VALUES ('owner', ?)", (user_id,))
        conn.commit()
    finally:
        conn.close()


def has_local_investments(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM investments").fetchone()[0] > 0
    finally:
        conn.close()


def stash_and_clear_local(db_path):
    """Back up the whole DB file, then remove all synced rows. Returns backup path."""
    base = os.path.dirname(db_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = os.path.join(base, "stash", f"account_switch_{ts}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(db_path))
    shutil.copy2(db_path, dest)
    conn = sqlite3.connect(db_path)
    try:
        _set_applying(conn, True)
        for table in list(_CHILDREN) + ["investments", "sync_tombstones"]:
            conn.execute(f"DELETE FROM {table}")
        _set_applying(conn, False)
        conn.commit()
    finally:
        conn.close()
    return dest


# ──────────────────────────────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────────────────────────────
class SyncEngine:
    def __init__(self, db_path, store):
        self.db_path = db_path
        self.store = store

    def sync(self):
        """Two-way merge. Returns {'pushed','pulled','deleted_remote','deleted_local'}."""
        out = {"pushed": 0, "pulled": 0, "deleted_remote": 0, "deleted_local": 0}
        remote = {r["id"]: r for r in self.store.list_index()}
        conn = sqlite3.connect(self.db_path)
        try:
            # 1) local deletions
            for uuid, deleted_at in conn.execute(
                    "SELECT uuid, deleted_at FROM sync_tombstones").fetchall():
                r = remote.get(uuid)
                if r is None or r["deleted"]:
                    conn.execute("DELETE FROM sync_tombstones WHERE uuid=?", (uuid,))
                elif _parse_ts(r["updated_at"]) <= _parse_ts(deleted_at):
                    self.store.upsert(uuid, {}, deleted_at, deleted=True)
                    out["deleted_remote"] += 1
                    remote[uuid] = {"id": uuid, "updated_at": deleted_at, "deleted": True}
                    conn.execute("DELETE FROM sync_tombstones WHERE uuid=?", (uuid,))
                else:  # edited elsewhere after we deleted: edit wins
                    conn.execute("DELETE FROM sync_tombstones WHERE uuid=?", (uuid,))
            conn.commit()

            # 2) local rows vs remote
            locals_ = {u: (i, t) for i, u, t in conn.execute(
                "SELECT id, uuid, updated_at FROM investments").fetchall()}
            to_pull = []
            for uuid, (inv_id, l_ts) in locals_.items():
                r = remote.get(uuid)
                if r is None:
                    self.store.upsert(uuid, export_investment(conn, inv_id), l_ts)
                    out["pushed"] += 1
                    continue
                lt, rt = _parse_ts(l_ts), _parse_ts(r["updated_at"])
                if lt > rt:
                    self.store.upsert(uuid, export_investment(conn, inv_id), l_ts)
                    out["pushed"] += 1
                elif rt > lt:
                    if r["deleted"]:
                        delete_local(conn, uuid)
                        out["deleted_local"] += 1
                    else:
                        to_pull.append(uuid)
            for uuid, r in remote.items():
                if uuid not in locals_ and not r["deleted"]:
                    to_pull.append(uuid)

            # 3) pull
            if to_pull:
                docs = self.store.get_docs(to_pull)
                for uuid in to_pull:
                    d = docs.get(uuid)
                    if d:
                        apply_investment(conn, uuid, d["data"], d["updated_at"])
                        out["pulled"] += 1
        finally:
            conn.close()
        return out
