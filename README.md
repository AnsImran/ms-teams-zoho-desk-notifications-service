# 41 PACS Pros Automations

This repository contains Python automations for Zoho Desk that go beyond native product-level alerting and reporting workflows.

It is built to be efficient, maintainable, and easy to extend:
- One shared Zoho access token is reused across all product watchers.
- One shared search call is fan-out processed for multiple products.
- One loop can send multiple product-specific Teams notifications in parallel.
- New products can be added by configuration and a thin script module, without rewriting core logic.

## Why this exists

Native helpdesk rules can be limited when you need control over notification timing.

This project provides:
- Product-specific unresolved ticket reminders (currently Super-Stat, Code Stroke, Critical Findings).
- Scheduled pending-ticket summary snapshots.
- A shared automation core with schema validation on Zoho API responses.
- Strong operational control via environment variables (polling, age windows, cooldowns, schedules, concurrency).

## High-level architecture

1. `main.py` runs a continuous polling loop.
2. It fetches/reuses one Zoho token and uses it for all watchers in that cycle.
3. It fetches shared ticket results once for the reminder products and then runs each product watcher in parallel.
4. Each watcher applies product-specific matching + cooldown rules and posts Adaptive Cards to the corresponding Teams webhook.
5. Pending-summary watcher runs on schedule slots and sends a consolidated pending snapshot.

## Repository structure

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
|       |-- superstat_watch.py
|       |-- code_stroke_watch.py
|       |-- critical_findings_watch.py
|       |-- pending_watch.py
|       `-- pending_status_search_standalone.py
`-- .github/workflows
```

Folder roles:
- `src/core`: Shared runtime engine (token handling, search, matching, cooldown, Teams payload/posting, scheduling, state files).
- `src/schema`: Pydantic v2 models that validate Zoho token and ticket search responses.
- `src/scripts`: Product-specific and standalone script entry modules.

Note:
- `src/automatic report generation/` is intentionally ignored in this repo (`.gitignore`) and kept local-only.

## Token efficiency model

The system uses a long-lived refresh token to obtain one-hour Zoho access tokens.  
`watch_helper.get_access_token()` caches access tokens in-memory and refreshes only when needed (grace window before expiry), so repeated loops do not request unnecessary tokens.

Result:
- Less API overhead.
- Lower chance of rate/credential churn.
- Cleaner behavior when running multiple product watchers together.

## Current watcher set

Reminder watchers (shared fetch + product fan-out):
- Super-Stat
- Code Stroke
- Critical Findings

Scheduled summary watcher:
- Pending ticket summary snapshots to Teams at configured LA times.

You can extend this to any number of products by adding more watcher modules using `ProductConfig`.

## Local setup

Prerequisites:
- Python `3.12` (see `.python-version`)
- `uv`

Install:

```bash
uv sync
```

## Environment configuration

Required Zoho credentials:
- `ZOHO_REFRESH_TOKEN`
- `ZOHO_CLIENT_ID`
- `ZOHO_CLIENT_SECRET`
- `ZOHO_DESK_ORG_ID`

Common runtime controls:
- `CHECK_EVERY_SECONDS` (default `30`)
- `MAX_AGE_HOURS` (default `24`)
- `MIN_AGE_MINUTES` (default `5`)
- `NOTIFY_COOLDOWN_SECONDS` (optional global override; if unset, cooldown defaults to each product's `min_age_minutes`)
- `TZ_NAME` (default `America/Los_Angeles`)
- `PRODUCT_WORKERS` (optional thread count for product cycles)
- `NOTIFY_WORKERS` (optional thread count for Teams post workers)

Product-specific controls:
- `SUPERSTAT_*` (statuses, regex, product names, age windows, webhook)
- `CODE_STROKE_*` (statuses, regex, product names, age windows, webhook)
- `CRITICAL_FINDINGS_*` (statuses, regex, product names, age windows, webhook, banner text)

Pending summary controls:
- `TEAMS_WEBHOOK_PENDING`
- `PENDING_STATUS_NAME` (default `PENDING`)
- `PENDING_REPORT_TIMES_LA` (default `04:00;12:00;20:00`)
- `PENDING_REPORT_WINDOW_SECONDS` (default `120`)

Teams webhooks:
- `TEAMS_WEBHOOK_SUPERSTAT`
- `TEAMS_WEBHOOK_CODE_STROKE`
- `TEAMS_WEBHOOK_CRITICAL_FINDINGS`
- `TEAMS_WEBHOOK_PENDING`

## Running

Run all automations (recommended):

```bash
uv run python main.py
```

Run one reminder watcher standalone:

```bash
uv run python src/scripts/superstat_watch.py
uv run python src/scripts/code_stroke_watch.py
uv run python src/scripts/critical_findings_watch.py
```

Run pending watcher standalone:

```bash
uv run python src/scripts/pending_watch.py
```

Run pending search probe:

```bash
uv run python src/scripts/pending_status_search_standalone.py --help
```

## Testing

Run all tests:

```bash
uv run --with pytest pytest -q
```

Run only the `search_tickets` unit test module:

```bash
uv run --with pytest pytest tests/core/test_watch_helper_search_tickets.py -q
```

Fixture notes:
- Raw Zoho payload fixture used by tests is stored at `tests/fixtures/zoho_tickets_search_raw_payload.txt`.
- The test parser extracts JSON content from the `RAW RESPONSE TEXT:` block in that file.

## Adding another product watcher

1. Create `src/scripts/<new_product>_watch.py`.
2. Define a `ProductConfig` with:
   - `name`
   - `keyword_regex`
   - `target_product_names`
   - `active_statuses`
   - `teams_webhook_env_var`
   - `last_sent_filename`
   - optional `max_age_hours`, `min_age_minutes`, `notify_cooldown_seconds`, `card_banner_text`
3. Implement `run_cycle(token, pre_fetched_tickets=None)` by delegating to `run_product_loop_once(...)`.
4. Wire it into `main.py` for shared-fetch parallel execution.
5. Add env vars for statuses, patterns, and webhook.

## State files and cooldown behavior

- Cooldown and pending-slot state are stored as JSON files under `src/core/`.
- Startup cleanup currently deletes these state files so each process start begins fresh.
- During runtime, cooldown checks use dynamic values (product-specific `min_age_minutes` by default, or explicit cooldown overrides when configured).

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml`
- Runs on pushes and PRs to `main`.
- Installs with `uv sync --frozen`.
- Runs import smoke checks.
- Compiles Python sources with `python -m compileall`.

## CD (Auto deploy on `main`)

`Deploy (auto)` job in `.github/workflows/ci.yml`:
- Runs only on `push` to `main` after CI succeeds.
- SSHes to server and hard-resets deployment checkout to `origin/main`.
- Can run optional `DEPLOY_POST_COMMAND` after sync.

Required GitHub secrets:
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_GIT_PATH`
- `DEPLOY_SSH_KEY`

Optional secrets:
- `DEPLOY_PORT` (default `22`)
- `DEPLOY_POST_COMMAND`

## CD (Manual rsync deploy)

Workflow: `.github/workflows/deploy-ssh.yml`
- Manual trigger (`workflow_dispatch`).
- Safe defaults: `dry_run=true`, `delete_extra=false`.
- Excludes `.env` and cache/state artifacts to avoid clobbering local server config.

Required GitHub secrets:
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_REMOTE_PATH`
- `DEPLOY_SSH_KEY`

Optional secrets:
- `DEPLOY_PORT`
- `DEPLOY_POST_COMMAND`
