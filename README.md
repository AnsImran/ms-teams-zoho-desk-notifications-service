## 41-pacs-pros-automations

Python . scripts for automations (Zoho Desk + reporting).

## Local setup

Prereqs:
- Python `3.12` (see `.python-version`)
- `uv`

Install deps:
- `uv sync`

Run examples:
- `uv run python main.py`
- `uv run python "src/scripts/superstat_watch.py"`
- `uv run python "src/automatic report generation/generate_radiologist_productivity_reports.py" --help`

## CI (GitHub Actions)

Workflow: `.github/workflows/ci.yml`
- Runs on pushes and PRs to `main`
- Uses `uv sync --frozen`
- Runs a small import smoke-test
- Compiles the repo with `python -m compileall`

## CD (auto deploy on main)

There is a `Deploy (auto)` job inside `.github/workflows/ci.yml`:
- Runs only on `push` to `main`, after CI passes
- SSHes to your server and updates a git checkout in-place using `git fetch/reset`
- Optionally runs `DEPLOY_POST_COMMAND` on the server (for example, restart a service)

GitHub repo secrets required for auto-deploy:
- `DEPLOY_HOST` (example: `server.example.com`)
- `DEPLOY_USER` (example: `deploy`)
- `DEPLOY_GIT_PATH` (example: `/opt/automations/zoho-desk-beyond-native-automations`)
- `DEPLOY_SSH_KEY` (private key contents, multi-line)

Optional (auto-deploy):
- `DEPLOY_PORT` (default is `22`)
- `DEPLOY_POST_COMMAND` (example: `cd /opt/automations/zoho-desk-beyond-native-automations && uv sync --frozen && sudo systemctl restart superstat-watch`)

Server prep (auto-deploy):
1. Ensure the server is reachable by SSH from GitHub Actions.
2. Clone this repo on the server into `DEPLOY_GIT_PATH` (so it has an `origin` remote).
3. Add the deploy public key to `~deploy/.ssh/authorized_keys`.

## CD (manual rsync deploy)

Workflow: `.github/workflows/deploy-ssh.yml`
- Manual only (`workflow_dispatch`)
- Starts in safe mode by default: `dry_run=true`, `delete_extra=false`
- Excludes `.env` and `seen_superstat_ticket_ids.json` so you don't overwrite server-side config/state

GitHub repo secrets required for manual deploy:
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_REMOTE_PATH` (destination folder for rsync)
- `DEPLOY_SSH_KEY`

Optional (manual deploy):
- `DEPLOY_PORT`
- `DEPLOY_POST_COMMAND`
