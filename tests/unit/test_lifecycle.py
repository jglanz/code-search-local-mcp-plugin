import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_search_local import constants, harnesses, install, lifecycle
from code_search_local.storage import ServiceLock, atomic_json
from tests import constants as test_constants

ID = "code-search-local@code-search-local"


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setattr(install, "run", Mock())
    target = harnesses.targets((constants.HARNESS_CODEX,))[0]
    harnesses.save_document(
        target[constants.KEY_PRIMARY],
        {
            constants.KEY_PLUGINS: {ID: {constants.KEY_ENABLED: False}},
            constants.KEY_MCP_SERVERS_LOWERCASE: {
                constants.APPLICATION_NAME: {constants.KEY_URL: "http://test"},
                test_constants.KEY_OTHER: {},
            },
        },
    )
    unit = install.unit_path()
    unit.parent.mkdir(parents=True)
    unit.write_text("test unit")
    result = {constants.KEY_SERVICE: str(unit), constants.KEY_BACKEND: constants.BACKEND_CPU}
    lifecycle.record_installation(
        result,
        [target],
        lifecycle.marketplace_entries([target]),
        tmp_path / test_constants.PATH_PERSISTENT_BIN_PYTHON,
    )
    return lifecycle.load_state()


def test_guard_units_and_repeated_record(state):
    unit = Path(state[constants.KEY_SERVICE])
    path, timer, service = lifecycle.guard_paths(unit)
    assert (
        constants.SYSTEMD_PATH_CHANGED_PREFIX
        + state[constants.KEY_TARGETS][0][constants.KEY_PRIMARY]
        in path.read_text()
    )
    assert "OnUnitInactiveSec=30" in timer.read_text()
    assert '"marketplace-check"' in service.read_text()
    assert '"XDG_CONFIG_HOME=' in service.read_text()
    lifecycle.record_installation(
        state,
        state[constants.KEY_TARGETS],
        state[constants.KEY_MARKETPLACE],
        state[constants.KEY_PYTHON],
    )
    assert len(lifecycle.load_state()[constants.KEY_MARKETPLACE]) == 1
    assert len(lifecycle.load_state()[constants.KEY_TARGETS]) == 1
    # Converting to a direct installation removes the marketplace lifecycle binding.
    lifecycle.record_installation(state, [], [], state[constants.KEY_PYTHON])
    assert all(not path.exists() for path in lifecycle.guard_paths(unit))
    assert not lifecycle.load_state()[constants.KEY_MARKETPLACE]


def test_claude_registry_watch_and_no_plugin_error(tmp_path):
    target = harnesses.targets((constants.HARNESS_CLAUDE,))[0]
    with pytest.raises(ValueError, match="installed plugin"):
        lifecycle.marketplace_entries([target])
    registry = Path(target[constants.KEY_ROOT]) / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON
    harnesses.save_document(
        registry, {constants.KEY_PLUGINS: {ID: [{constants.KEY_SCOPE: constants.USER_SCOPE}]}}
    )
    assert lifecycle.marketplace_entries([target])[0][constants.KEY_PLUGIN] == ID


def test_uninstall_cleans_recorded_and_discovered_profiles_and_preserves_data(
    state, monkeypatch, tmp_path
):
    monkeypatch.setattr(harnesses.shutil, "which", lambda _: None)
    stored = Path(state[constants.KEY_TARGETS][0][constants.KEY_PRIMARY])
    monkeypatch.setenv(
        constants.ENV_CODEX_HOME, str(tmp_path / test_constants.PATH_DIFFERENT_PROFILE)
    )
    current = harnesses.targets((constants.HARNESS_CODEX,))[0]
    harnesses.save_document(
        current[constants.KEY_PRIMARY],
        {constants.KEY_MCP_SERVERS_LOWERCASE: {constants.APPLICATION_NAME: {}}},
    )
    models = tmp_path / test_constants.PATH_STORAGE_MODELS_KEEP
    models.parent.mkdir(parents=True)
    models.write_text("cached model")
    result = lifecycle.uninstall()
    assert result[constants.KEY_DATA_PRESERVED] and models.read_text() == "cached model"
    assert harnesses.read_document(stored)[constants.KEY_MCP_SERVERS_LOWERCASE] == {
        test_constants.KEY_OTHER: {}
    }
    assert ID not in harnesses.read_document(stored).get(constants.KEY_PLUGINS, {})
    assert not harnesses.read_document(current[constants.KEY_PRIMARY]).get(
        constants.KEY_MCP_SERVERS_LOWERCASE, {}
    )
    assert not lifecycle.state_path().exists()
    assert not Path(state[constants.KEY_SERVICE]).exists()
    assert not any(
        path.exists() for path in lifecycle.guard_paths(Path(state[constants.KEY_SERVICE]))
    )
    assert lifecycle.uninstall()[constants.KEY_DATA_PRESERVED]


def test_uninstall_errors_keep_record_for_retry(state, monkeypatch):
    original = harnesses.unregister
    monkeypatch.setattr(harnesses, "unregister", Mock(side_effect=ValueError("bad config")))
    with pytest.raises(RuntimeError, match="needs retry"):
        lifecycle.uninstall()
    assert not Path(state[constants.KEY_SERVICE]).exists()
    assert lifecycle.state_path().exists()
    assert all(path.exists() for path in lifecycle.guard_paths(Path(state[constants.KEY_SERVICE])))
    monkeypatch.setattr(harnesses, "unregister", original)
    lifecycle.uninstall(remove_plugins=False)
    assert not lifecycle.state_path().exists()


def test_marketplace_removal_cleans_only_recorded_profiles(state, monkeypatch):
    target = state[constants.KEY_TARGETS][0]
    doc = harnesses.read_document(target[constants.KEY_PRIMARY])
    doc[constants.KEY_PLUGINS].pop(ID)
    harnesses.save_document(target[constants.KEY_PRIMARY], doc)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(
        harnesses,
        constants.KEY_TARGETS,
        Mock(side_effect=AssertionError("must not discover profiles")),
    )
    result = lifecycle.marketplace_check()
    assert constants.KEY_SERVICE_REMOVED in result
    assert harnesses.read_document(target[constants.KEY_PRIMARY])[
        constants.KEY_MCP_SERVERS_LOWERCASE
    ] == {test_constants.KEY_OTHER: {}}
    assert not lifecycle.state_path().exists()


def test_disabling_plugin_leaves_service_installed(state):
    assert lifecycle.marketplace_check() == {constants.KEY_STATUS: constants.STATUS_INSTALLED}
    assert Path(state[constants.KEY_SERVICE]).exists()


def test_transient_registry_write_keeps_service(state, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(harnesses, constants.KEY_PLUGINS, Mock(side_effect=[[], [ID]]))
    assert lifecycle.marketplace_check() == {constants.KEY_STATUS: constants.STATUS_INSTALLED}
    assert Path(state[constants.KEY_SERVICE]).exists()


@pytest.mark.parametrize(
    "responses", [[ValueError("incomplete JSON")], [[], OSError("read failed")]]
)
def test_registry_errors_retry(state, monkeypatch, responses):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(harnesses, constants.KEY_PLUGINS, Mock(side_effect=responses))
    assert lifecycle.marketplace_check() == {constants.KEY_STATUS: constants.STATUS_RETRY}
    assert Path(state[constants.KEY_SERVICE]).exists()


def test_guard_does_not_race_setup(state):
    lock = ServiceLock(lifecycle.state_path().parent, constants.PATH_INSTALL_LOCK)
    try:
        assert lifecycle.marketplace_check() == {constants.KEY_STATUS: constants.STATUS_BUSY}
    finally:
        lock.close()


def test_guard_rejects_newline_watch_path(state):
    state[constants.KEY_MARKETPLACE][0][constants.KEY_TARGET][constants.KEY_PRIMARY] = "/bad\npath"
    with pytest.raises(ValueError, match="line breaks"):
        lifecycle.install_guard(state)


def test_no_state_is_noop(monkeypatch):
    monkeypatch.setattr(install, "run", Mock())
    assert lifecycle.marketplace_check() == {constants.KEY_STATUS: constants.STATUS_INSTALLED}
    lifecycle.uninstall(discover=False)
    atomic_json(lifecycle.state_path(), {})
    assert lifecycle.load_state() == {}


def test_new_marketplace_setup_drops_removed_owner_but_retains_unreadable_profile(
    state, monkeypatch
):
    replacement = harnesses.targets((constants.HARNESS_CLAUDE,))[0]
    entries = [{constants.KEY_TARGET: replacement, constants.KEY_PLUGIN: ID}]
    monkeypatch.setattr(
        harnesses, constants.KEY_PLUGINS, Mock(side_effect=ValueError("partial write"))
    )
    lifecycle.record_installation(state, [replacement], entries, state[constants.KEY_PYTHON])
    assert len(lifecycle.load_state()[constants.KEY_MARKETPLACE]) == 2
    monkeypatch.setattr(
        harnesses,
        constants.KEY_PLUGINS,
        lambda target: [ID] if target[constants.KEY_NAME] == constants.HARNESS_CLAUDE else [],
    )
    lifecycle.record_installation(state, [replacement], entries, state[constants.KEY_PYTHON])
    assert lifecycle.load_state()[constants.KEY_MARKETPLACE] == entries
