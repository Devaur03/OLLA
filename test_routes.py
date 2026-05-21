"""
Route integration test — ASGI in-process, SQLite + fakeredis.
Run:  python3 test_routes.py
"""
import asyncio, json, os, sys, time
from dataclasses import dataclass
from typing import Any

SQLITE_URL = "sqlite+aiosqlite:///:memory:"

os.environ.update({
    "DATABASE_URL":          SQLITE_URL,
    "REDIS_URL":             "redis://localhost:6379",
    "REQUIRE_AUTH":          "false",
    "USE_LOCAL_EMBEDDINGS":  "true",
    "DB_POOL_SIZE":          "1",
    "DB_MAX_OVERFLOW":       "0",
    "LOG_JSON":              "false",
    "CACHE_TTL_SECONDS":     "60",
    "STRIPE_SECRET_KEY":     "",
    "STRIPE_WEBHOOK_SECRET": "",
    "STRIPE_PUBLISHABLE_KEY":"",
    "STRIPE_PRICE_STARTER":  "",
    "STRIPE_PRICE_PRO":      "",
    "STRIPE_PRICE_TEAM":     "",
    "STRIPE_PRICE_ENTERPRISE":"",
})

# ── Patch SQLAlchemy: always use SQLite, strip pool kwargs ──────────────────
import sqlalchemy.ext.asyncio as _sa_async
_orig_engine = _sa_async.create_async_engine
def _sqlite_engine(url, **kw):
    kw.pop("pool_size",None); kw.pop("max_overflow",None); kw.pop("pool_pre_ping",None)
    return _orig_engine(SQLITE_URL, **kw)
_sa_async.create_async_engine = _sqlite_engine

# ── Patch redis → fakeredis ─────────────────────────────────────────────────
import fakeredis.aioredis as _fake
import redis.asyncio as _real
_fake_factory = lambda *a,**kw: _fake.FakeRedis()
_real.from_url = _fake_factory

sys.path.insert(0, "/sessions/admiring-confident-davinci/mnt/ddgsSearch")
from app.main import create_app
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.db.base import Base
from app.config import settings
from httpx import AsyncClient, ASGITransport

# Force settings values after import
for attr, val in [
    ("database_url", SQLITE_URL), ("stripe_secret_key",""),
    ("stripe_webhook_secret",""), ("stripe_publishable_key",""),
]:
    try: object.__setattr__(settings, attr, val)
    except: pass

import app.db.session as _sess
_shared_engine = create_async_engine(SQLITE_URL)
_sess.engine = _shared_engine
_sess.AsyncSessionLocal = async_sessionmaker(
    bind=_shared_engine, class_=AsyncSession,
    expire_on_commit=False, autocommit=False, autoflush=False,
)

@dataclass
class R:
    method:str; path:str; description:str; notes:str=""
    expected:int=200; status_code:int=0
    body:Any=None; error:str=""; latency_ms:float=0.0; passed:bool=False

results: list[R] = []
API_KEY = ""

def _fmt(b, n=600):
    try:
        s = json.dumps(b,indent=2) if isinstance(b,(dict,list)) else str(b)
        return s[:n]
    except: return str(b)[:n]

async def hit(client, method, path, desc, expected=200, notes="", **kw):
    r = R(method=method,path=path,description=desc,notes=notes,expected=expected)
    try:
        t0 = time.perf_counter()
        resp = await getattr(client,method.lower())(path,**kw)
        r.latency_ms = round((time.perf_counter()-t0)*1000,1)
        r.status_code = resp.status_code
        try: r.body = resp.json()
        except: r.body = resp.text[:400]
        r.passed = (r.status_code == r.expected)
    except Exception as e:
        r.error = str(e); r.passed = False
    results.append(r)
    icon = "✓" if r.passed else "✗"
    print(f"  {icon} [{r.status_code or 'ERR'}] {method.upper():6} {path}  ({r.latency_ms}ms)")
    if not r.passed:
        print(f"      expect={expected}  body={_fmt(r.body,180)}  err={r.error[:120]}")
    return r

async def run():
    global API_KEY

    async with _shared_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver", timeout=30.0) as c:

        # ── Health ────────────────────────────────────────────────────────────
        print("\n── GET /api/v1/health ──────────────────────────────────────")
        await hit(c,"GET","/api/v1/health",
                  "Deep health check — DB + Redis status",200,
                  "Public. No auth needed. Returns component latencies.")

        # ── Docs ──────────────────────────────────────────────────────────────
        print("\n── OpenAPI / Swagger / ReDoc ───────────────────────────────")
        await hit(c,"GET","/openapi.json","OpenAPI 3 JSON schema",200,
                  "Auto-generated. Lists all routes, schemas, status codes.")
        await hit(c,"GET","/docs","Swagger UI HTML",200,"Interactive browser API explorer.")
        await hit(c,"GET","/redoc","ReDoc UI HTML",200,"Alternative reference docs.")

        # ── Key registration (public) ─────────────────────────────────────────
        print("\n── POST /api/v1/keys/register ──────────────────────────────")
        r = await hit(c,"POST","/api/v1/keys/register",
                      "Register new user + issue first key (public)",201,
                      "Creates user + api_key rows. Raw key returned ONCE.",
                      json={"email":"tester@example.com","name":"Primary key"})
        if r.passed and isinstance(r.body,dict):
            API_KEY = r.body.get("api_key","")
            print(f"      ↳ prefix={API_KEY[:12]}…  plan={r.body.get('plan')}  user={str(r.body.get('user_id',''))[:8]}…")

        await hit(c,"POST","/api/v1/keys/register",
                  "Re-register same email → second key (idempotent)",201,
                  "Existing user receives a new active key.",
                  json={"email":"tester@example.com","name":"Key 2"})

        await hit(c,"POST","/api/v1/keys/register",
                  "Invalid email → 422 validation error",422,
                  "Pydantic EmailStr rejects non-email strings.",
                  json={"email":"not-an-email"})

        await hit(c,"POST","/api/v1/keys/register",
                  "Missing email field → 422 validation error",422,
                  "Required field; Pydantic raises validation error.",
                  json={"name":"no-email"})

        hdrs = {"X-API-Key": API_KEY} if API_KEY else {}

        # ── List keys ─────────────────────────────────────────────────────────
        print("\n── GET /api/v1/keys ────────────────────────────────────────")
        r_list = await hit(c,"GET","/api/v1/keys",
                           "List keys for authenticated user",200,
                           "Returns key prefix + metadata. Raw key never returned.",
                           headers=hdrs)
        # Pick a key that is NOT our auth key to use for the delete test
        revoke_id = None
        if r_list.passed and isinstance(r_list.body,list):
            for k in r_list.body:
                if not API_KEY.startswith(k.get("key_prefix","")):
                    revoke_id = k.get("id")
                    break

        await hit(c,"GET","/api/v1/keys",
                  "List keys — no auth → 401",401,
                  "Route reads request.state.user_id; missing = 401.")

        # ── Create additional key ─────────────────────────────────────────────
        print("\n── POST /api/v1/keys ───────────────────────────────────────")
        r_new = await hit(c,"POST","/api/v1/keys",
                          "Create additional key (auth required)",201,
                          "Issues another raw key for the same user.",
                          headers=hdrs, json={"name":"CI Bot"})

        # If we didn't find a revoke candidate yet, use the one just created
        if not revoke_id and r_new.passed:
            r_list2 = await hit(c,"GET","/api/v1/keys","Re-list to find revoke target",200,headers=hdrs)
            if isinstance(r_list2.body,list):
                for k in r_list2.body:
                    if not API_KEY.startswith(k.get("key_prefix","")):
                        revoke_id = k.get("id"); break

        await hit(c,"POST","/api/v1/keys",
                  "Create key — no auth → 401",401,
                  "Must be authenticated.",
                  json={"name":"Unauthed"})

        # ── Revoke key ────────────────────────────────────────────────────────
        print("\n── DELETE /api/v1/keys/{key_id} ────────────────────────────")
        if revoke_id:
            await hit(c,"DELETE",f"/api/v1/keys/{revoke_id}",
                      f"Revoke non-auth key → 204 No Content",204,
                      "Soft-delete: is_active=false. Key stops working immediately.",
                      headers=hdrs)
        else:
            print("  (skipped — no separate key to revoke)")

        await hit(c,"DELETE","/api/v1/keys/00000000-0000-0000-0000-000000000000",
                  "Revoke non-existent key → 404",404,
                  "Returns 404 when key not found for authenticated user.",
                  headers=hdrs)

        await hit(c,"DELETE","/api/v1/keys/some-id",
                  "Revoke key — no auth → 401",401,
                  "Auth required before DB lookup.")

        # ── Billing: usage ────────────────────────────────────────────────────
        print("\n── GET /api/v1/billing/usage ───────────────────────────────")
        await hit(c,"GET","/api/v1/billing/usage",
                  "Current plan + monthly usage (authenticated)",200,
                  "Returns plan, queries_used, queries_limit, period start/end.",
                  headers=hdrs)

        await hit(c,"GET","/api/v1/billing/usage",
                  "Usage — no auth → 401",401,
                  "Returns 401 when X-API-Key is missing.")

        # ── Billing: checkout ─────────────────────────────────────────────────
        print("\n── POST /api/v1/billing/checkout ───────────────────────────")
        await hit(c,"POST","/api/v1/billing/checkout",
                  "Checkout — invalid plan name → 400",400,
                  "Validated before calling Stripe.",
                  headers=hdrs, json={"plan":"diamond"})

        await hit(c,"POST","/api/v1/billing/checkout",
                  "Checkout — valid plan, Stripe not configured → 503",503,
                  "STRIPE_SECRET_KEY is empty; stripe package raises 503.",
                  headers=hdrs, json={"plan":"starter"})

        await hit(c,"POST","/api/v1/billing/checkout",
                  "Checkout — no auth → 401",401,
                  "Auth required before Stripe interaction.",
                  json={"plan":"starter"})

        # ── Billing: portal ───────────────────────────────────────────────────
        print("\n── POST /api/v1/billing/portal ─────────────────────────────")
        await hit(c,"POST","/api/v1/billing/portal",
                  "Portal — no Stripe customer yet → 400",400,
                  "User has no stripe_customer_id; returns 400 before calling Stripe.",
                  headers=hdrs)

        await hit(c,"POST","/api/v1/billing/portal",
                  "Portal — no auth → 401",401,
                  "Auth required.")

        # ── Billing: webhook ──────────────────────────────────────────────────
        print("\n── POST /api/v1/billing/webhook ────────────────────────────")
        await hit(c,"POST","/api/v1/billing/webhook",
                  "Webhook — invalid Stripe signature → 400",400,
                  "Public. Stripe signature always fails without real webhook secret.",
                  content=b'{"type":"ping"}',
                  headers={"stripe-signature":"t=1,v1=bad","Content-Type":"application/json"})

        # ── Search: keyword ───────────────────────────────────────────────────
        print("\n── POST /api/v1/search ─────────────────────────────────────")
        await hit(c,"POST","/api/v1/search",
                  "Search — missing query → 422 validation error",422,
                  "Pydantic requires the 'query' field.",
                  headers=hdrs, json={})

        # Sandbox has no internet; DDG will fail → 404 "no results" — record as known infra issue
        print("  (live web search — sandbox has no outbound internet; expected to fail with 404)")
        await hit(c,"POST","/api/v1/search",
                  "Web search — sandbox network unavailable",404,
                  "DDG + Brave blocked in sandbox. On a live server this returns 200 with results.",
                  headers=hdrs,
                  json={"query":"FastAPI Python framework","max_results":2},
                  timeout=20.0)

        # ── Search: semantic ──────────────────────────────────────────────────
        print("\n── POST /api/v1/search/semantic ────────────────────────────")
        await hit(c,"POST","/api/v1/search/semantic",
                  "Semantic search — missing query → 422",422,
                  "Pydantic validation.",
                  headers=hdrs, json={})

        # sentence-transformers not installed in sandbox → 503
        await hit(c,"POST","/api/v1/search/semantic",
                  "Semantic search — missing ML deps → 503",503,
                  "sentence-transformers not installed in sandbox. "
                  "Run: pip install sentence-transformers. Returns 200 on a full install.",
                  headers=hdrs,
                  json={"query":"vector database embeddings","top_k":5},
                  timeout=15.0)

        # ── Dashboard ─────────────────────────────────────────────────────────
        print("\n── GET /dashboard ──────────────────────────────────────────")
        await hit(c,"GET","/dashboard",
                  "Built-in HTML dashboard UI",200,
                  "Returns HTML page. No auth required.")

    return results

if __name__ == "__main__":
    print("="*64)
    print("  Hybrid Search API — Route Integration Test")
    print("  DB:    SQLite in-memory (aiosqlite)")
    print("  Cache: fakeredis")
    print("  Auth:  REQUIRE_AUTH=false + DB key lookup enabled")
    print("="*64)
    res = asyncio.run(run())
    passed = sum(1 for r in res if r.passed)
    total  = len(res)
    print(f"\n{'='*64}")
    print(f"  RESULT: {passed}/{total} passed  |  {total-passed} failed")
    print("="*64)
    with open("/tmp/route_results.json","w") as f:
        json.dump([{
            "method":r.method.upper(),"path":r.path,
            "description":r.description,"notes":r.notes,
            "expected":r.expected,"status_code":r.status_code,
            "passed":r.passed,"latency_ms":r.latency_ms,
            "body_summary":_fmt(r.body,400),"error":r.error,
        } for r in res], f, indent=2)
    print("JSON → /tmp/route_results.json")
