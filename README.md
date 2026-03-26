# Teams Notifications Service (Zoho Desk)

This service sends automated Microsoft Teams notifications for selected Zoho Desk products, plus scheduled pending-ticket snapshots.

It is now fully registry-driven: products are configured in `src/scripts/product_registry.py` and environment variables.  
There are no standalone per-product watcher scripts in `src/scripts/`.

## What It Does

- Runs one long-lived loop (`main.py`).
- Reuses one Zoho access token across loop cycles (with in-memory caching).
- Fetches tickets once per cycle using the union of all product statuses.
- Fans out the shared result set across product configs.
- Applies unresolved + product match + age + cooldown checks.
- Sends Adaptive Cards to product-specific Teams webhooks.
- Runs pending summary snapshots on LA schedule windows.

## Current Product Registry

Production reminder products currently configured:

| Product Name | Prefix | Min Age (minutes) | Source Env Var |
|---|---|---:|---|
| Super-Stat | `SUPERSTAT` | 5 | `SUPERSTAT_MIN_AGE_MINUTES` |
| Code Stroke | `CODE_STROKE` | 5 | `CODE_STROKE_MIN_AGE_MINUTES` |
| Critical Findings | `CRITICAL_FINDINGS` | 5 | `CRITICAL_FINDINGS_MIN_AGE_MINUTES` |
| Amendments | `AMENDMENTS` | 60 | `AMENDMENTS_MIN_AGE_MINUTES` |
| NM Studies | `NM_STUDIES` | 30 | `NM_STUDIES_MIN_AGE_MINUTES` |
| IT / System Studies | `IT_SYSTEM_STUDIES` | 240 | `IT_SYSTEM_STUDIES_MIN_AGE_MINUTES` |
| Reading Requests | `READING_REQUESTS` | 30 | `READING_REQUESTS_MIN_AGE_MINUTES` |
| Password Reset | `PASSWORD_RESET` | 240 | `PASSWORD_RESET_MIN_AGE_MINUTES` |
| General | `GENERAL` | 240 | `GENERAL_MIN_AGE_MINUTES` |
| Consults & Physician Connection | `CONSULTS_AND_PHYSICIAN_CONNECTION` | 240 | `CONSULTS_AND_PHYSICIAN_CONNECTION_MIN_AGE_MINUTES` |

These values reflect the currently configured production `.env`.

Source of truth: `src/scripts/product_registry.py`.

## Matching Logic (Current)

- Matching is product-name based only.
- Regex/keyword matching is not used anymore.
- Product comparison is case-insensitive exact match against configured target product names.
- Ticket is treated unresolved when:
  - `status` is not `Resolved`, and
  - `statusType` is not `closed`.
- Cooldown precedence:
  1. `<PREFIX>_NOTIFY_COOLDOWN_SECONDS`
  2. global `NOTIFY_COOLDOWN_SECONDS`
  3. fallback to `<PREFIX>_MIN_AGE_MINUTES * 60`

## Repository Layout

```text
.
|-- main.py
|-- src
|   |-- core
|   |   |-- watch_helper.py
|   |   |-- test_teams_webhook.py
|   |   |-- zoho_probe_raw.py
|   |   `-- zoho_search_raw_payload.txt
|   |-- schema
|   |   `-- zoho_api_schemas.py
|   `-- scripts
|       |-- product_registry.py
|       |-- pending_watch.py
|       `-- pending_status_search_standalone.py
|-- tests
|   |-- core
|   `-- scripts
`-- .github/workflows
```

## Requirements

- Python `3.12` (see `.python-version`)
- `uv`

Install:

```bash
uv sync
```

## Environment Configuration

### Required Zoho Credentials

- `ZOHO_REFRESH_TOKEN`
- `ZOHO_CLIENT_ID`
- `ZOHO_CLIENT_SECRET`
- `ZOHO_DESK_ORG_ID`

### Core Runtime Controls

- `CHECK_EVERY_SECONDS` (default `30`)
- `TZ_NAME` (default `America/Los_Angeles`)
- `MAX_AGE_HOURS` (default `24`)
- `MIN_AGE_MINUTES` (default `5`)
- `NOTIFY_COOLDOWN_SECONDS` (optional global override)
- `PRODUCT_WORKERS` (optional)
- `NOTIFY_WORKERS` (optional)
- `PAGE_LIMIT` (default `50`)
- `PAGE_SIZE` (default `100`)
- `ZOHO_DESK_BASE` (default `https://desk.zoho.com`)
- `ZOHO_ACCOUNTS_TOKEN_URL` (default `https://accounts.zoho.com/oauth/v2/token`)
- `MAGIC_TEST_TRIGGER_PHRASE` (optional magic-phrase trigger)

### Product Configuration Pattern

Per product prefix, configure:

- `<PREFIX>_TARGET_PRODUCT_NAMES` (comma-separated product names)
- `<PREFIX>_ACTIVE_STATUSES` (comma-separated statuses)
- `<PREFIX>_MAX_AGE_HOURS`
- `<PREFIX>_MIN_AGE_MINUTES`
- `<PREFIX>_NOTIFY_COOLDOWN_SECONDS`

Currently used prefixes:

- `SUPERSTAT`
- `CODE_STROKE`
- `CRITICAL_FINDINGS`
- `AMENDMENTS`
- `NM_STUDIES`
- `IT_SYSTEM_STUDIES`
- `READING_REQUESTS`
- `PASSWORD_RESET`
- `GENERAL`
- `CONSULTS_AND_PHYSICIAN_CONNECTION`

Banner text variables currently used:

- `CRITICAL_FINDINGS_BANNER_TEXT`
- `NM_STUDIES_BANNER_TEXT`

### Teams Webhook Variables

- `TEAMS_WEBHOOK_SUPERSTAT`
- `TEAMS_WEBHOOK_CODE_STROKE`
- `TEAMS_WEBHOOK_CRITICAL_FINDINGS`
- `TEAMS_WEBHOOK_AMENDMENTS`
- `TEAMS_WEBHOOK_NM_STUDIES`
- `TEAMS_WEBHOOK_IT_SYSTEM_STUDIES`
- `TEAMS_WEBHOOK_READING_REQUESTS`
- `TEAMS_WEBHOOK_PASSWORD_RESET`
- `TEAMS_WEBHOOK_GENERAL`
- `TEAMS_WEBHOOK_CONSULTS_AND_PHYSICIAN_CONNECTION`
- `TEAMS_WEBHOOK_PENDING`

### Pending Summary Configuration

- `PENDING_STATUS_NAME` (default `PENDING`)
- `PENDING_REPORT_TIMES_LA` (default `04:00;12:00;20:00`)
- `PENDING_REPORT_WINDOW_SECONDS` (default `120`)

## Running

Run the full service:

```bash
uv run python main.py
```

Run pending summary watcher once (schedule-aware):

```bash
uv run python src/scripts/pending_watch.py
```

Run pending search probe:

```bash
uv run python src/scripts/pending_status_search_standalone.py --help
```

Run webhook smoke test:

```bash
uv run python src/core/test_teams_webhook.py --title "Webhook Smoke Test" --note "Test message"
```

## Testing

Run all tests:

```bash
uv run --with pytest pytest -q
```

Run specific suites:

```bash
uv run --with pytest pytest tests/core/test_watch_helper_search_tickets.py -q
uv run --with pytest pytest tests/scripts/test_product_watchers.py -q
```

## State Files and Startup Behavior

- Cooldown and pending-slot state files are written under `src/core/`.
- On service startup, product cooldown files and pending slot-state file are deleted intentionally.
- Result: each process restart starts with a fresh state.

## CI/CD

### CI

Workflow: `.github/workflows/ci.yml`

- Runs on pushes and PRs to `main`.
- Installs dependencies via `uv sync --frozen`.
- Runs import smoke checks.
- Compiles Python sources.

### Auto Deploy on `main`

Also in `.github/workflows/ci.yml`:

- Deploy job runs only on `push` to `main` after CI job.
- SSHes to server checkout and resets to `origin/main`.
- Optional post-deploy command can run via secret.

### Manual SSH Deploy

Workflow: `.github/workflows/deploy-ssh.yml`

- Manual trigger (`workflow_dispatch`).
- Supports `dry_run` and optional `--delete` behavior via inputs.
- Uses `rsync` with excludes (including `.env`).

## How to Add a New Product (Current Flow)

1. Add a new entry to `PRODUCT_REGISTRY` in `src/scripts/product_registry.py`.
2. Choose:
   - `prefix`
   - display `name`
   - `teams_webhook_env_var`
   - `last_sent_filename`
   - default target product behavior
3. Add corresponding env vars in `.env`.
4. Add ignore rule for the new `sent_<product>_notifications.json` state file (recommended).
5. Update `tests/scripts/test_product_watchers.py` with the new case.

No additional script module is required for a new product.
