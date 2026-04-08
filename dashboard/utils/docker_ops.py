"""Docker operations for the dashboard — rebuild the notification service."""  # Module purpose.

import subprocess  # Run shell commands for docker compose.
import time        # Sleep between health-check polls.
import docker      # Docker SDK for container status queries.


COMPOSE_DIR         = "/app"   # Directory containing docker-compose.yml inside the dashboard container.
HEALTH_POLL_SECONDS = 3        # Seconds between health-check polls after rebuild.
HEALTH_TIMEOUT      = 120      # Max seconds to wait for the service to become healthy.


def rebuild_notification_service() -> str:                                     # Full tear-down + rebuild of the notification container.
    """Stop, remove, rebuild, and restart the notification-service container."""
    try:
        # 1. Stop the running container.
        subprocess.run(
            ["docker", "compose", "stop", "notification-service"],
            capture_output=True, text=True, timeout=60, cwd=COMPOSE_DIR,
        )

        # 2. Remove the stopped container so nothing lingers.
        subprocess.run(
            ["docker", "compose", "rm", "-f", "notification-service"],
            capture_output=True, text=True, timeout=30, cwd=COMPOSE_DIR,
        )

        # 3. Rebuild the image and start a fresh container.
        result = subprocess.run(
            ["docker", "compose", "up", "--build", "-d", "--force-recreate", "notification-service"],
            capture_output=True, text=True, timeout=300, cwd=COMPOSE_DIR,
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()}"

        # 4. Prune dangling images so old layers don't fill disk.
        subprocess.run(
            ["docker", "image", "prune", "-f"],
            capture_output=True, text=True, timeout=30,
        )

        # 5. Wait until the container is running.
        healthy = wait_for_healthy()
        if not healthy:
            return "ERROR: Service did not become healthy within the timeout."

        return "ok"

    except subprocess.TimeoutExpired:
        return "ERROR: Rebuild timed out."
    except Exception as error:
        return f"ERROR: {error}"


def wait_for_healthy() -> bool:                                                # Poll until the notification-service container is running.
    """Poll container status until it reports 'running' or we time out."""
    elapsed = 0
    while elapsed < HEALTH_TIMEOUT:
        status = get_notification_service_status()
        if status["status"] == "running":
            return True
        time.sleep(HEALTH_POLL_SECONDS)
        elapsed += HEALTH_POLL_SECONDS
    return False


def get_notification_service_status() -> dict:                                 # Get container status info.
    """Return status info about the notification-service container."""
    try:
        client    = docker.from_env()
        container = client.containers.get("notification-service")
        return {
            "status":  container.status,
            "started": container.attrs.get("State", {}).get("StartedAt", ""),
            "image":   container.image.tags[0] if container.image.tags else "",
        }
    except Exception as error:
        return {"status": f"error: {error}", "started": "", "image": ""}
