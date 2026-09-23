"""Required release lane: two real Claude processes, real model, cold cache.

Run CODE_SEARCH_REAL_CLIENTS=1 uv run --extra server --extra cuda pytest -m clients.
Missing credentials fail this opted-in lane; they never turn into a passing mock test.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.service import token_for
from tests.helpers import free_port, wait_healthy

pytestmark = [pytest.mark.clients, pytest.mark.real_model]
AUTH_SOURCE = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def test_two_real_claude_instances(tmp_path):
    if os.environ.get("CODE_SEARCH_REAL_CLIENTS") != "1":
        pytest.skip(
            "Opt into the authenticated real-client release lane with CODE_SEARCH_REAL_CLIENTS=1"
        )
    auth = subprocess.run(
        ["claude", "auth", "status"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "CLAUDE_CONFIG_DIR": str(AUTH_SOURCE)},
    )
    assert json.loads(auth.stdout)["loggedIn"], (
        "Claude authentication is required for this release lane"
    )
    backend = os.environ.get("CODE_SEARCH_TEST_BACKEND", "cuda")
    settings = Settings(storage=str(tmp_path / "cold-state"), port=free_port(), watch=False)
    client = Client(settings)
    roots = []
    for name in ("quartz", "saffron"):
        root = tmp_path / name
        root.mkdir()
        (root / "shared.py").write_text('def common_helper():\n    return "shared cache"\n')
        (root / f"{name}.py").write_text(
            f'def {name}_only():\n    """Unique {name} fixture."""\n    return "{name}"\n'
        )
        roots.append(root)
    command = [
        sys.executable,
        "-m",
        "tests.daemon",
        "--storage",
        settings.storage,
        "--port",
        str(settings.port),
        "--backend",
        backend,
        "--gate",
        "2",
    ]
    auth_dir = tmp_path / "claude-auth"
    auth_dir.mkdir(mode=0o700)
    original_auth = AUTH_SOURCE / ".credentials.json"
    if original_auth.exists():
        shutil.copy2(original_auth, auth_dir / ".credentials.json")
        (auth_dir / ".credentials.json").chmod(0o600)
    env = {
        **os.environ,
        "HF_HUB_DISABLE_XET": "1",
        "CLAUDE_CONFIG_DIR": str(auth_dir),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    log = (tmp_path / "daemon.log").open("w+")
    process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
    try:
        wait_healthy(process, client, log)
        mcp_path = tmp_path / "mcp.json"
        mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "code-search-local": {
                            "type": "http",
                            "url": settings.url + "/mcp",
                            "headers": {"Authorization": "Bearer " + token_for(settings.root)},
                        }
                    }
                }
            )
        )
        mcp_path.chmod(0o600)

        def run_claude(root):
            prompt = (
                f"Integration test: call mcp__code-search-local__index_directory for directory_path={str(root)!r}, "
                f"wait=true. Then call mcp__code-search-local__search_code with project_path={str(root)!r}, "
                f"query={root.name!r}. Use both tools now. Do not inspect files or run shell commands. "
                "Briefly report whether indexing succeeded and search found the fixture."
            )
            args = [
                "claude",
                "--setting-sources",
                "",
                "--settings",
                '{"disableAllHooks":true}',
                "-p",
                prompt,
                "--strict-mcp-config",
                "--mcp-config",
                str(mcp_path),
                "--no-session-persistence",
                "--output-format",
                "stream-json",
                "--verbose",
                "--tools",
                "",
                "--allowedTools",
                "mcp__code-search-local__index_directory",
                "mcp__code-search-local__search_code",
            ]
            result = subprocess.run(
                args, cwd=root, capture_output=True, text=True, timeout=300, env=env
            )
            (tmp_path / f"{root.name}-claude.jsonl").write_text(result.stdout)
            assert result.returncode == 0, result.stderr + result.stdout[-3000:]
            events = [
                json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")
            ]
            calls = [
                block
                for event in events
                if event.get("type") == "assistant"
                for block in event.get("message", {}).get("content", [])
                if block.get("type") == "tool_use"
            ]
            assert any(c["name"].endswith("index_directory") for c in calls), result.stdout
            assert any(c["name"].endswith("search_code") for c in calls), result.stdout
            return events

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(run_claude, roots))
        stats = asyncio.run(client.stats())
        (tmp_path / "stats-first.json").write_text(json.dumps(stats, indent=2))
        assert len(stats["projects"]) == 2
        jobs = list(stats["jobs"].values())
        assert len(jobs) == 2 and all(job["status"] == "succeeded" for job in jobs)
        assert max(job["started_at"] for job in jobs) < min(job["finished_at"] for job in jobs)
        assert stats["shared"]["model_acquisitions"] == 1
        assert stats["shared"]["model_downloads"] == 1
        assert stats["shared"]["model_loads"] == 1
        assert stats["shared"]["max_concurrent_inference"] == 1
        assert stats["shared"]["model"]["backend"] == backend
        assert stats["shared"]["model"]["fallback_reason"] is None
        assert sum(p["cache_hits"] for p in stats["projects"].values()) >= 1
        audit = settings.root / "download-transfers.jsonl"
        transfers = [json.loads(line) for line in audit.read_text().splitlines()]
        assert transfers and all(event["bytes"] > 0 for event in transfers)
        names = [event["blob"] for event in transfers]
        assert len(names) == len(set(names)), "An artifact was transferred more than once"
        blobs = {
            str(p): (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns)
            for p in (settings.root / "models").glob("models--*/blobs/*")
            if p.is_file()
        }
        assert len(blobs) == stats["shared"]["downloaded_files"]
        for root in roots:
            result = asyncio.run(
                client.request(
                    "POST", "/api/v1/search", data={"project_path": str(root), "query": root.name}
                )
            )
            assert all(Path(hit["file_path"]).is_relative_to(root) for hit in result["results"])
            assert any(root.name in hit["name"] for hit in result["results"])
        process.terminate()
        process.wait(30)
        process = subprocess.Popen([*command[:-2], "--offline"], stdout=log, stderr=log, env=env)
        wait_healthy(process, client, log)
        for root in roots:
            result = asyncio.run(
                client.request(
                    "POST", "/api/v1/search", data={"project_path": str(root), "query": root.name}
                )
            )
            assert result["results"]
        after = asyncio.run(client.stats())
        assert after["shared"]["model_downloads"] == 1
        assert audit.read_text().splitlines() == [
            json.dumps(event, sort_keys=True) for event in transfers
        ]
        assert blobs == {
            str(p): (p.stat().st_ino, p.stat().st_size, p.stat().st_mtime_ns)
            for p in (settings.root / "models").glob("models--*/blobs/*")
            if p.is_file()
        }
        for root in roots:
            (root / f"{root.name}.py").unlink()
            (root / "updated.py").write_text(f'def {root.name}_updated(): return "changed"\n')

        async def update():
            return await asyncio.gather(
                *(
                    client.request(
                        "POST", "/api/v1/index", data={"directory_path": str(root), "wait": True}
                    )
                    for root in roots
                )
            )

        updated = asyncio.run(update())
        assert all(
            job["result"]["changes"] == {"added": 1, "deleted": 1, "modified": 0} for job in updated
        )
    finally:
        process.terminate()
        process.wait(30)
        log.close()
        shutil.rmtree(auth_dir)
