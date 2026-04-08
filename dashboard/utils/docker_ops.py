"""Docker operations for the dashboard — restart the notification service."""  # Module purpose.

import docker                                                                 # Docker SDK for container management.


def restart_notification_service(timeout: int = 10) -> str:                   # Restart the notification container.
    """Restart the notification-service container and return status message."""  # Docstring in plain words.
    try:                                                                       # Wrap in try so dashboard never crashes.
        client    = docker.from_env()                                          # Connect to Docker daemon via socket.
        container = client.containers.get("notification-service")              # Find the notification container.
        container.restart(timeout=timeout)                                     # Restart with grace period.
        return "Notification service restarted successfully."                  # Success message.
    except docker.errors.NotFound:                                             # Container not found.
        return "ERROR: notification-service container not found."              # Clear error for the UI.
    except docker.errors.APIError as error:                                    # Docker API error.
        return f"ERROR: Docker API error: {error}"                            # Clear error for the UI.
    except Exception as error:                                                 # Any other error.
        return f"ERROR: {error}"                                              # Clear error for the UI.


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
