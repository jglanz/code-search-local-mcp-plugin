import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_search_local import harnesses, install, lifecycle
from code_search_local.storage import ServiceLock, atomic_json

ID = "code-search-local@code-search-local"


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "run", Mock())
    target = harnesses.targets(("codex",))[0]
    harnesses.save_document(
        target["primary"],
        {
            "plugins": {ID: {"enabled": False}},
            "mcp_servers": {"code-search-local": {"url": "http://test"}, "other": {}},
        },
    )
    unit = install.unit_path()
    unit.parent.mkdir(parents=True)
    unit.write_text("test unit")
    result = {"service": str(unit), "backend": "cpu"}
    lifecycle.record_installation(
        result,
        [target],
        lifecycle.marketplace_entries([target]),
        tmp_path / "persistent/bin/python",
    )
    return lifecycle.load_state()


def test_guard_units_and_repeated_record(state):
    unit = Path(state["service"])
    path, timer, service = lifecycle.guard_paths(unit)
    assert "PathChanged=" + state["targets"][0]["primary"] in path.read_text()
    assert "OnUnitInactiveSec=30" in timer.read_text()
    assert '"marketplace-check"' in service.read_text()
    assert '"XDG_CONFIG_HOME=' in service.read_text()
    lifecycle.record_installation(state, state["targets"], state["marketplace"], state["python"])
    assert len(lifecycle.load_state()["marketplace"]) == 1
    assert len(lifecycle.load_state()["targets"]) == 1
    # Converting to a direct installation removes the marketplace lifecycle binding.
    lifecycle.record_installation(state, [], [], state["python"])
    assert all(not path.exists() for path in lifecycle.guard_paths(unit))
    assert not lifecycle.load_state()["marketplace"]


def test_claude_registry_watch_and_no_plugin_error(tmp_path):
    target = harnesses.targets(("claude",))[0]
    with pytest.raises(ValueError, match="installed plugin"):
        lifecycle.marketplace_entries([target])
    registry = Path(target["root"]) / "plugins/installed_plugins.json"
    harnesses.save_document(registry, {"plugins": {ID: [{"scope": "user"}]}})
    assert lifecycle.marketplace_entries([target])[0]["plugin"] == ID


def test_uninstall_cleans_recorded_and_discovered_profiles_and_preserves_data(
    state, monkeypatch, tmp_path
):
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: None)
    stored = Path(state["targets"][0]["primary"])
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "different-profile"))
    current = harnesses.targets(("codex",))[0]
    harnesses.save_document(current["primary"], {"mcp_servers": {"code-search-local": {}}})
    models = tmp_path / "storage/models/keep"
    models.parent.mkdir(parents=True)
    models.write_text("cached model")
    result = lifecycle.uninstall()
    assert result["data_preserved"] and models.read_text() == "cached model"
    assert harnesses.read_document(stored)["mcp_servers"] == {"other": {}}
    assert ID not in harnesses.read_document(stored).get("plugins", {})
    assert not harnesses.read_document(current["primary"]).get("mcp_servers", {})
    assert not lifecycle.state_path().exists()
    assert not Path(state["service"]).exists()
    assert not any(path.exists() for path in lifecycle.guard_paths(Path(state["service"])))
    assert lifecycle.uninstall()["data_preserved"]


def test_uninstall_errors_keep_record_for_retry(state, monkeypatch):
    original = harnesses.unregister
    monkeypatch.setattr(harnesses, "unregister", Mock(side_effect=ValueError("bad config")))
    with pytest.raises(RuntimeError, match="needs retry"):
        lifecycle.uninstall()
    assert not Path(state["service"]).exists()
    assert lifecycle.state_path().exists()
    assert all(path.exists() for path in lifecycle.guard_paths(Path(state["service"])))
    monkeypatch.setattr(harnesses, "unregister", original)
    lifecycle.uninstall(remove_plugins=False)
    assert not lifecycle.state_path().exists()


def test_marketplace_removal_cleans_only_recorded_profiles(state, monkeypatch):
    target = state["targets"][0]
    doc = harnesses.read_document(target["primary"])
    doc["plugins"].pop(ID)
    harnesses.save_document(target["primary"], doc)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(
        harnesses, "targets", Mock(side_effect=AssertionError("must not discover profiles"))
    )
    result = lifecycle.marketplace_check()
    assert "service_removed" in result
    assert harnesses.read_document(target["primary"])["mcp_servers"] == {"other": {}}
    assert not lifecycle.state_path().exists()


def test_disabling_plugin_leaves_service_installed(state):
    assert lifecycle.marketplace_check() == {"status": "installed"}
    assert Path(state["service"]).exists()


def test_transient_registry_write_keeps_service(state, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(harnesses, "plugins", Mock(side_effect=[[], [ID]]))
    assert lifecycle.marketplace_check() == {"status": "installed"}
    assert Path(state["service"]).exists()


@pytest.mark.parametrize(
    "responses", [[ValueError("incomplete JSON")], [[], OSError("read failed")]]
)
def test_registry_errors_retry(state, monkeypatch, responses):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(harnesses, "plugins", Mock(side_effect=responses))
    assert lifecycle.marketplace_check() == {"status": "retry"}
    assert Path(state["service"]).exists()


def test_guard_does_not_race_setup(state):
    lock = ServiceLock(lifecycle.state_path().parent, "install.lock")
    try:
        assert lifecycle.marketplace_check() == {"status": "busy"}
    finally:
        lock.close()


def test_guard_rejects_newline_watch_path(state):
    state["marketplace"][0]["target"]["primary"] = "/bad\npath"
    with pytest.raises(ValueError, match="line breaks"):
        lifecycle.install_guard(state)


def test_no_state_is_noop(monkeypatch):
    monkeypatch.setattr(install, "run", Mock())
    assert lifecycle.marketplace_check() == {"status": "installed"}
    lifecycle.uninstall(discover=False)
    atomic_json(lifecycle.state_path(), {})
    assert lifecycle.load_state() == {}


def test_new_marketplace_setup_drops_removed_owner_but_retains_unreadable_profile(
    state, monkeypatch
):
    replacement = harnesses.targets(("claude",))[0]
    entries = [{"target": replacement, "plugin": ID}]
    monkeypatch.setattr(harnesses, "plugins", Mock(side_effect=ValueError("partial write")))
    lifecycle.record_installation(state, [replacement], entries, state["python"])
    assert len(lifecycle.load_state()["marketplace"]) == 2
    monkeypatch.setattr(
        harnesses, "plugins", lambda target: [ID] if target["name"] == "claude" else []
    )
    lifecycle.record_installation(state, [replacement], entries, state["python"])
    assert lifecycle.load_state()["marketplace"] == entries
