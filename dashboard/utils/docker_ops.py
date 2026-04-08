"""Docker operations for the dashboard — check notification service status."""  # Module purpose.

import docker  # Docker SDK for container status queries.


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
