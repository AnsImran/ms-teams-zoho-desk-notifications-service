# Deployment and Architecture

This document explains how the system is built, deployed, and updated. It covers the
containers, how they connect, what happens when you push code, and how the system ensures
only the container that actually changed gets restarted.

---

## The containers

The service runs as **two Docker containers** on a single EC2 server:

| Container | What it does | Dockerfile |
|-----------|-------------|------------|
| **notification-service** | Polls Zoho Desk every 30 seconds and sends Teams alerts | `Dockerfile.notification` |
| **dashboard** | Streamlit admin UI for adding/removing products | `Dockerfile.dashboard` |

A third container, **token-service**, lives in a separate repository and manages Zoho OAuth
tokens. The two containers above connect to it over a shared Docker network.

---

## Which files belong to which container

Each container only includes the files it needs. This is what makes selective rebuilds
possible — changing a dashboard file does not affect the notification service image.

**notification-service** copies:
```
main.py
src/
config/
entrypoint.sh
```

**dashboard** copies:
```
dashboard/
src/
```

`src/` is shared. A change there affects both containers.

---

## How deployment works

When you push to `main`, three things happen automatically via GitHub Actions:

### Step 1: Tests

The CI runner installs dependencies and runs the test suite. If tests fail, nothing
gets deployed.

### Step 2: Build and push images

The CI runner builds both Docker images and pushes them to **GitHub Container Registry**
(GHCR) at:

- `ghcr.io/ansimran/teams-notifications-service/notification-service:latest`
- `ghcr.io/ansimran/teams-notifications-service/dashboard:latest`

The build uses **registry-based caching**: layers that haven't changed are pulled from
the cache in GHCR rather than rebuilt from scratch. This means if you only changed a
dashboard file, the notification-service image is built entirely from cached layers and
produces the **exact same image digest** as the previous push.

Three settings make the digest deterministic (identical when nothing changed):

- `provenance: false` — disables non-deterministic provenance attestations
- `sbom: false` — disables non-deterministic SBOM attestations
- `SOURCE_DATE_EPOCH: 0` — fixes all timestamps in the image to a constant value

### Step 3: Deploy to EC2

The CI runner SSHs into the EC2 server and runs:

```bash
docker compose pull              # Download images from GHCR
docker compose up -d --remove-orphans  # Start/recreate containers
docker image prune -f            # Clean up old unused images
```

`docker compose pull` compares the image digest on GHCR with the one already on the
server. If the digest is the same (because nothing changed for that service), it skips
the download. `docker compose up -d` then only recreates containers whose image actually
changed.

---

## Selective rebuilds in practice

| What you changed | notification-service | dashboard |
|-----------------|---------------------|-----------|
| A file under `dashboard/` | Stays running | Recreated |
| `main.py` or a file under `config/` | Recreated | Stays running |
| A file under `src/` | Recreated | Recreated |
| `docker-compose.yml` or CI config | Depends on what changed | Depends on what changed |

---

## How product config changes work (no restart needed)

The notification service **re-reads `products.json` every 30 seconds** during its polling
loop. When you add or remove a product via the dashboard:

1. The dashboard writes to `products.json` on a shared Docker volume
2. The dashboard UI blocks for ~35 seconds with a spinner
3. The notification service picks up the change on its next polling cycle

No container restart or rebuild is needed for product configuration changes.

---

## Files that live on the server (not in the repo)

These files contain secrets and are never committed to Git. They must be created manually
on the server (one-time setup) and persist across deployments.

| File | Purpose | Used by |
|------|---------|---------|
| `.env` | Zoho org ID, webhook URLs, polling config | Both containers |
| `.streamlit/secrets.toml` | Dashboard login credentials (bcrypt hash) | Dashboard only |

Both are mounted into containers as read-only volumes via `docker-compose.yml`.

---

## Setting up a new server from scratch

1. **Clone the repo** to the server
2. **Create `.env`** with the required environment variables
3. **Create `.streamlit/secrets.toml`** with dashboard auth credentials:
   ```toml
   [auth]
   username = "admin"
   name = "Admin"
   password_hash = "<bcrypt hash>"
   cookie_key = "<random hex string>"
   ```
4. **Log in to GHCR** so Docker can pull images:
   ```bash
   echo "<PAT token>" | docker login ghcr.io -u <github-username> --password-stdin
   ```
5. **Start the services:**
   ```bash
   docker compose pull
   docker compose up -d
   ```

From this point on, every push to `main` deploys automatically.

---

## GitHub secrets required

These are configured in the repo under Settings > Secrets and variables > Actions:

| Secret | Purpose |
|--------|---------|
| `DEPLOY_HOST` | EC2 server IP or hostname |
| `DEPLOY_USER` | SSH username (e.g., `ubuntu`) |
| `DEPLOY_SSH_KEY` | SSH private key for the server |
| `DEPLOY_GIT_PATH` | Absolute path to the repo on the server |
| `DEPLOY_PORT` | SSH port (optional, defaults to 22) |
| `GHCR_USER` | GitHub username for pulling images |
| `GHCR_TOKEN` | GitHub PAT with `read:packages` scope |
