"""Run a real user service directly from a raw checkout with all backend venvs present."""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from code_search_local.client import Client
from code_search_local.config import Settings
from tests.helpers import SYSTEMD_DRIVER, copy_source_checkout, free_port

pytestmark = pytest.mark.packaging
ROOT = Path(__file__).resolve().parents[2]


def test_source_service_keeps_backends_and_picks_up_edits(tmp_path):
    if os.environ.get("CODE_SEARCH_SYSTEMD_TESTS") != "1":
        pytest.skip("Set CODE_SEARCH_SYSTEMD_TESTS=1 for source-service acceptance")
    source = copy_source_checkout(tmp_path / "live checkout with spaces")
    service = "code-search-local-source-test-" + uuid.uuid4().hex[:12] + ".service"
    storage = tmp_path / "state"
    storage.mkdir()
    cache = Path(os.environ.get("CODE_SEARCH_MODEL_STORAGE", ROOT / ".test-artifacts/real-model"))
    if (cache / "models").exists():
        (storage / "models").symlink_to((cache / "models").resolve(), target_is_directory=True)
    env = {
        **os.environ,
        "CODE_SEARCH_STORAGE": str(storage),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "CODEX_HOME": str(tmp_path / "codex"),
        "CLAUDE_CONFIG_DIR": str(tmp_path / "claude"),
    }
    for name in ("VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT"):
        env.pop(name, None)
    settings = Settings(storage=str(storage), port=free_port())
    client = Client(settings)

    def run(args):
        result = subprocess.run(
            [str(arg) for arg in args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        with (tmp_path / "commands.log").open("a") as log:
            log.write(result.stdout + "\n" + result.stderr + "\n")
        assert result.returncode == 0, result.stdout[-4000:] + "\n" + result.stderr[-4000:]
        return result.stdout

    def health():
        deadline = time.monotonic() + 30
        while True:
            try:
                return asyncio.run(client.request("GET", "/api/v1/health"))
            except OSError:
                assert time.monotonic() < deadline, "Source service did not restart"
                time.sleep(0.2)

    project = tmp_path / "fixture"
    project.mkdir()
    (project / "fixture.py").write_text('def source_symbol(): return "source service"\n')
    try:
        for backend in ("cpu", "cuda", "rocm"):
            output = run(
                [
                    sys.executable,
                    "-c",
                    SYSTEMD_DRIVER,
                    service,
                    "setup",
                    "--source",
                    source,
                    "--agent-harness",
                    "claude",
                    "--agent-harness",
                    "codex",
                    "--backend",
                    backend,
                    "--no-cpu-fallback",
                    "--storage",
                    storage,
                    "--port",
                    settings.port,
                ]
            )
            assert '"mode": "source"' in output
            python = source / ".venvs" / backend / "bin/python"
            unit = run(["systemctl", "--user", "cat", service])
            assert f'ExecStart="{python}" "-m" "code_search_local" "serve"' in unit
            assert f"WorkingDirectory={source}/" in unit
            pid = run(
                ["systemctl", "--user", "show", service, "--property=MainPID", "--value"]
            ).strip()
            assert Path(f"/proc/{pid}/cwd").resolve() == source
            assert Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0] == str(python).encode()
            job = asyncio.run(
                client.request(
                    "POST",
                    "/api/v1/index",
                    data={
                        "directory_path": str(project),
                        "wait": True,
                    },
                )
            )
            assert job["status"] == "succeeded"
            stats = asyncio.run(client.stats())
            assert stats["projects"][str(project)]["model"]["backend"] == backend
            assert not (storage / "runtimes").exists()
            assert not (source / "dist").exists()

        # All builds remain usable simultaneously after source setup selects ROCm.
        for backend, suffix in (("cpu", "+cpu"), ("cuda", "+cu130"), ("rocm", "+rocm7.14")):
            python = source / ".venvs" / backend / "bin/python"
            info = json.loads(
                run(
                    [
                        python,
                        "-c",
                        "import json, torch, code_search_local; "
                        "print(json.dumps([torch.__version__, code_search_local.__file__]))",
                    ]
                )
            )
            assert info[0].endswith(suffix)
            assert Path(info[1]) == source / "src/code_search_local/__init__.py"

        # Edit application source, restart the same unit, and observe the change over HTTP.
        service_source = source / "src/code_search_local/service.py"
        before = service_source.read_text()
        after = before.replace(
            '{"status": "ok", "daemon_id":',
            '{"status": "ok", "source_revision": "edited", "daemon_id":',
        )
        assert after != before
        service_source.write_text(after)
        python = source / ".venvs/rocm/bin/python"
        run([python, "-c", SYSTEMD_DRIVER, service, "service", "restart"])
        assert health()["source_revision"] == "edited"
        hits = asyncio.run(
            client.request(
                "POST",
                "/api/v1/search",
                data={
                    "project_path": str(project),
                    "query": "source_symbol",
                },
            )
        )
        assert hits["results"][0]["name"] == "source_symbol"
        assert not (source / "dist").exists()
        assert sorted(path.parent.name for path in (source / ".venvs").glob("*/pyvenv.cfg")) == [
            "cpu",
            "cuda",
            "rocm",
        ]
        run([python, "-c", SYSTEMD_DRIVER, service, "uninstall"])
        assert not (Path.home() / ".config/systemd/user" / service).exists()
        from code_search_local.harnesses import read_document

        assert "code-search-local" not in read_document(tmp_path / "codex/config.toml").get(
            "mcp_servers", {}
        )
        assert "code-search-local" not in read_document(tmp_path / "claude/.claude.json").get(
            "mcpServers", {}
        )
        assert (storage / "state.sqlite3").exists()
        assert python.exists(), "Uninstall must preserve the source environment"
    finally:
        subprocess.run(["systemctl", "--user", "disable", "--now", service], capture_output=True)
        (Path.home() / ".config/systemd/user" / service).unlink(missing_ok=True)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
