# Teams Notifications Service (Zoho Desk)

Automated Microsoft Teams notifications for Zoho Desk tickets, plus scheduled pending-ticket summaries.

Fully registry-driven: products are configured in `src/scripts/product_registry.py` and environment variables — no standalone per-product scripts.

## Architecture

```mermaid
flowchart TB
    subgraph EC2["EC2 Server"]
        direction TB
        subgraph docker_net["Docker Network (zoho-token-service_default)"]
            direction LR
            TS["Token Service<br>(FastAPI)<br>Port 8000<br>Auto-refreshes every ~58 min"]
            NS["Notification Service<br>(Python 3.12)<br>main.py"]
        end
    end

    subgraph Zoho["Zoho Cloud"]
        ZA["Zoho Accounts<br>OAuth Token Endpoint"]
        ZD["Zoho Desk API<br>/api/v1/tickets/search"]
    end

    subgraph Teams["Microsoft Teams"]
        WH1["Product Webhooks<br>(11 channels)"]
        WH2["Pending Summary<br>Webhook"]
    end

    subgraph Config["Configuration"]
        ENV[".env file<br>Zoho credentials<br>Product names<br>Webhook URLs<br>Timing controls"]
        REG["product_registry.py<br>11 product definitions"]
    end

    TS -- "refresh_token grant" --> ZA
    NS -- "GET /token" --> TS
    NS -- "GET /tickets/search<br>?productName=...&status=..." --> ZD
    NS -- "POST Adaptive Card" --> WH1
    NS -- "POST Pending Summary" --> WH2
    ENV -. "loads" .-> NS
    REG -. "builds ProductConfig" .-> NS
```

## Polling Cycle (every 30 seconds)

```mermaid
flowchart LR
    A["Fetch Token<br>from Token Service"] --> B["Search Zoho<br>All products + statuses<br>in one API call"]
    B --> C["Fan Out<br>to 11 product workers<br>(thread pool)"]
    C --> D{"For each ticket:<br>1. Status active?<br>2. Product match?<br>3. Old enough?<br>4. Cooldown passed?"}
    D -- "Yes" --> E["Send Teams<br>Adaptive Card"]
    D -- "No" --> F["Skip"]
    E --> G["Update<br>cooldown file"]
```

## How the Search Query Works

```mermaid
flowchart TB
    subgraph build["Query Construction"]
        S["Statuses from all products<br>→ Assigned,Escalated,Pending"]
        P["Product names from .env<br>→ Amendments,Code Stroke Alert,<br>Critical Finding,GENERAL,..."]
    end

    subgraph call["Single API Call"]
        Q["GET /api/v1/tickets/search<br>?status=Assigned,Escalated,Pending<br>&productName=Amendments,Code Stroke Alert,...<br>&sortBy=-createdTime<br>&limit=100"]
    end

    subgraph filter["Local Filtering (per product worker)"]
        F1["Product name match?"]
        F2["Age ≥ min_age_minutes?"]
        F3["Cooldown expired?"]
        F4["Magic test phrase?"]
    end

    S --> Q
    P --> Q
    Q --> F1 --> F2 --> F3 --> F4
```

## Pending Summary Schedule

```mermaid
flowchart LR
    subgraph schedule["LA Timezone Schedule"]
        T1["04:00 AM"]
        T2["12:00 PM"]
        T3["08:00 PM"]
    end

    T1 & T2 & T3 --> W["±120 sec<br>send window"]
    W --> S["Search Zoho<br>status=PENDING<br>all time"]
    S --> C["Build summary card<br>ticket #, subject,<br>assignee, age"]
    C --> P["POST to<br>Pending Webhook"]
```

## Current Product Registry

| Product | Prefix | Min Age | Teams Webhook Env Var |
|---|---|---:|---|
| Super-Stat | `SUPERSTAT` | 5 min | `TEAMS_WEBHOOK_SUPERSTAT` |
| Code Stroke | `CODE_STROKE` | 5 min | `TEAMS_WEBHOOK_CODE_STROKE` |
| Critical Findings | `CRITICAL_FINDINGS` | 5 min | `TEAMS_WEBHOOK_CRITICAL_FINDINGS` |
| Amendments | `AMENDMENTS` | 60 min | `TEAMS_WEBHOOK_AMENDMENTS` |
| NM Studies | `NM_STUDIES` | 30 min | `TEAMS_WEBHOOK_NM_STUDIES` |
| IT / System Studies | `IT_SYSTEM_STUDIES` | 240 min | `TEAMS_WEBHOOK_IT_SYSTEM_STUDIES` |
| Reading Requests | `READING_REQUESTS` | 30 min | `TEAMS_WEBHOOK_READING_REQUESTS` |
| Password Reset | `PASSWORD_RESET` | 240 min | `TEAMS_WEBHOOK_PASSWORD_RESET` |
| Unlock Account | `UNLOCK_ACCOUNT` | 240 min | `TEAMS_WEBHOOK_PASSWORD_RESET` |
| General | `GENERAL` | 240 min | `TEAMS_WEBHOOK_GENERAL` |
| Consults & Physician Connection | `CONSULTS_AND_PHYSICIAN_CONNECTION` | 240 min | `TEAMS_WEBHOOK_CONSULTS_AND_PHYSICIAN_CONNECTION` |

Password Reset and Unlock Account are separate products that share the same Teams webhook.

Source of truth: `src/scripts/product_registry.py`.

## Matching Logic

- Product names are sent directly in the Zoho API query (`productName` parameter) for server-side filtering.
- Local matching is case-insensitive exact match against configured target product names.
- A ticket qualifies for alert when **all** conditions are met:
  1. Status is in the product's active statuses set
  2. Product name matches (case-insensitive)
  3. Ticket age ≥ `min_age_minutes`
  4. Cooldown window has passed since last notification for this ticket
- Cooldown precedence:
  1. `<PREFIX>_NOTIFY_COOLDOWN_SECONDS`
  2. Global `NOTIFY_COOLDOWN_SECONDS`
  3. Fallback: `<PREFIX>_MIN_AGE_MINUTES × 60`

## Repository Layout

```text
.
├── main.py                          # Entry point — infinite polling loop
├── Dockerfile.notification          # Container image for the notification service
├── docker-compose.yml               # Orchestration (joins token service network)
├── src/
│   ├── core/
│   │   └── watch_helper.py          # Shared logic (~700 lines): token, search, cards, filtering
│   ├── schema/
│   │   └── zoho_api_schemas.py      # Pydantic models for Zoho API validation
│   └── scripts/
│       ├── product_registry.py      # Declarative config for all 11 products
│       └── pending_watch.py         # Pending summary scheduler
├── scripts/
│   └── create_test_tickets.py       # Creates one test ticket per product (end-to-end testing)
├── tests/
│   ├── core/                        # Unit tests for watch_helper logic
│   └── scripts/                     # Parameterized tests for product registry
├── credentials/                     # SSH keys and server connection info (git-ignored)
└── .github/workflows/
    └── ci.yml                       # CI (test on push) + CD (deploy on main)
```

## Deployment

### Docker Compose (Production)

The notification service runs as a single Docker container that connects to the centralized Zoho token service's Docker network:

```yaml
# docker-compose.yml
services:
  notification-service:
    build: { dockerfile: Dockerfile.notification }
    environment:
      TOKEN_SERVICE_URL: http://token-service:8000
    networks:
      - zoho-token-service_default

networks:
  zoho-token-service_default:
    external: true
```

Deploy commands:
```bash
docker compose up --build -d     # Start/rebuild
docker compose logs -f           # Watch logs
docker compose down              # Stop
```

### CI/CD

Workflow: `.github/workflows/ci.yml`

- **Test job**: runs on push to `main`/`dev` and PRs to `main` — installs deps, compiles, runs all tests.
- **Deploy job**: runs only on push to `main` after tests pass — SSHes to server, pulls latest, rebuilds container.

## Environment Configuration

### Token Service

- `TOKEN_SERVICE_URL` (default `http://host.docker.internal:8000`) — overridden to `http://token-service:8000` in Docker Compose.

### Core Runtime Controls

| Variable | Default | Purpose |
|---|---|---|
| `CHECK_EVERY_SECONDS` | `30` | Polling interval |
| `TZ_NAME` | `America/Los_Angeles` | Timezone for all time calculations |
| `MIN_AGE_MINUTES` | `5` | Global default minimum ticket age before alerting |
| `NOTIFY_COOLDOWN_SECONDS` | — | Optional global cooldown override |
| `PAGE_SIZE` | `100` | Zoho search page size |
| `PAGE_LIMIT` | `50` | Max pages to fetch |
| `ZOHO_DESK_ORG_ID` | — | **Required**: Zoho organization ID |
| `ZOHO_DESK_BASE` | `https://desk.zoho.com` | Zoho Desk API base URL |

### Per-Product Configuration

Each product prefix supports:
- `<PREFIX>_TARGET_PRODUCT_NAMES` — comma-separated product names (original casing preserved)
- `<PREFIX>_ACTIVE_STATUSES` — comma-separated statuses (default: `Assigned,Pending,Escalated`)
- `<PREFIX>_MIN_AGE_MINUTES` — minimum age before alerting
- `<PREFIX>_NOTIFY_COOLDOWN_SECONDS` — cooldown between repeat alerts

### Pending Summary

| Variable | Default | Purpose |
|---|---|---|
| `PENDING_STATUS_NAME` | `PENDING` | Status text for pending tickets |
| `PENDING_REPORT_TIMES_LA` | `04:00;12:00;20:00` | Scheduled report times (LA timezone) |
| `PENDING_REPORT_WINDOW_SECONDS` | `120` | Send window around each scheduled time |

## Running Locally

```bash
uv sync                                          # Install dependencies
uv run python main.py                            # Run the full service
uv run python src/scripts/pending_watch.py       # Run pending summary once
uv run --with pytest pytest -q                   # Run all tests
```

## How to Add a New Product

1. Add a new entry to `PRODUCT_REGISTRY` in `src/scripts/product_registry.py`.
2. Set `prefix`, `name`, `teams_webhook_env_var`, `last_sent_filename`, and `default_target_product_names`.
3. Add corresponding env vars in `.env` (at minimum: `<PREFIX>_TARGET_PRODUCT_NAMES` and the webhook).
4. Add a test case in `tests/scripts/test_product_watchers.py`.
5. Deploy — no new script module needed.

## State Files

- Cooldown files (`sent_<product>_notifications.json`) are written under `src/core/`.
- Pending slot state (`sent_pending_summary_slots.json`) tracks which time slots have been sent.
- **All state files are deleted on startup** — each restart begins fresh.
