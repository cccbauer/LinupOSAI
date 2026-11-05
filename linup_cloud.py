"""
Supabase client for Linup: email/password auth + investment storage.

Pure Python over HTTPS (httpx ships with flet), so it also works in
`flet build apk`. Blocking calls - run them with run_in_executor from the UI.

Configuration (public values; the anon key is safe to ship because Row Level
Security in supabase_schema.sql restricts every row to its owner):
    LINUP_SUPABASE_URL, LINUP_SUPABASE_ANON_KEY    environment variables, or
    cloud_config.json next to this file: {"url": "...", "anon_key": "..."}
"""
import json
import os
import time

import httpx

_HERE = os.path.dirname(os.path.abspath(__file__))


class CloudError(Exception):
    """User-presentable error."""


def load_config():
    url = os.environ.get("LINUP_SUPABASE_URL")
    key = os.environ.get("LINUP_SUPABASE_ANON_KEY")
    if not (url and key):
        try:
            with open(os.path.join(_HERE, "cloud_config.json"), encoding="utf-8") as f:
                cfg = json.load(f)
            url, key = cfg.get("url"), cfg.get("anon_key")
        except Exception:
            pass
    if url and key and "YOUR-PROJECT" not in url:
        return url.rstrip("/"), key
    return None


def _err(resp):
    try:
        j = resp.json()
        msg = (j.get("msg") or j.get("error_description") or j.get("message")
               or j.get("error") or resp.text)
    except Exception:
        msg = resp.text
    return CloudError(str(msg)[:300])


class CloudAuth:
    """Email + password accounts via Supabase Auth, session kept on disk."""

    def __init__(self, url, anon_key, session_path):
        self.url, self.key, self.path = url, anon_key, session_path
        self.session = self._load()

    # -- persistence ---------------------------------------------------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _save(self):
        if self.session is None:
            try:
                os.remove(self.path)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.session, f)

    def _headers(self, token=None):
        return {"apikey": self.key, "Authorization": f"Bearer {token or self.key}",
                "Content-Type": "application/json"}

    def _store_session(self, j):
        self.session = {
            "access_token": j["access_token"],
            "refresh_token": j["refresh_token"],
            "expires_at": j.get("expires_at") or int(time.time()) + int(j.get("expires_in", 3600)),
            "user_id": j["user"]["id"],
            "email": j["user"].get("email", ""),
        }
        self._save()

    # -- public API ----------------------------------------------------
    @property
    def signed_in(self):
        return bool(self.session)

    @property
    def email(self):
        return (self.session or {}).get("email", "")

    @property
    def user_id(self):
        return (self.session or {}).get("user_id")

    def sign_up(self, email, password):
        """Returns 'signed_in' or 'confirm_email' (verification mail sent)."""
        try:
            r = httpx.post(f"{self.url}/auth/v1/signup", headers=self._headers(),
                           json={"email": email, "password": password}, timeout=20)
        except httpx.HTTPError as e:
            raise CloudError(f"Can't reach the server: {e}")
        if r.status_code >= 400:
            raise _err(r)
        j = r.json()
        if j.get("access_token"):
            self._store_session(j)
            return "signed_in"
        return "confirm_email"

    def sign_in(self, email, password):
        try:
            r = httpx.post(f"{self.url}/auth/v1/token?grant_type=password",
                           headers=self._headers(),
                           json={"email": email, "password": password}, timeout=20)
        except httpx.HTTPError as e:
            raise CloudError(f"Can't reach the server: {e}")
        if r.status_code >= 400:
            raise _err(r)
        self._store_session(r.json())

    def reset_password(self, email):
        try:
            r = httpx.post(f"{self.url}/auth/v1/recover", headers=self._headers(),
                           json={"email": email}, timeout=20)
        except httpx.HTTPError as e:
            raise CloudError(f"Can't reach the server: {e}")
        if r.status_code >= 400:
            raise _err(r)

    def sign_out(self):
        if self.session:
            try:
                httpx.post(f"{self.url}/auth/v1/logout",
                           headers=self._headers(self.session["access_token"]), timeout=10)
            except httpx.HTTPError:
                pass
        self.session = None
        self._save()

    def token(self):
        """Valid access token, refreshing when it is about to expire."""
        if not self.session:
            raise CloudError("Not signed in")
        if self.session["expires_at"] - 60 > time.time():
            return self.session["access_token"]
        try:
            r = httpx.post(f"{self.url}/auth/v1/token?grant_type=refresh_token",
                           headers=self._headers(),
                           json={"refresh_token": self.session["refresh_token"]}, timeout=20)
        except httpx.HTTPError as e:
            raise CloudError(f"Can't reach the server: {e}")
        if r.status_code >= 400:
            self.session = None       # refresh token revoked/expired: sign in again
            self._save()
            raise CloudError("Session expired - please sign in again")
        self._store_session(r.json())
        return self.session["access_token"]


class SupabaseStore:
    """Cloud side of linup_sync.SyncEngine, backed by the `investments` table."""

    def __init__(self, auth: CloudAuth):
        self.auth = auth

    def _h(self, **extra):
        h = {"apikey": self.auth.key, "Authorization": f"Bearer {self.auth.token()}",
             "Content-Type": "application/json"}
        h.update(extra)
        return h

    def _call(self, method, path, **kw):
        try:
            r = httpx.request(method, f"{self.auth.url}/rest/v1/{path}", timeout=30, **kw)
        except httpx.HTTPError as e:
            raise CloudError(f"Can't reach the server: {e}")
        if r.status_code >= 400:
            raise _err(r)
        return r

    def list_index(self):
        return self._call("GET", "investments?select=id,updated_at,deleted",
                          headers=self._h()).json()

    def get_docs(self, ids):
        out = {}
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            rows = self._call(
                "GET", f"investments?select=id,data,updated_at&id=in.({','.join(chunk)})",
                headers=self._h()).json()
            out.update({r["id"]: r for r in rows})
        return out

    def upsert(self, id, data, updated_at, deleted=False):
        self._call("POST", "investments?on_conflict=user_id,id",
                   headers=self._h(Prefer="resolution=merge-duplicates,return=minimal"),
                   json={"id": id, "data": data, "updated_at": updated_at,
                         "deleted": deleted})
