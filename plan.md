# Microservice Split Plan: Token Service + Notification Service

---

## Original User Request

> "We want to break it into two separate microservices:
> 1. One microservice will get these tokens and keep these tokens. Whenever some other service calls it, it provides the token to them.
> 2. The other microservice gets that token from the token microservice and then sends all these notifications and everything else remains the same. We only want to make this token thing a separate microservice, and of course we want to do it intelligently. We use FastAPI for this separate microservice, the token microservice, and we put the expiry time of the token, created at, expiry at, and so on.
>
> When a token is about to expire, one or two minutes before, we fetch a new token. In memory, we don't want to keep the previous tokens. We want to be intelligent with memory. We don't want to keep creating, keep filling up RAM or the local hard drive or whatever. We don't want to do that. In memory at a time, only one token. Once we get a new token, the new one replaces the old one and so on. We need to be good with memory management as well, and we need to have unit tests for that as well.
>
> Now we want to move towards containers. Is it a better idea to use containers, like a separate container for each microservice? This Zoho token microservice cannot ideally accept requests from the outside world from the internet. It can only get requests from, I don't know, our virtual private cloud or from within the server, the EC2 instance on which we will run these both microservices.
>
> About the other microservice, the one that sends notifications and makes API calls to this token microservice and API calls to Zoho, that one can interact with the internet, but of course we want to tighten the security there as well. Do we need to go to Kubernetes, etc.? Do we need to go towards Terraform, or do we not need it? It's too early, so what do you think?"

---

## Repository

- **GitHub:** https://github.com/AnsImran/zoho-desk-beyond-native-automations
- **Local:** `c:\Users\Ans\Desktop\code\41_pacs_pros_automations\teams_notifications_service`

---

## Current Architecture (What Exists Today)

### Key files
- `main.py` — entry point, infinite loop every 30s
- `src/core/watch_helper.py` — all core logic (~725 lines)
- `src/scripts/product_registry.py` — declarative config for 10 products
- `src/scripts/pending_watch.py` — scheduled pending-ticket summary
- `src/schema/zoho_api_schemas.py` — Pydantic models for Zoho API
- `tests/` — 6 existing test modules

### Current token management (to be replaced)

In `src/core/watch_helper.py`, lines 47-49:
```python
TOKEN_LIFETIME_SECONDS      = 3600
TOKEN_RENEW_GRACE_SECONDS   = 10 * 60  # 10 min grace (will become 2 min in new service)
TOKEN_CACHE: Dict[str, Any] = {"token": None, "created_at": None, "expires_at": None}
```

`get_access_token()` function (~lines 131-163): checks cache, POSTs to Zoho OAuth if stale, updates cache.

Called from:
- `main.py` line 49: `token = get_access_token()`
- `src/scripts/pending_watch.py` line 41: `shared_token = get_access_token()` (standalone `__main__` only)

---

## Target Architecture

```
teams_notifications_service/          ← repo root (notification service)
│
├── token_service/                    ← NEW: token microservice (FastAPI)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   ← FastAPI app + lifespan
│   │   ├── token_manager.py          ← async cache + proactive background refresh
│   │   └── schemas.py                ← Pydantic response models
│   └── tests/
│       ├── __init__.py
│       └── test_token_manager.py     ← 8 async unit tests
│
├── Dockerfile.notification           ← NEW: image for notification service
├── docker-compose.yml                ← NEW: orchestrates both containers
│
├── main.py                           ← MODIFIED (2 lines)
├── src/core/watch_helper.py          ← MODIFIED (remove ~35 lines, add ~12 lines)
├── src/scripts/pending_watch.py      ← MODIFIED (2 lines)
│
└── tests/core/test_token_client.py   ← NEW: 5 sync unit tests
```

---

## Step 1 — Build the Token Service

### `token_service/app/schemas.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class TokenResponse(BaseModel):
    access_token: str
    created_at:   datetime
    expires_at:   datetime
    token_type:   str = "Zoho-oauthtoken"

class HealthResponse(BaseModel):
    status:       str
    token_cached: bool
    expires_at:   Optional[datetime] = None
```

### `token_service/app/token_manager.py`

Design rules:
- `_TOKEN_CACHE` is a **module-level dict** — the only token slot in memory
- On refresh, `_TOKEN_CACHE = new_dict` replaces the object entirely (old one is GC'd immediately — no accumulation, no history)
- A **proactive asyncio background task** (`_refresh_loop`) sleeps until `expires_at - 120s`, then fetches. On failure it backs off 15s and retries — never crashes
- Uses `httpx.AsyncClient` (async-native, not `requests` which is blocking)
- **Grace period: 120 seconds** (2 minutes before expiry, per requirement)
- **`--workers 1`** in Dockerfile: multiple Uvicorn workers would each have their own `_TOKEN_CACHE`, causing N parallel Zoho refresh calls

```python
TOKEN_LIFETIME_SECONDS    = 3600
PROACTIVE_REFRESH_SECONDS = 120   # 2 min before expiry

_TOKEN_CACHE  = {"token": None, "created_at": None, "expires_at": None}
_refresh_task = None              # holds the single asyncio.Task

async def _fetch_fresh_token() -> dict:
    # httpx POST to ZOHO_ACCOUNTS_TOKEN_URL
    # reads ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN from env
    # returns {"token": str, "created_at": datetime, "expires_at": datetime}
    ...

async def _refresh_loop() -> None:
    # while True:
    #   sleep until (expires_at - 120s)
    #   _TOKEN_CACHE = await _fetch_fresh_token()   ← single assignment, old object GC'd
    #   on failure: sleep 15s and retry
    ...

async def start_background_refresh() -> None:
    # eager first fetch so /token never blocks on first call
    # then asyncio.create_task(_refresh_loop())
    ...

async def stop_background_refresh() -> None:
    # cancel and await the task cleanly
    ...

def get_cached_token() -> dict:
    # returns shallow copy of _TOKEN_CACHE
    # raises RuntimeError if token is None (not yet populated)
    ...
```

### `token_service/app/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from .token_manager import start_background_refresh, stop_background_refresh, get_cached_token
from .schemas import TokenResponse, HealthResponse

load_dotenv()

@asynccontextmanager
async def lifespan(app):
    await start_background_refresh()   # eager fetch + launch background task
    yield
    await stop_background_refresh()    # clean cancel on shutdown

app = FastAPI(title="Zoho Token Service", lifespan=lifespan)

@app.get("/token", response_model=TokenResponse)
async def get_token():
    # returns cached token; raises HTTP 503 if not yet ready
    ...

@app.get("/health", response_model=HealthResponse)
async def health():
    # returns {"status": "ok", "token_cached": bool, "expires_at": ...}
    ...
```

### `token_service/pyproject.toml`

```toml
[project]
name = "token-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "httpx>=0.27.0",
    "pydantic>=2,<3",
    "python-dotenv>=1.0.0",
    "certifi>=2026.1.4",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx"]
```

### `token_service/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx "pydantic>=2,<3" python-dotenv certifi
COPY app/ ./app/
EXPOSE 8000
# --workers 1 is INTENTIONAL: multiple workers = multiple _TOKEN_CACHE dicts = N Zoho refreshes
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

## Step 2 — Modify the Notification Service

### `src/core/watch_helper.py`

**REMOVE** lines 47-49 (token cache constants):
```python
TOKEN_LIFETIME_SECONDS      = 3600
TOKEN_RENEW_GRACE_SECONDS   = 10 * 60
TOKEN_CACHE: Dict[str, Any] = {"token": None, "created_at": None, "expires_at": None}
```

**REMOVE** from imports line 18: `ZohoAccessTokenResponse` (only used by `get_access_token()`).
Keep `ValidationError` — still used by `search_tickets()`.

**REMOVE** entire `get_access_token()` function (~lines 131-163).

**ADD** after `desk_headers()` (around line 172):
```python
TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://token-service:8000").rstrip("/")

def get_token_from_service() -> str:
    """Fetch the current Zoho access token from the internal token service."""
    url = f"{TOKEN_SERVICE_URL}/token"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as error:
        raise RuntimeError(f"Token service unreachable at {url}: {error}") from error
    token = (response.json().get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Token service returned empty access_token from {url}.")
    return token
```

Note: `requests` (synchronous) is correct here — `main.py` is a synchronous blocking loop, not asyncio.

### `main.py` — 2 line changes only

```python
# Line 10: change import
get_access_token,       →    get_token_from_service,

# Line 49: change call
token = get_access_token()   →   token = get_token_from_service()
```

### `src/scripts/pending_watch.py` — 2 line changes only

```python
# Line 8: change import
get_access_token,       →    get_token_from_service,

# Line 41: change call (standalone __main__ only)
shared_token = get_access_token()   →   shared_token = get_token_from_service()
```

Everything else in both files is untouched.

---

## Step 3 — Docker Compose

### `docker-compose.yml`

```yaml
services:

  token-service:
    build:
      context: ./token_service
    container_name: token-service
    env_file: .env
    networks: [internal]
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    # No ports: block → unreachable from outside Docker / internet

  notification-service:
    build:
      context: .
      dockerfile: Dockerfile.notification
    container_name: notification-service
    env_file: .env
    environment:
      TOKEN_SERVICE_URL: http://token-service:8000
    networks: [internal]
    depends_on:
      token-service:
        condition: service_healthy   # waits for health check before starting
    restart: unless-stopped
    # No ports: block → push-only, no inbound needed

networks:
  internal:
    driver: bridge
    # Shared bridge network for inter-service communication.
    # No published ports = unreachable from outside Docker.
    # Outbound internet (Zoho API, Teams webhooks) works via default Docker routing.
```

Key: `depends_on: service_healthy` prevents the notification service from starting before
the token service is ready — avoids first-cycle 503 errors on startup.

### `Dockerfile.notification`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir requests "pydantic>=2,<3" pytz python-dotenv certifi
COPY pyproject.toml .
COPY main.py .
COPY src/ ./src/
CMD ["python", "main.py"]
```

---

## Step 4 — Tests

### `token_service/tests/test_token_manager.py` (pytest + pytest-asyncio)

All tests mock `httpx.AsyncClient.post` with `AsyncMock`.

| Test | What it verifies |
|---|---|
| `test_fetch_fresh_token_populates_cache` | All three cache fields non-None after fetch |
| `test_get_cached_token_raises_when_empty` | `RuntimeError` when `_TOKEN_CACHE["token"]` is None |
| `test_get_cached_token_returns_copy` | Mutating returned dict does NOT change `_TOKEN_CACHE` |
| `test_proactive_refresh_replaces_cache` | After near-expiry simulation, cache has new token + later `expires_at` |
| `test_refresh_loop_retries_after_failure` | On `_fetch_fresh_token` exception, loop backs off 15s and retries |
| `test_background_task_created_on_startup` | `start_background_refresh()` sets `_refresh_task` to live `asyncio.Task` |
| `test_stop_cancels_task_cleanly` | `stop_background_refresh()` cancels without raising |
| `test_120s_grace_triggers_immediate_refresh` | With 90s remaining (< 120s threshold), loop fetches immediately |

### `tests/core/test_token_client.py` (standard pytest, no asyncio — matches existing test style)

All tests use `monkeypatch` to stub `requests.get`, same pattern as existing test files.

| Test | What it verifies |
|---|---|
| `test_get_token_from_service_happy_path` | Returns `access_token` string from mocked 200 response |
| `test_correct_url_called` | URL passed to `requests.get` is `{TOKEN_SERVICE_URL}/token` |
| `test_raises_on_connection_error` | `requests.RequestException` → `RuntimeError("unreachable")` |
| `test_raises_on_empty_token` | Response `{"access_token": ""}` → `RuntimeError` |
| `test_env_url_override` | `TOKEN_SERVICE_URL=http://custom:9000` → uses `http://custom:9000/token` |

---

## Infrastructure Decision

**Use Docker Compose on a single EC2 instance. No Kubernetes, no Terraform yet.**

- 2 containers on 1 host → Docker Compose is the right tool
- Kubernetes (EKS): overkill — adds control plane cost, IAM complexity, YAML manifests. Not justified for 2 services
- Security: Docker bridge network with no published ports = neither service reachable from internet; both have normal outbound to Zoho + Teams
- Terraform: useful later for EC2 + VPC + security group provisioning as code. Not needed now.

**When to graduate:**
- 3+ services needing independent scaling → move to **ECS Fargate** (simpler than EKS, managed control plane)
- Add **Terraform** at that point to manage VPC, security groups, task definitions as code
- Only consider **Kubernetes (EKS)** if you need multi-node orchestration or complex service mesh

---

## Verification Steps

```bash
# 1. Token service unit tests
cd token_service
uv run --with pytest --with pytest-asyncio pytest tests/ -q

# 2. Notification service tests (existing + new token client tests)
cd ..
uv run --with pytest pytest tests/ -q

# 3. Build and start both containers
docker compose up --build

# 4. Smoke test token service from inside container
docker exec token-service python -c \
  "import urllib.request, json; print(json.loads(urllib.request.urlopen('http://localhost:8000/token').read()))"

# 5. Check notification service logs for successful cycle
docker compose logs -f notification-service
# Expected every 30s: "[main] Sleeping for 30 seconds..." with no RuntimeError
```

---

## Environment Variables

The single `.env` file at repo root is shared by both containers.

Token service needs:
```
ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REFRESH_TOKEN=...
ZOHO_ACCOUNTS_TOKEN_URL=https://accounts.zoho.com/oauth/v2/token   # optional override
```

Notification service needs (in addition to existing vars):
```
TOKEN_SERVICE_URL=http://token-service:8000   # set automatically in docker-compose.yml
ZOHO_DESK_ORG_ID=...
ZOHO_DESK_BASE=https://desk.zoho.com
TEAMS_WEBHOOK_SUPERSTAT=...
TEAMS_WEBHOOK_CODE_STROKE=...
# ... all other TEAMS_WEBHOOK_* vars
# ... all other scheduling/product vars
```
