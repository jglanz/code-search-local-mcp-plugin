from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from code_search_local import constants
from code_search_local.cli import main
from code_search_local.config import Settings
from code_search_local.install import (
    atomic_text,
    install_runtime,
    register_clients,
    select_runtime,
    service_action,
    setup,
    systemd_quote,
    unit_path,
)
from code_search_local.service import token_for
from tests import constants as test_constants


def test_runtime_install_uses_bundled_lock_and_persistent_interpreter(tmp_path, monkeypatch):
    from importlib.metadata import distribution

    from code_search_local import install

    commands = []
    monkeypatch.setattr(install, "run", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(install, "uv_executable", lambda: "/venv/bin/uv")
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    wheel = tmp_path / test_constants.PATH_LOCAL_WHL
    wheel.touch()
    python = install_runtime(settings, constants.BACKEND_ROCM, str(wheel))
    assert python.is_relative_to(settings.root / constants.RUNTIMES_DIRECTORY)
    assert (python.parent.parent.parent / constants.PATH_UV_LOCK).exists()
    resources = distribution(constants.APPLICATION_NAME).locate_file(
        constants.PATH_CODE_SEARCH_LOCAL_RUNTIME
    )
    for name in (constants.PATH_PYPROJECT_TOML, constants.PATH_UV_LOCK):
        assert (python.parent.parent.parent / name).read_bytes() == (resources / name).read_bytes()
    assert (
        constants.OPTION_LOCKED in commands[0]
        and constants.OPTION_NO_INSTALL_PROJECT in commands[0]
    )
    assert commands[0][-1] == constants.RUNTIME_PYTHON_VERSION
    assert commands[1][-1] == str(wheel)


def test_codex_registration_preserves_settings_and_is_idempotent(tmp_path):
    import tomlkit

    config = tmp_path / constants.HARNESS_CODEX / constants.PATH_CONFIG_TOML
    config.parent.mkdir()
    config.write_text(
        '# preserve me\nmodel = "custom"\n[mcp_servers.other]\nurl = "http://other"\n'
    )
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token_for(settings.root, create=True)
    register_clients(settings, constants.HARNESS_CODEX)
    first = config.read_text()
    register_clients(settings, constants.HARNESS_CODEX)
    assert config.read_text() == first
    document = tomlkit.parse(first)
    assert (
        document[constants.KEY_MODEL] == test_constants.VALUE_CUSTOM
        and document[constants.KEY_MCP_SERVERS_LOWERCASE][test_constants.KEY_OTHER][
            constants.KEY_URL
        ]
        == "http://other"
    )
    assert (
        document[constants.KEY_MCP_SERVERS_LOWERCASE][constants.APPLICATION_NAME][constants.KEY_URL]
        == settings.url + constants.MCP_ENDPOINT
    )
    assert first.startswith("# preserve me")
    assert config.stat().st_mode & 0o777 == 0o600


def test_claude_registration_uses_user_configuration(tmp_path):
    import json

    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token = token_for(settings.root, create=True)
    register_clients(settings, constants.HARNESS_CLAUDE)
    config = tmp_path / test_constants.PATH_CLAUDE_CLAUDE_JSON
    entry = json.loads(config.read_text())[constants.KEY_MCP_SERVERS][constants.APPLICATION_NAME]
    assert entry == {
        constants.KEY_TYPE: constants.TRANSPORT_HTTP,
        constants.KEY_URL: settings.url + constants.MCP_ENDPOINT,
        constants.KEY_HEADERS: {constants.KEY_AUTHORIZATION: f"Bearer {token}"},
    }
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "backend,expected",
    [
        (constants.BACKEND_CPU, constants.BACKEND_CPU),
        (constants.BACKEND_ROCM, constants.BACKEND_ROCM),
        (constants.BACKEND_CUDA, constants.BACKEND_CUDA),
        (constants.BACKEND_MPS, constants.BACKEND_CPU),
    ],
)
def test_explicit_runtime_selection(backend, expected):
    assert select_runtime(backend) == expected


def test_automatic_runtime_selection(monkeypatch):
    from code_search_local import install

    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_MACOS)
    assert select_runtime(constants.BACKEND_AUTO) == constants.BACKEND_CPU
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    monkeypatch.setattr(install.shutil, "which", lambda _: True)
    monkeypatch.setattr(
        install.subprocess, "run", lambda *a, **k: NS(returncode=0, stdout="GPU 0: NVIDIA")
    )
    assert select_runtime(constants.BACKEND_AUTO) == constants.BACKEND_CUDA
    monkeypatch.setattr(install.shutil, "which", lambda _: False)
    monkeypatch.setattr(install.Path, "glob", lambda *args: [])
    assert select_runtime(constants.BACKEND_AUTO) == constants.BACKEND_CPU


def test_setup_validates_before_replacing_service_and_registers(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client

    calls = []
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    python = (
        tmp_path / test_constants.PATH_PERSISTENT / constants.BIN_DIRECTORY / constants.KEY_PYTHON
    )
    monkeypatch.setattr(install, "install_runtime", lambda *a, **k: python)
    monkeypatch.setattr(install, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(
        install,
        "register_clients",
        lambda settings, client, **kwargs: calls.append(["register", client]),
    )
    monkeypatch.setattr(
        Client, "request", AsyncMock(return_value={constants.KEY_STATUS: constants.STATUS_OK})
    )
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), backend=constants.BACKEND_CPU
    )
    result = setup(settings, client=constants.LEGACY_HARNESS_BOTH)
    assert result[constants.KEY_BACKEND] == constants.BACKEND_CPU
    assert calls[0][3] == constants.COMMAND_DOCTOR
    assert ["register", (constants.HARNESS_CODEX, constants.HARNESS_CLAUDE)] in calls
    unit = unit_path().read_text()
    assert str(python) in unit and test_constants.VALUE_UVX not in unit
    assert "UMask=0077" in unit and "WantedBy=default.target" in unit
    service_action(constants.COMMAND_UNINSTALL)
    assert not unit_path().exists()
    service_action(constants.KEY_STATUS)
    assert calls[-1] == [
        constants.COMMAND_SYSTEMCTL,
        constants.OPTION_USER,
        constants.KEY_STATUS,
        "code-search-local.service",
    ]
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_MACOS)
    with pytest.raises(RuntimeError, match=constants.PLATFORM_LINUX):
        setup(settings, client=constants.HARNESS_CODEX)


def test_safe_systemd_arguments_and_atomic_text(tmp_path):
    assert systemd_quote('a $b %h "x"') == '"a $$b %%h \\"x\\""'
    path = tmp_path / test_constants.PATH_CONFIG
    atomic_text(path, "first")
    atomic_text(path, "second")
    assert path.read_text() == test_constants.VALUE_SECOND and path.stat().st_mode & 0o777 == 0o600


def test_setup_and_service_cli_errors(monkeypatch):
    from code_search_local import install

    runner = CliRunner()
    monkeypatch.setattr(
        install, "setup", lambda *a, **k: {constants.KEY_BACKEND: constants.BACKEND_CPU}
    )
    assert (
        runner.invoke(
            main,
            [
                "setup",
                constants.OPTION_BACKEND,
                constants.BACKEND_CPU,
                constants.OPTION_CLIENT,
                constants.HARNESS_CODEX,
            ],
        ).exit_code
        == 0
    )

    def fail(*args, **kwargs):
        raise RuntimeError("failed setup")

    monkeypatch.setattr(install, "setup", fail)
    assert (
        runner.invoke(main, ["setup", constants.OPTION_CLIENT, constants.HARNESS_CODEX]).exit_code
        == 1
    )
    monkeypatch.setattr(install, "service_action", lambda *a, **kwargs: None)
    for action in (
        constants.COMMAND_START,
        constants.COMMAND_STOP,
        constants.COMMAND_RESTART,
        constants.KEY_STATUS,
        constants.COMMAND_UNINSTALL,
    ):
        assert runner.invoke(main, [constants.KEY_SERVICE, action]).exit_code == 0

    def osfail(*args):
        raise OSError("systemd missing")

    monkeypatch.setattr(install, "service_action", osfail)
    assert runner.invoke(main, [constants.KEY_SERVICE, constants.COMMAND_START]).exit_code == 1


def test_repeated_setup_reuses_running_service(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client

    commands = []
    python = tmp_path / constants.KEY_RUNTIME / constants.BIN_DIRECTORY / constants.KEY_PYTHON
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    monkeypatch.setattr(install, "install_runtime", lambda *a, **k: python)
    monkeypatch.setattr(install, "run", lambda args, **kwargs: commands.append(args))
    registrations = []
    monkeypatch.setattr(
        install, "register_clients", lambda settings, client, **kwargs: registrations.append(client)
    )
    monkeypatch.setattr(
        Client, "request", AsyncMock(return_value={constants.KEY_STATUS: constants.STATUS_OK})
    )
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), backend=constants.BACKEND_CPU
    )
    first = setup(settings, client=constants.HARNESS_CLAUDE)
    count = len(commands)
    second = setup(settings, client=constants.HARNESS_CODEX)
    assert second == {
        **first,
        constants.KEY_AGENT_HARNESS: [constants.HARNESS_CODEX],
        constants.KEY_HARNESS_CONFIGS: second[constants.KEY_HARNESS_CONFIGS],
    }
    assert set(second[constants.KEY_HARNESS_CONFIGS]) == {constants.HARNESS_CODEX}
    assert commands[count:] == [
        [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD]
    ]
    assert registrations == [(constants.HARNESS_CLAUDE,), (constants.HARNESS_CODEX,)]


def test_failed_claude_registration_restores_previous_configuration(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from code_search_local import harnesses

    config = Path(os.environ[constants.ENV_CLAUDE_CONFIG_DIR]) / constants.PATH_CLAUDE_JSON
    config.parent.mkdir()
    previous = '{"unrelated": true, "mcpServers": {"code-search-local": {"command": "old"}}}'
    config.write_text(previous)
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    token_for(settings.root, create=True)
    save = harnesses.save_document

    def fail(path, doc, **kwargs):
        if constants.APPLICATION_NAME in doc.get(constants.KEY_MCP_SERVERS, {}):
            raise OSError("full disk")
        save(path, doc, **kwargs)

    monkeypatch.setattr(harnesses, "save_document", fail)
    with pytest.raises(OSError, match="full disk"):
        register_clients(settings, constants.HARNESS_CLAUDE)
    assert config.read_text() == previous
    assert (
        config.with_name(test_constants.PATH_CLAUDE_JSON_CODE_SEARCH_LOCAL_BAK).read_text()
        == previous
    )
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "failures, expected",
    [
        ({constants.BACKEND_CUDA}, constants.BACKEND_ROCM),
        ({constants.BACKEND_CUDA, constants.BACKEND_ROCM}, constants.BACKEND_CPU),
    ],
)
def test_auto_tries_available_backends_and_reuses_selected_runtime(
    tmp_path, monkeypatch, failures, expected
):
    import json
    import subprocess
    from pathlib import Path

    from code_search_local import install
    from code_search_local.client import Client

    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    monkeypatch.setattr(install, "select_runtime", lambda _: constants.BACKEND_CUDA)
    vendor = tmp_path / test_constants.PATH_VENDOR
    vendor.write_text(constants.AMD_PCI_VENDOR_ID)
    monkeypatch.setattr(install.Path, "glob", lambda *a: [vendor])
    monkeypatch.setattr(
        install,
        "install_runtime",
        lambda settings, backend, source: tmp_path / backend / constants.PATH_BIN_PYTHON,
    )
    monkeypatch.setattr(install, "register_clients", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        Client, "request", AsyncMock(return_value={constants.KEY_STATUS: constants.STATUS_OK})
    )
    validation = []

    def run(args, **kwargs):
        if constants.COMMAND_DOCTOR in args:
            config = json.loads(Path(args[-2]).read_text())
            validation.append(config[constants.KEY_BACKEND])
            assert config[constants.KEY_CPU_FALLBACK] is False
            if config[constants.KEY_BACKEND] in failures:
                raise subprocess.CalledProcessError(1, [constants.COMMAND_DOCTOR])

    monkeypatch.setattr(install, "run", run)
    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    first = setup(settings, client=constants.LEGACY_HARNESS_BOTH)
    assert first[constants.KEY_BACKEND] == expected
    sequence = [constants.BACKEND_CUDA, constants.BACKEND_ROCM] + (
        [constants.BACKEND_CPU] if expected == constants.BACKEND_CPU else []
    )
    assert validation == sequence
    assert str(tmp_path / expected / constants.PATH_BIN_PYTHON) in unit_path().read_text()
    second = setup(settings, client=constants.HARNESS_CODEX)
    assert second == {
        **first,
        constants.KEY_AGENT_HARNESS: [constants.HARNESS_CODEX],
        constants.KEY_HARNESS_CONFIGS: second[constants.KEY_HARNESS_CONFIGS],
    }
    assert set(second[constants.KEY_HARNESS_CONFIGS]) == {constants.HARNESS_CODEX}
    assert validation == sequence, "A second client must reuse the healthy selected runtime"


def test_failed_backend_validation_preserves_running_service_configuration(tmp_path, monkeypatch):
    import subprocess

    from code_search_local import install
    from code_search_local.config import config_path

    old = Settings(storage=str(tmp_path / test_constants.KEY_STATE), backend=constants.BACKEND_ROCM)
    old.save()
    unit_path().parent.mkdir(parents=True)
    unit_path().write_text("existing unit")
    before = config_path().read_bytes()
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    monkeypatch.setattr(
        install, "install_runtime", lambda *args: tmp_path / test_constants.PATH_NEW_BIN_PYTHON
    )

    def fail(args, **kwargs):
        assert args[3] == constants.COMMAND_DOCTOR
        raise subprocess.CalledProcessError(1, [constants.COMMAND_DOCTOR])

    monkeypatch.setattr(install, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        setup(
            Settings(storage=old.storage, backend=constants.BACKEND_CUDA),
            client=constants.LEGACY_HARNESS_BOTH,
        )
    assert config_path().read_bytes() == before
    assert unit_path().read_text() == "existing unit"


@pytest.mark.parametrize(
    constants.KEY_BACKEND, [constants.BACKEND_CPU, constants.BACKEND_CUDA, constants.BACKEND_ROCM]
)
def test_source_runtime_uses_declared_environment_and_editable_sync(tmp_path, monkeypatch, backend):
    import os
    from pathlib import Path

    from code_search_local import install
    from tests.helpers import copy_source_checkout

    source = copy_source_checkout(tmp_path / test_constants.PATH_SOURCE_WITH_SPACES)
    monkeypatch.setenv(constants.ENV_UV_PROJECT_ENVIRONMENT, "/wrong/environment")
    monkeypatch.setenv(constants.ENV_VIRTUAL_ENV, "/wrong/active")
    monkeypatch.setenv(constants.ENV_PYTHONPATH, "/wrong/source")
    calls = []
    monkeypatch.setattr(install, "run", lambda args, **kw: calls.append((args, kw)))
    python = install.install_source_runtime(install.source_checkout(source), backend)
    assert (
        python == source / test_constants.PATH_VENVS_LOWERCASE / backend / constants.PATH_BIN_PYTHON
    )
    args, kwargs = calls[0]
    assert args[1:4] == [constants.COMMAND_SYNC, constants.OPTION_PROJECT, source]
    assert constants.OPTION_LOCKED in args and constants.OPTION_REINSTALL_PACKAGE in args
    assert (
        constants.OPTION_NO_INSTALL_PROJECT not in args
        and test_constants.OPTION_NO_EDITABLE not in args
    )
    assert (
        Path(kwargs[constants.KEY_ENV][constants.ENV_UV_PROJECT_ENVIRONMENT])
        == python.parent.parent
    )
    assert (
        constants.ENV_VIRTUAL_ENV not in kwargs[constants.KEY_ENV]
        and constants.ENV_PYTHONPATH not in kwargs[constants.KEY_ENV]
    )
    assert os.environ[constants.ENV_UV_PROJECT_ENVIRONMENT] == "/wrong/environment"


def test_source_setup_points_service_at_checkout_and_restarts_after_edits(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client
    from tests.helpers import copy_source_checkout

    source = copy_source_checkout(tmp_path / test_constants.PATH_SOURCE_WITH_DOLLARS_SPECIFIERS)
    python = source / test_constants.PATH_VENVS_ROCM_BIN_PYTHON
    calls = []
    installs = []
    monkeypatch.setattr(install.platform, "system", lambda: constants.PLATFORM_LINUX)
    monkeypatch.setattr(
        install,
        "install_source_runtime",
        lambda root, backend: installs.append((root, backend)) or python,
    )
    monkeypatch.setattr(install, "run", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(install, "register_clients", lambda *a, **kwargs: None)
    monkeypatch.setattr(
        Client, "request", AsyncMock(return_value={constants.KEY_STATUS: constants.STATUS_OK})
    )
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE), backend=constants.BACKEND_ROCM
    )
    result = setup(settings, client=constants.LEGACY_HARNESS_BOTH, source=source)
    assert result[constants.KEY_MODE] == constants.KEY_SOURCE and result[
        constants.KEY_SOURCE
    ] == str(source)
    assert result[constants.KEY_RUNTIME] == str(python.parent.parent)
    unit = unit_path().read_text()
    assert f"ExecStart={systemd_quote(python)}" in unit
    assert f"WorkingDirectory={str(source).replace('%', '%%')}/" in unit
    assert calls[0][0][3] == constants.COMMAND_DOCTOR and calls[0][1][constants.KEY_CWD] == source
    assert installs == [(source, constants.BACKEND_ROCM)], "Sync each candidate once per setup"
    assert not (settings.root / constants.RUNTIMES_DIRECTORY).exists()
    calls.clear()
    setup(settings, client=constants.HARNESS_CODEX, source=source)
    systemd = [args for args, _ in calls if args[0] == constants.COMMAND_SYSTEMCTL]
    assert systemd.index(
        [
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_STOP,
            install.SERVICE,
        ]
    ) < systemd.index(
        [
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_START,
            install.SERVICE,
        ]
    )


def test_source_setup_rejects_non_checkouts_and_package_combination(tmp_path):
    from code_search_local import install

    settings = Settings(storage=str(tmp_path / test_constants.KEY_STATE))
    with pytest.raises(ValueError, match="line breaks"):
        install.source_checkout(tmp_path / test_constants.PATH_BAD_PATH)
    with pytest.raises(ValueError, match="cannot be used"):
        setup(
            settings, client=constants.HARNESS_CODEX, source=tmp_path, package_source="release.whl"
        )
    for contents in (None, "invalid toml", '[project]\nname="another-project"\n'):
        if contents is not None:
            (tmp_path / constants.PATH_PYPROJECT_TOML).write_text(contents)
        with pytest.raises(ValueError, match="Not a Code Search Local source checkout"):
            install.source_checkout(tmp_path)
    wheel = tmp_path / test_constants.PATH_RELEASE_WHL
    wheel.touch()
    result = CliRunner().invoke(
        main,
        [
            "setup",
            constants.OPTION_CLIENT,
            constants.HARNESS_CODEX,
            constants.OPTION_SOURCE,
            str(tmp_path),
            constants.OPTION_PACKAGE_SOURCE,
            str(wheel),
        ],
    )
    assert result.exit_code == 2 and "cannot be used" in result.output
    (tmp_path / constants.PATH_PYPROJECT_TOML).write_text('[project]\nname="code-search-local"\n')
    with pytest.raises(ValueError, match="Hatch rocm environment"):
        install.install_source_runtime(tmp_path, constants.BACKEND_ROCM)


@pytest.fixture
def startup_clock(monkeypatch):
    from code_search_local import install

    clock = NS(now=0.0)
    monkeypatch.setattr(install.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(
        install.time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds)
    )
    monkeypatch.setattr(
        install,
        "service_state",
        lambda: {
            constants.KEY_ACTIVE_STATE: "active",
            constants.KEY_SUB_STATE: constants.STATUS_RUNNING,
        },
    )
    return clock


def test_source_reconfiguration_waits_for_slow_start_and_registers_all_harnesses(
    tmp_path, monkeypatch, startup_clock
):
    import json
    from dataclasses import replace
    from pathlib import Path

    from code_search_local import harnesses, install, lifecycle
    from code_search_local.config import config_path
    from tests.helpers import copy_source_checkout

    source = copy_source_checkout(tmp_path / constants.KEY_SOURCE)
    python = source / test_constants.PATH_VENVS_ROCM_BIN_PYTHON
    monkeypatch.setattr(install, "install_source_runtime", lambda *a: python)
    calls = []
    ready_at = 0
    old = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE),
        backend=constants.BACKEND_ROCM,
        cpu_fallback=False,
    )

    def probe(settings, timeout=test_constants.EVENT_WAIT_TIMEOUT_SECONDS):
        if startup_clock.now < ready_at:
            raise OSError("restoring indexes")
        return {constants.KEY_STATUS: constants.STATUS_OK}

    def run(args, **kwargs):
        calls.append(args)
        if args[:3] == [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_STOP]:
            assert Settings.load().cpu_fallback is False
            assert unit_path().read_text() == "previous unit\n"
        if (
            args[:3]
            == [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_START]
            and ready_at
        ):
            assert json.loads(config_path().read_text())[constants.KEY_CPU_FALLBACK] is True
            assert str(python) in unit_path().read_text()

    monkeypatch.setattr(install, "run", run)
    monkeypatch.setattr(install, "probe_service", probe)
    setup(old, source=source, agent_harness=(constants.HARNESS_CLAUDE,))
    assert not Path(
        harnesses.targets((constants.HARNESS_CODEX,))[0][constants.KEY_PRIMARY]
    ).exists()
    assert not Path(
        harnesses.targets((constants.HARNESS_OPENCODE,))[0][constants.KEY_PRIMARY]
    ).exists()
    unit_path().write_text("previous unit\n")
    # Existing Codex entries must be updated, while OpenCode needs a new entry.
    codex = harnesses.targets((constants.HARNESS_CODEX,))[0]
    harnesses.save_document(
        codex[constants.KEY_PRIMARY],
        {
            constants.KEY_MCP_SERVERS_LOWERCASE: {
                constants.APPLICATION_NAME: {test_constants.KEY_COMMAND: "obsolete"},
                test_constants.KEY_OTHER: {test_constants.KEY_COMMAND: "keep"},
            }
        },
    )
    calls.clear()
    ready_at = 123
    result = setup(
        replace(old, cpu_fallback=True), source=source, agent_harness=(constants.HARNESS_ALL,)
    )
    assert startup_clock.now == 123
    assert (
        calls.index(
            [
                constants.COMMAND_SYSTEMCTL,
                constants.OPTION_USER,
                constants.COMMAND_STOP,
                install.SERVICE,
            ]
        )
        < calls.index(
            [constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD]
        )
        < calls.index(
            [
                constants.COMMAND_SYSTEMCTL,
                constants.OPTION_USER,
                constants.COMMAND_START,
                install.SERVICE,
            ]
        )
    )
    for target, key in zip(
        harnesses.targets(),
        (constants.KEY_MCP_SERVERS_LOWERCASE, constants.KEY_MCP_SERVERS, constants.KEY_MCP),
    ):
        entry = harnesses.read_document(target[constants.KEY_PRIMARY])[key][
            constants.APPLICATION_NAME
        ]
        assert entry[constants.KEY_URL] == old.url + constants.MCP_ENDPOINT
        assert test_constants.KEY_COMMAND not in entry
        assert (
            result[constants.KEY_HARNESS_CONFIGS][target[constants.KEY_NAME]]
            == target[constants.KEY_PRIMARY]
        )
    assert harnesses.read_document(codex[constants.KEY_PRIMARY])[
        constants.KEY_MCP_SERVERS_LOWERCASE
    ][test_constants.KEY_OTHER] == {test_constants.KEY_COMMAND: "keep"}
    assert {t[constants.KEY_NAME] for t in lifecycle.load_state()[constants.KEY_TARGETS]} == set(
        harnesses.HARNESSES
    )


@pytest.mark.parametrize(
    "state",
    [
        {
            constants.KEY_ACTIVE_STATE: constants.STATUS_FAILED,
            constants.KEY_SUB_STATE: constants.STATUS_FAILED,
            constants.KEY_EXEC_MAIN_STATUS: constants.ENV_ENABLED,
        },
        {
            constants.KEY_ACTIVE_STATE: constants.STATUS_INACTIVE,
            constants.KEY_SUB_STATE: "dead",
            constants.KEY_EXEC_MAIN_STATUS: constants.ENV_DISABLED,
        },
        {
            constants.KEY_ACTIVE_STATE: "activating",
            constants.KEY_SUB_STATE: constants.STATUS_AUTO_RESTART,
            constants.KEY_EXEC_MAIN_STATUS: constants.ENV_ENABLED,
        },
    ],
)
def test_startup_failure_reports_journal_without_waiting_full_timeout(
    monkeypatch, startup_clock, state
):
    from code_search_local import install

    monkeypatch.setattr(
        install,
        "probe_service",
        lambda *a, **k: (_ for _ in ()).throw(OSError("connection refused")),
    )
    monkeypatch.setattr(install, "service_state", lambda: state)
    monkeypatch.setattr(
        install, "run", lambda *a, **k: NS(stdout="RuntimeError: startup fixture failed\n")
    )
    with pytest.raises(RuntimeError, match="startup fixture failed") as error:
        install.wait_for_service(Settings())
    assert "Harness registrations were not updated" in str(error.value)
    assert startup_clock.now == 0


def test_startup_timeout_is_bounded_and_includes_diagnostics(monkeypatch, startup_clock, capsys):
    from code_search_local import install

    timeouts = []

    def probe(settings, timeout=test_constants.EVENT_WAIT_TIMEOUT_SECONDS):
        timeouts.append(timeout)
        raise TimeoutError("unresponsive health endpoint")

    monkeypatch.setattr(install, "probe_service", probe)
    monkeypatch.setattr(install, "run", lambda *a, **k: NS(stdout="still starting\n"))
    with pytest.raises(RuntimeError, match="within 2s") as error:
        install.wait_for_service(Settings(), timeout=test_constants.SHORT_STARTUP_BUDGET_SECONDS)
    assert startup_clock.now == 2
    assert timeouts == [2, 1.5, 1, 0.5]
    assert constants.OPTION_STARTUP_TIMEOUT in str(error.value)
    assert "unresponsive health endpoint" in str(error.value)
    assert "Waiting for" in capsys.readouterr().err


def test_hung_health_request_has_a_per_probe_deadline(monkeypatch):
    import asyncio

    from code_search_local import install
    from code_search_local.client import Client

    cancelled = []

    async def request(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(Client, "request", request)
    with pytest.raises(TimeoutError):
        install.probe_service(Settings(), timeout=test_constants.SHORT_HEALTH_PROBE_TIMEOUT_SECONDS)
    assert cancelled == [True]


def test_setup_startup_timeout_is_an_installer_option(monkeypatch):
    from unittest.mock import Mock

    from code_search_local import install

    mocked = Mock(return_value={})
    monkeypatch.setattr(install, "setup", mocked)
    runner = CliRunner()
    assert runner.invoke(main, ["setup", constants.OPTION_STARTUP_TIMEOUT, "600"]).exit_code == 0
    assert mocked.call_args.kwargs[test_constants.KEY_STARTUP_TIMEOUT] == 600
    assert (
        runner.invoke(
            main, ["setup", constants.OPTION_STARTUP_TIMEOUT, constants.ENV_DISABLED]
        ).exit_code
        == 2
    )
