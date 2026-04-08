"""Docker operations for the dashboard — restart the notification service."""  # Module purpose.

import subprocess                                                              # Run shell commands for docker compose.
import docker                                                                  # Docker SDK for container status queries.


COMPOSE_DIR = "/app"                                                           # Directory containing docker-compose.yml inside the dashboard container.


def restart_notification_service() -> str:                                     # Restart the notification container via docker compose.
    """Restart the notification-service using docker compose."""               # Docstring in plain words.
    try:                                                                       # Wrap in try so dashboard never crashes.
        result = subprocess.run(                                               # Call docker compose restart as a shell command.
            ["docker", "compose", "restart", "notification-service"],          # Compose-aware restart command.
            capture_output = True,                                             # Capture stdout and stderr.
            text           = True,                                             # Return strings, not bytes.
            timeout        = 30,                                               # Safety timeout.
            cwd            = COMPOSE_DIR,                                      # Run from the compose directory.
        )                                                                      # End subprocess call.
        if result.returncode == 0:                                             # If command succeeded...
            return "Notification service restarted successfully."              # Success message.
        return f"ERROR: {result.stderr.strip()}"                               # Return stderr on failure.
    except subprocess.TimeoutExpired:                                          # If restart took too long...
        return "ERROR: Restart timed out after 30 seconds."                    # Timeout message.
    except Exception as error:                                                 # Any other error.
        return f"ERROR: {error}"                                               # Clear error for the UI.


def get_notification_service_status() -> dict:                                 # Get container status info.
    """Return status info about the notification-service container."""         # Docstring in plain words.
    try:                                                                       # Wrap in try so dashboard never crashes.
        client    = docker.from_env()                                          # Connect to Docker daemon via socket.
        container = client.containers.get("notification-service")              # Find the notification container.
        return {                                                               # Return status dict.
            "status":  container.status,                                       # e.g., "running", "exited".
            "started": container.attrs.get("State", {}).get("StartedAt", ""),  # Container start time.
            "image":   container.image.tags[0] if container.image.tags else "", # Image name.
        }                                                                      # End status dict.
    except Exception as error:                                                 # Any error.
        return {"status": f"error: {error}", "started": "", "image": ""}       # Fallback status.
