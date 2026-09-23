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


def test_claude_registration_uses_native_user_scope(tmp_path, monkeypatch):
    from code_search_local import install

    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    calls = []
    monkeypatch.setattr(install.shutil, "which", lambda name: "/bin/claude")
    monkeypatch.setattr(install.subprocess, "run", lambda args, **kwargs: calls.append(args))
    register_clients(settings, "claude")
    assert calls[0][:4] == ["claude", "mcp", "remove", "code-search-local"]
    assert calls[1][2] == "add" and "user" in calls[1] and "http" in calls[1]
    monkeypatch.setattr(install.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="not installed"):
        register_clients(settings, "claude")


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
        install, "register_clients", lambda settings, client: calls.append(["register", client])
    )
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    settings = Settings(storage=str(tmp_path / "state"), backend="cpu")
    result = setup(settings, client="both")
    assert result["backend"] == "cpu"
    assert calls[0][3] == "doctor"
    assert calls[-1] == ["register", "both"]
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
    monkeypatch.setattr(install, "service_action", lambda *a: None)
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
        install, "register_clients", lambda settings, client: registrations.append(client)
    )
    monkeypatch.setattr(Client, "request", AsyncMock(return_value={"status": "ok"}))
    settings = Settings(storage=str(tmp_path / "state"), backend="cpu")
    first = setup(settings, client="claude")
    count = len(commands)
    assert setup(settings, client="codex") == first
    assert len(commands) == count
    assert registrations == ["claude", "codex"]


def test_failed_claude_registration_restores_previous_configuration(tmp_path, monkeypatch):
    import os
    import subprocess
    from pathlib import Path

    from code_search_local import install

    config = Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".claude.json"
    config.parent.mkdir()
    previous = '{"unrelated": true, "mcpServers": {"other": {"url": "http://other"}}}'
    config.write_text(previous)
    settings = Settings(storage=str(tmp_path / "state"))
    token_for(settings.root, create=True)
    monkeypatch.setattr(install.shutil, "which", lambda name: "/bin/claude")
    monkeypatch.setattr(install.subprocess, "run", lambda *a, **k: None)

    def fail(args, **kwargs):
        config.write_text("{}")
        raise subprocess.CalledProcessError(1, ["claude"])

    monkeypatch.setattr(install, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
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
    monkeypatch.setattr(install, "register_clients", lambda *args: None)
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
    assert setup(settings, client="codex") == first
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
