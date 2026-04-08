"""Unit tests for env helpers and cooldown file deletion behavior in watch_helper."""  # Module purpose.

from __future__ import annotations

from pathlib import Path  # Build temp file paths in a platform-safe way.

from src.core import watch_helper  # Module under test.


def _product_config(last_sent_filename: str = "sent_test_notifications.json") -> watch_helper.ProductConfig:
    """Create a tiny ProductConfig used by helper-focused tests."""  # Shared fixture-like helper.
    return watch_helper.ProductConfig(
        name                  = "Test Product",
        target_product_names  = ["test product"],
        active_statuses       = {"Assigned"},
        teams_webhook_url = "TEAMS_WEBHOOK_TEST",
        last_sent_filename    = last_sent_filename,
    )


def test_env_required_returns_value_when_present(monkeypatch) -> None:
    """env_required should return env value when key is present and non-empty."""  # Happy path.
    monkeypatch.setenv("UNIT_TEST_ENV_REQUIRED_KEY", "present-value")
    assert watch_helper.env_required("UNIT_TEST_ENV_REQUIRED_KEY") == "present-value"


def test_env_required_raises_when_missing(monkeypatch) -> None:
    """env_required should raise RuntimeError with key name when missing."""  # Missing-key path.
    missing_key = "UNIT_TEST_ENV_REQUIRED_MISSING"
    monkeypatch.delenv(missing_key, raising=False)
    try:
        watch_helper.env_required(missing_key)
        raise AssertionError("Expected RuntimeError for missing env var.")
    except RuntimeError as error:
        assert missing_key in str(error)


def test_effective_notify_cooldown_seconds_precedence(monkeypatch) -> None:
    """Cooldown precedence should be: product override > global override > min-age fallback."""  # Contract.
    base_config = _product_config()
    base_config.min_age_minutes = 7

    monkeypatch.setattr(watch_helper, "NOTIFY_COOLDOWN_SECONDS", None)
    assert watch_helper.effective_notify_cooldown_seconds(base_config) == 420  # 7 * 60 fallback.

    monkeypatch.setattr(watch_helper, "NOTIFY_COOLDOWN_SECONDS", 33)
    assert watch_helper.effective_notify_cooldown_seconds(base_config) == 33   # Global override.

    base_config.notify_cooldown_seconds = 99
    assert watch_helper.effective_notify_cooldown_seconds(base_config) == 99   # Product override wins.


def test_delete_cooldown_file_removes_existing_file(monkeypatch, tmp_path: Path) -> None:
    """delete_cooldown_file should remove existing file from helper directory path."""  # Delete path.
    fake_module_path = tmp_path / "watch_helper.py"
    target_file      = tmp_path / "sent_test_notifications.json"
    target_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(watch_helper.os.path, "abspath", lambda _path: str(fake_module_path))
    config = _product_config(last_sent_filename=target_file.name)

    watch_helper.delete_cooldown_file(config)

    assert not target_file.exists()


def test_delete_cooldown_file_noops_when_missing(monkeypatch, tmp_path: Path) -> None:
    """delete_cooldown_file should silently do nothing when file does not exist."""  # Missing-file path.
    fake_module_path = tmp_path / "watch_helper.py"
    removed_paths: list[str] = []

    monkeypatch.setattr(watch_helper.os.path, "abspath", lambda _path: str(fake_module_path))
    monkeypatch.setattr(watch_helper.os, "remove", lambda path: removed_paths.append(path))

    config = _product_config(last_sent_filename="missing_file.json")
    watch_helper.delete_cooldown_file(config)

    assert removed_paths == []


def test_delete_cooldown_file_swallows_remove_errors(monkeypatch, tmp_path: Path) -> None:
    """delete_cooldown_file should not raise when os.remove fails."""  # Error-swallowing path.
    fake_module_path = tmp_path / "watch_helper.py"
    target_file      = tmp_path / "sent_test_notifications.json"
    target_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(watch_helper.os.path, "abspath", lambda _path: str(fake_module_path))

    def failing_remove(_path: str) -> None:
        raise PermissionError("simulated permission problem")

    monkeypatch.setattr(watch_helper.os, "remove", failing_remove)
    config = _product_config(last_sent_filename=target_file.name)

    watch_helper.delete_cooldown_file(config)  # Should not raise.

