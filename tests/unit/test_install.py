from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

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


def test_runtime_install_uses_bundled_lock_and_persistent_interpreter(tmp_path, monkeypatch):
    from importlib.metadata import distribution

    from code_search_local import install

    commands = []
    monkeypatch.setattr(install, "run", lambda args, **kwargs: commands.append(args))
    monkeypatch.setattr(install, "uv_executable", lambda: "/venv/bin/uv")
    settings = Settings(storage=str(tmp_path / "state"))
    wheel = tmp_path / "local.whl"
    wheel.touch()
    python = install_runtime(settings, "rocm", str(wheel))
    assert python.is_relative_to(settings.root / "runtimes")
    assert (python.parent.parent.parent / "uv.lock").exists()
    resources = distribution("code-search-local").locate_file("code_search_local/runtime")
    for name in ("pyproject.toml", "uv.lock"):
        assert (python.parent.parent.parent / name).read_bytes() == (resources / name).read_bytes()
    assert "--locked" in commands[0] and "--no-install-project" in commands[0]
    assert commands[0][-1] == "3.12"
    assert commands[1][-1] == str(wheel)


def test_codex_registration_preserves_settings_and_is_idempotent(tmp_path):
    import tomlkit

    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '# preserve me\nmodel = "custom"\n[mcp_servers.other]\nurl = "http://other"\n'
    )
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    register_clients(settings, "codex")
    first = config.read_text()
    register_clients(settings, "codex")
    assert config.read_text() == first
    document = tomlkit.parse(first)
    assert (
        document["model"] == "custom" and document["mcp_servers"]["other"]["url"] == "http://other"
    )
    assert document["mcp_servers"]["code-search-local"]["url"] == settings.url + "/mcp"
    assert first.startswith("# preserve me")
    assert config.stat().st_mode & 0o777 == 0o600


def test_claude_registration_uses_user_configuration(tmp_path):
    import json

    settings = Settings(storage=str(tmp_path / "state"))
    token = token_for(settings.root, create=True)
    register_clients(settings, "claude")
    config = tmp_path / "claude/.claude.json"
    entry = json.loads(config.read_text())["mcpServers"]["code-search-local"]
    assert entry == {
        "type": "http",
        "url": settings.url + "/mcp",
        "headers": {"Authorization": f"Bearer {token}"},
    }
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "backend,expected", [("cpu", "cpu"), ("rocm", "rocm"), ("cuda", "cuda"), ("mps", "cpu")]
)
def test_explicit_runtime_selection(backend, expected):
    assert select_runtime(backend) == expected


def test_automatic_runtime_selection(monkeypatch):
    from code_search_local import install

    monkeypatch.setattr(install.platform, "system", lambda: "Darwin")
    assert select_runtime("auto") == "cpu"
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install.shutil, "which", lambda _: True)
    monkeypatch.setattr(
        install.subprocess, "run", lambda *a, **k: NS(returncode=0, stdout="GPU 0: NVIDIA")
    )
    assert select_runtime("auto") == "cuda"
    monkeypatch.setattr(install.shutil, "which", lambda _: False)
    monkeypatch.setattr(install.Path, "glob", lambda *args: [])
    assert select_runtime("auto") == "cpu"


def test_setup_validates_before_replacing_service_and_registers(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client

    calls = []
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    python = tmp_path / "persistent" / "bin" / "python"
    monkeypatch.setattr(install, "install_runtime", lambda *a, **k: python)
    monkeypatch.setattr(install, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(
        install,
        "register_clients",
        lambda settings, client, **kwargs: calls.append(["register", client]),
    )
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    settings = Settings(storage=str(tmp_path / "state"), backend="cpu")
    result = setup(settings, client="both")
    assert result["backend"] == "cpu"
    assert calls[0][3] == "doctor"
    assert ["register", ("codex", "claude")] in calls
    unit = unit_path().read_text()
    assert str(python) in unit and "uvx" not in unit
    assert "UMask=0077" in unit and "WantedBy=default.target" in unit
    service_action("uninstall")
    assert not unit_path().exists()
    service_action("status")
    assert calls[-1] == ["systemctl", "--user", "status", "code-search-local.service"]
    monkeypatch.setattr(install.platform, "system", lambda: "Darwin")
    with pytest.raises(RuntimeError, match="Linux"):
        setup(settings, client="codex")


def test_safe_systemd_arguments_and_atomic_text(tmp_path):
    assert systemd_quote('a $b %h "x"') == '"a $$b %%h \\"x\\""'
    path = tmp_path / "config"
    atomic_text(path, "first")
    atomic_text(path, "second")
    assert path.read_text() == "second" and path.stat().st_mode & 0o777 == 0o600


def test_setup_and_service_cli_errors(monkeypatch):
    from code_search_local import install

    runner = CliRunner()
    monkeypatch.setattr(install, "setup", lambda *a, **k: {"backend": "cpu"})
    assert runner.invoke(main, ["setup", "--backend", "cpu", "--client", "codex"]).exit_code == 0

    def fail(*args, **kwargs):
        raise RuntimeError("failed setup")

    monkeypatch.setattr(install, "setup", fail)
    assert runner.invoke(main, ["setup", "--client", "codex"]).exit_code == 1
    monkeypatch.setattr(install, "service_action", lambda *a, **kwargs: None)
    for action in ("start", "stop", "restart", "status", "uninstall"):
        assert runner.invoke(main, ["service", action]).exit_code == 0

    def osfail(*args):
        raise OSError("systemd missing")

    monkeypatch.setattr(install, "service_action", osfail)
    assert runner.invoke(main, ["service", "start"]).exit_code == 1


def test_repeated_setup_reuses_running_service(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client

    commands = []
    python = tmp_path / "runtime" / "bin" / "python"
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install, "install_runtime", lambda *a, **k: python)
    monkeypatch.setattr(install, "run", lambda args, **kwargs: commands.append(args))
    registrations = []
    monkeypatch.setattr(
        install, "register_clients", lambda settings, client, **kwargs: registrations.append(client)
    )
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    settings = Settings(storage=str(tmp_path / "state"), backend="cpu")
    first = setup(settings, client="claude")
    count = len(commands)
    assert setup(settings, client="codex") == {**first, "agent_harness": ["codex"]}
    assert commands[count:] == [["systemctl", "--user", "daemon-reload"]]
    assert registrations == [("claude",), ("codex",)]


def test_failed_claude_registration_restores_previous_configuration(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from code_search_local import harnesses

    config = Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".claude.json"
    config.parent.mkdir()
    previous = '{"unrelated": true, "mcpServers": {"code-search-local": {"command": "old"}}}'
    config.write_text(previous)
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    save = harnesses.save_document

    def fail(path, doc, **kwargs):
        if "code-search-local" in doc.get("mcpServers", {}):
            raise OSError("full disk")
        save(path, doc, **kwargs)

    monkeypatch.setattr(harnesses, "save_document", fail)
    with pytest.raises(OSError, match="full disk"):
        register_clients(settings, "claude")
    assert config.read_text() == previous
    assert config.with_name(".claude.json.code-search-local.bak").read_text() == previous
    assert config.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("failures, expected", [({"cuda"}, "rocm"), ({"cuda", "rocm"}, "cpu")])
def test_auto_tries_available_backends_and_reuses_selected_runtime(
    tmp_path, monkeypatch, failures, expected
):
    import json
    import subprocess
    from pathlib import Path

    from code_search_local import install
    from code_search_local.client import Client

    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install, "select_runtime", lambda _: "cuda")
    vendor = tmp_path / "vendor"
    vendor.write_text("0x1002")
    monkeypatch.setattr(install.Path, "glob", lambda *a: [vendor])
    monkeypatch.setattr(
        install,
        "install_runtime",
        lambda settings, backend, source: tmp_path / backend / "bin/python",
    )
    monkeypatch.setattr(install, "register_clients", lambda *args, **kwargs: None)
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    validation = []

    def run(args, **kwargs):
        if "doctor" in args:
            config = json.loads(Path(args[-2]).read_text())
            validation.append(config["backend"])
            assert config["cpu_fallback"] is False
            if config["backend"] in failures:
                raise subprocess.CalledProcessError(1, ["doctor"])

    monkeypatch.setattr(install, "run", run)
    settings = Settings(storage=str(tmp_path / "state"))
    first = setup(settings, client="both")
    assert first["backend"] == expected
    sequence = ["cuda", "rocm"] + (["cpu"] if expected == "cpu" else [])
    assert validation == sequence
    assert str(tmp_path / expected / "bin/python") in unit_path().read_text()
    assert setup(settings, client="codex") == {**first, "agent_harness": ["codex"]}
    assert validation == sequence, "A second client must reuse the healthy selected runtime"


def test_failed_backend_validation_preserves_running_service_configuration(tmp_path, monkeypatch):
    import subprocess

    from code_search_local import install
    from code_search_local.config import config_path

    old = Settings(storage=str(tmp_path / "state"), backend="rocm")
    old.save()
    unit_path().parent.mkdir(parents=True)
    unit_path().write_text("existing unit")
    before = config_path().read_bytes()
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(install, "install_runtime", lambda *args: tmp_path / "new/bin/python")

    def fail(args, **kwargs):
        assert args[3] == "doctor"
        raise subprocess.CalledProcessError(1, ["doctor"])

    monkeypatch.setattr(install, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        setup(Settings(storage=old.storage, backend="cuda"), client="both")
    assert config_path().read_bytes() == before
    assert unit_path().read_text() == "existing unit"


@pytest.mark.parametrize("backend", ["cpu", "cuda", "rocm"])
def test_source_runtime_uses_declared_environment_and_editable_sync(tmp_path, monkeypatch, backend):
    import os
    from pathlib import Path

    from code_search_local import install
    from tests.helpers import copy_source_checkout

    source = copy_source_checkout(tmp_path / "source with spaces")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "/wrong/environment")
    monkeypatch.setenv("VIRTUAL_ENV", "/wrong/active")
    monkeypatch.setenv("PYTHONPATH", "/wrong/source")
    calls = []
    monkeypatch.setattr(install, "run", lambda args, **kw: calls.append((args, kw)))
    python = install.install_source_runtime(install.source_checkout(source), backend)
    assert python == source / ".venvs" / backend / "bin/python"
    args, kwargs = calls[0]
    assert args[1:4] == ["sync", "--project", source]
    assert "--locked" in args and "--reinstall-package" in args
    assert "--no-install-project" not in args and "--no-editable" not in args
    assert Path(kwargs["env"]["UV_PROJECT_ENVIRONMENT"]) == python.parent.parent
    assert "VIRTUAL_ENV" not in kwargs["env"] and "PYTHONPATH" not in kwargs["env"]
    assert os.environ["UV_PROJECT_ENVIRONMENT"] == "/wrong/environment"


def test_source_setup_points_service_at_checkout_and_restarts_after_edits(tmp_path, monkeypatch):
    from code_search_local import install
    from code_search_local.client import Client
    from tests.helpers import copy_source_checkout

    source = copy_source_checkout(tmp_path / "source with $dollars %specifiers")
    python = source / ".venvs/rocm/bin/python"
    calls = []
    installs = []
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        install,
        "install_source_runtime",
        lambda root, backend: installs.append((root, backend)) or python,
    )
    monkeypatch.setattr(install, "run", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(install, "register_clients", lambda *a, **kwargs: None)
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    settings = Settings(storage=str(tmp_path / "state"), backend="rocm")
    result = setup(settings, client="both", source=source)
    assert result["mode"] == "source" and result["source"] == str(source)
    assert result["runtime"] == str(python.parent.parent)
    unit = unit_path().read_text()
    assert f"ExecStart={systemd_quote(python)}" in unit
    assert f"WorkingDirectory={str(source).replace('%', '%%')}/" in unit
    assert calls[0][0][3] == "doctor" and calls[0][1]["cwd"] == source
    assert installs == [(source, "rocm")], "Sync each candidate once per setup"
    assert not (settings.root / "runtimes").exists()
    calls.clear()
    setup(settings, client="codex", source=source)
    assert any(args[:3] == ["systemctl", "--user", "restart"] for args, _ in calls)


def test_source_setup_rejects_non_checkouts_and_package_combination(tmp_path):
    from code_search_local import install

    settings = Settings(storage=str(tmp_path / "state"))
    with pytest.raises(ValueError, match="line breaks"):
        install.source_checkout(tmp_path / "bad\npath")
    with pytest.raises(ValueError, match="cannot be used"):
        setup(settings, client="codex", source=tmp_path, package_source="release.whl")
    for contents in (None, "invalid toml", '[project]\nname="another-project"\n'):
        if contents is not None:
            (tmp_path / "pyproject.toml").write_text(contents)
        with pytest.raises(ValueError, match="Not a Code Search Local source checkout"):
            install.source_checkout(tmp_path)
    wheel = tmp_path / "release.whl"
    wheel.touch()
    result = CliRunner().invoke(
        main,
        [
            "setup",
            "--client",
            "codex",
            "--source",
            str(tmp_path),
            "--package-source",
            str(wheel),
        ],
    )
    assert result.exit_code == 2 and "cannot be used" in result.output
    (tmp_path / "pyproject.toml").write_text('[project]\nname="code-search-local"\n')
    with pytest.raises(ValueError, match="Hatch rocm environment"):
        install.install_source_runtime(tmp_path, "rocm")
