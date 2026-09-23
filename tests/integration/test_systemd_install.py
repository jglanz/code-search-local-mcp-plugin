"""Opted-in Linux acceptance test; installs and removes one uniquely named user unit."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from code_search_local import __version__
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.install import uv_executable
from tests.helpers import free_port

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]

DRIVER = """
from pathlib import Path
import sys
from code_search_local import install
from code_search_local.cli import main
install.SERVICE = sys.argv[1]
install.unit_path = lambda: Path.home() / ".config/systemd/user" / install.SERVICE
main(args=sys.argv[2:], standalone_mode=False)
"""


def test_managed_backends_and_both_client_registrations(tmp_path):
    if os.environ.get("CODE_SEARCH_SYSTEMD_TESTS") != "1":
        pytest.skip(
            "Set CODE_SEARCH_SYSTEMD_TESTS=1 to exercise real user systemd and installed runtimes"
        )
    wheel = ROOT / "dist" / f"code_search_local-{__version__}-py3-none-any.whl"
    assert wheel.is_file(), "Build the current release wheel before running acceptance"
    service = "code-search-local-test-" + uuid.uuid4().hex[:12] + ".service"
    outside = tmp_path / "outside"
    outside.mkdir()
    storage = tmp_path / "state"
    config = tmp_path / "config"
    env = {
        **os.environ,
        "CODE_SEARCH_STORAGE": str(storage),
        "XDG_CONFIG_HOME": str(config),
        "CODEX_HOME": str(tmp_path / "codex"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "claude"),
        "PIPX_HOME": str(tmp_path / "pipx"),
        "PIPX_BIN_DIR": str(tmp_path / "bin"),
        "PIPX_MAN_DIR": str(tmp_path / "man"),
        "UV_CACHE_DIR": str(tmp_path / "disposable-cache"),
    }
    # The package wheel and model cache are local; downloads were independently validated in the cold-cache lane.
    source_cache = ROOT / ".test-artifacts/real-model/models"
    if source_cache.exists():
        shutil.copytree(source_cache, storage / "models", symlinks=True)
        for pointer in (storage / "models").glob("*.json"):
            data = json.loads(pointer.read_text())
            old = Path(data["snapshot"])
            data["snapshot"] = str(storage / "models" / old.relative_to(source_cache))
            pointer.write_text(json.dumps(data))
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    seed = os.environ.get("CODE_SEARCH_TEST_UV_CACHE")
    if seed:
        shutil.copytree(seed, tmp_path / "disposable-cache", symlinks=True, copy_function=os.link)
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex/config.toml").write_text('# keep this comment\nmodel = "custom"\n')
    (tmp_path / "claude").mkdir()
    (tmp_path / "claude/.claude.json").write_text('{"unrelatedSetting": "keep"}')

    def run(args, timeout=600):
        result = subprocess.run(
            [str(a) for a in args],
            cwd=outside,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        (tmp_path / "commands.log").open("a").write(
            json.dumps([str(a) for a in args]) + "\n" + result.stdout + "\n" + result.stderr + "\n"
        )
        assert result.returncode == 0, result.stdout[-4000:] + "\n" + result.stderr[-4000:]
        return result.stdout

    try:
        run([sys.executable, "-m", "pipx", "install", "--python", sys.executable, wheel])
        pipx_python = tmp_path / "pipx" / "venvs" / "code-search-local" / "bin" / "python"
        pip_venv = tmp_path / "pip-venv"
        run([sys.executable, "-m", "venv", pip_venv])
        pip_python = pip_venv / "bin/python"
        run([pip_python, "-m", "pip", "install", wheel])
        uvx_python = [uv_executable(), "tool", "run", "--from", wheel, "python"]
        port = free_port()
        common = [
            "setup",
            "--storage",
            storage,
            "--port",
            str(port),
            "--package-source",
            wheel,
            "--client",
            "both",
            "--no-cpu-fallback",
        ]
        client = Client(Settings(storage=str(storage), port=port))
        project = tmp_path / "fixture"
        project.mkdir()
        (project / "fixture.py").write_text('def persistent_symbol(): return "persistent"\n')
        for backend, origin in (
            ("cpu", [pipx_python]),
            ("cuda", [pip_python]),
            ("rocm", uvx_python),
        ):
            run([*origin, "-c", DRIVER, service, *common, "--backend", backend])
            job = asyncio.run(
                client.request(
                    "POST", "/api/v1/index", data={"directory_path": str(project), "wait": True}
                )
            )
            assert job["status"] == "succeeded"
            stats = asyncio.run(client.stats())
            assert stats["projects"][str(project)]["model"]["backend"] == backend
            assert run(["systemctl", "--user", "is-active", service]).strip() == "active"
            unit = run(["systemctl", "--user", "cat", service])
            assert str(storage / "runtimes") in unit
            assert str(tmp_path / "disposable-cache") not in unit
            # Both registered clients resolve to exactly this shared endpoint.
            import tomlkit

            codex = tomlkit.parse((tmp_path / "codex" / "config.toml").read_text())
            assert (
                codex["mcp_servers"]["code-search-local"]["url"] == f"http://127.0.0.1:{port}/mcp"
            )
            assert codex["model"] == "custom"
            assert (tmp_path / "codex/config.toml").read_text().startswith("# keep this comment")
            claude = json.loads((tmp_path / "claude/.claude.json").read_text())
            assert claude["unrelatedSetting"] == "keep"
            assert (
                claude["mcpServers"]["code-search-local"]["url"] == f"http://127.0.0.1:{port}/mcp"
            )
        before = run(["systemctl", "--user", "show", service, "--property=ExecStart"])
        run([pipx_python, "-c", DRIVER, service, *common, "--backend", "rocm"])
        assert run(["systemctl", "--user", "show", service, "--property=ExecStart"]) == before
        # Build a genuine next-version wheel and exercise the immutable runtime upgrade path.
        source = tmp_path / "upgrade-source"
        source.mkdir()
        for name in (
            "pyproject.toml",
            "uv.lock",
            "MANIFEST.in",
            "README.md",
            "LICENSE",
        ):
            shutil.copy2(ROOT / name, source / name)
        for name in ("src", "scripts", "plugins", ".claude-plugin"):
            shutil.copytree(
                ROOT / name,
                source / name,
                ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "runtime", "assets"),
            )
        metadata = source / "pyproject.toml"
        metadata.write_text(metadata.read_text().replace('version = "0.2.0"', 'version = "0.2.1"'))
        version = source / "src/code_search_local/__init__.py"
        version.write_text(version.read_text().replace("0.2.0", "0.2.1"))
        run([uv_executable(), "lock", "--project", source])
        run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--outdir",
                tmp_path / "upgrade-dist",
                source,
            ]
        )
        upgrade = next((tmp_path / "upgrade-dist").glob("*.whl"))
        run([pip_python, "-m", "pip", "install", "--upgrade", upgrade])
        upgraded = [upgrade if str(arg) == str(wheel) else arg for arg in common]
        run([pip_python, "-c", DRIVER, service, *upgraded, "--backend", "rocm"])
        assert "0.2.1-rocm" in run(["systemctl", "--user", "cat", service])
        hits = asyncio.run(
            client.request(
                "POST",
                "/api/v1/search",
                data={"project_path": str(project), "query": "persistent_symbol"},
            )
        )
        assert hits["results"][0]["name"] == "persistent_symbol"
        shutil.rmtree(tmp_path / "disposable-cache")
        run(["systemctl", "--user", "restart", service])
        assert run(["systemctl", "--user", "is-active", service]).strip() == "active"
        deadline = time.monotonic() + 30
        while True:
            try:
                asyncio.run(client.request("GET", "/api/v1/health"))
                break
            except OSError:
                assert time.monotonic() < deadline, "Service did not restart after cache deletion"
                time.sleep(0.2)
        hits = asyncio.run(
            client.request(
                "POST",
                "/api/v1/search",
                data={"project_path": str(project), "query": "persistent_symbol"},
            )
        )
        assert hits["results"][0]["name"] == "persistent_symbol"
        run([pip_python, "-c", DRIVER, service, "service", "uninstall"])
        assert storage.exists() and (storage / "models").exists()
    finally:
        subprocess.run(["systemctl", "--user", "disable", "--now", service], capture_output=True)
        (Path.home() / ".config/systemd/user" / service).unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
