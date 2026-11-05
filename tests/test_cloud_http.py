"""Run: python tests/test_cloud_http.py - checks request shapes with a mock transport."""
import os, sys, json, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import httpx, linup_cloud as lc

calls = []
def handler(req):
    calls.append((req.method, req.url.path, req.url.query.decode(), dict(req.headers), req.content))
    p = req.url.path
    if p == "/auth/v1/token":
        return httpx.Response(200, json=dict(access_token="AT", refresh_token="RT", expires_in=3600, user=dict(id="u1", email="a@b.co")))
    if p == "/auth/v1/signup":
        return httpx.Response(200, json=dict(id="u1", email="a@b.co"))      # confirm-email flow
    if p == "/rest/v1/investments" and req.method == "GET":
        return httpx.Response(200, json=[dict(id="x", updated_at="2026-01-01T00:00:00+00:00", deleted=False)])
    if p == "/rest/v1/investments":
        return httpx.Response(201)
    return httpx.Response(400, json=dict(msg="Invalid login credentials"))

_real = httpx.request
httpx.post = lambda url, **kw: httpx.Client(transport=httpx.MockTransport(handler)).post(url, **kw)
httpx.request = lambda m, url, **kw: httpx.Client(transport=httpx.MockTransport(handler)).request(m, url, **kw)

d = tempfile.mkdtemp(); path = os.path.join(d, "auth.json")
a = lc.CloudAuth("https://x.supabase.co", "ANON", path)
assert a.sign_up("a@b.co", "password1") == "confirm_email" and not a.signed_in
a.sign_in("a@b.co", "password1"); assert a.signed_in and a.user_id == "u1"
assert oct(os.stat(path).st_mode & 0o777) == "0o600"
assert lc.CloudAuth("https://x.supabase.co", "ANON", path).signed_in      # persisted
st = lc.SupabaseStore(a)
assert st.list_index()[0]["id"] == "x"
st.upsert("x", {"name": "n"}, "2026-01-01T00:00:00Z")
m, p, q, h, body = calls[-1]
assert "on_conflict=user_id,id" in q and h["authorization"] == "Bearer AT" and h["apikey"] == "ANON"
assert json.loads(body)["id"] == "x"
a.session["expires_at"] = time.time() - 5; a.token(); assert calls[-1][2] == "grant_type=refresh_token"
a.sign_out(); assert not a.signed_in and not os.path.exists(path)
print("cloud http tests passed")
