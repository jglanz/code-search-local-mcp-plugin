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

from code_search_local import constants
from code_search_local.client import Client
from code_search_local.config import Settings
from code_search_local.service import token_for
from tests import constants as test_constants
from tests.helpers import free_port, model_blob_fingerprints, search_project, wait_healthy

pytestmark = [pytest.mark.clients, pytest.mark.real_model]
AUTH_SOURCE = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def test_two_real_claude_instances(tmp_path):
    if os.environ.get(test_constants.ENV_CODE_SEARCH_REAL_CLIENTS) != constants.ENV_ENABLED:
        pytest.skip(
            "Opt into the authenticated real-client release lane with CODE_SEARCH_REAL_CLIENTS=1"
        )
    auth = subprocess.run(
        [constants.HARNESS_CLAUDE, "auth", constants.KEY_STATUS],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, constants.ENV_CLAUDE_CONFIG_DIR: str(AUTH_SOURCE)},
    )
    assert json.loads(auth.stdout)[test_constants.KEY_LOGGED_IN], (
        "Claude authentication is required for this release lane"
    )
    backend = os.environ.get(test_constants.ENV_CODE_SEARCH_TEST_BACKEND, constants.BACKEND_CUDA)
    settings = Settings(
        storage=str(tmp_path / test_constants.PATH_COLD_STATE), port=free_port(), watch=False
    )
    client = Client(settings)
    roots = []
    for name in ("quartz", "saffron"):
        root = tmp_path / name
        root.mkdir()
        (root / test_constants.PATH_SHARED_PY).write_text(
            'def common_helper():\n    return "shared cache"\n'
        )
        (root / f"{name}.py").write_text(
            f'def {name}_only():\n    """Unique {name} fixture."""\n    return "{name}"\n'
        )
        roots.append(root)
    command = [
        sys.executable,
        constants.SHORT_OPTION_M,
        "tests.daemon",
        constants.OPTION_STORAGE,
        settings.storage,
        constants.OPTION_PORT,
        str(settings.port),
        constants.OPTION_BACKEND,
        backend,
        test_constants.OPTION_GATE,
        "2",
    ]
    auth_dir = tmp_path / test_constants.PATH_CLAUDE_AUTH
    auth_dir.mkdir(mode=0o700)
    original_auth = AUTH_SOURCE / test_constants.PATH_CREDENTIALS_JSON
    if original_auth.exists():
        shutil.copy2(original_auth, auth_dir / test_constants.PATH_CREDENTIALS_JSON)
        (auth_dir / test_constants.PATH_CREDENTIALS_JSON).chmod(0o600)
    env = {
        **os.environ,
        test_constants.ENV_HF_HUB_DISABLE_XET: constants.ENV_ENABLED,
        constants.ENV_CLAUDE_CONFIG_DIR: str(auth_dir),
        test_constants.ENV_CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: constants.ENV_ENABLED,
    }
    log = (tmp_path / test_constants.PATH_DAEMON_LOG).open(test_constants.FILE_MODE_W)
    process = subprocess.Popen(command, stdout=log, stderr=log, env=env)
    try:
        wait_healthy(process, client, log)
        mcp_path = tmp_path / test_constants.PATH_MCP_JSON
        mcp_path.write_text(
            json.dumps(
                {
                    constants.KEY_MCP_SERVERS: {
                        constants.APPLICATION_NAME: {
                            constants.KEY_TYPE: constants.TRANSPORT_HTTP,
                            constants.KEY_URL: settings.url + constants.MCP_ENDPOINT,
                            constants.KEY_HEADERS: {
                                constants.KEY_AUTHORIZATION: constants.HTTP_BEARER
                                + token_for(settings.root)
                            },
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
                constants.HARNESS_CLAUDE,
                test_constants.OPTION_SETTING_SOURCES,
                "",
                test_constants.OPTION_SETTINGS,
                '{"disableAllHooks":true}',
                test_constants.SHORT_OPTION_P,
                prompt,
                test_constants.OPTION_STRICT_MCP_CONFIG,
                test_constants.OPTION_MCP_CONFIG,
                str(mcp_path),
                test_constants.OPTION_NO_SESSION_PERSISTENCE,
                test_constants.OPTION_OUTPUT_FORMAT,
                "stream-json",
                test_constants.OPTION_VERBOSE,
                test_constants.OPTION_TOOLS,
                "",
                test_constants.OPTION_ALLOWED_TOOLS,
                "mcp__code-search-local__index_directory",
                "mcp__code-search-local__search_code",
            ]
            result = subprocess.run(
                args,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=test_constants.REAL_CLIENT_TIMEOUT_SECONDS,
                env=env,
            )
            (tmp_path / f"{root.name}-claude.jsonl").write_text(result.stdout)
            assert result.returncode == 0, result.stderr + result.stdout[-3000:]
            events = [
                json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")
            ]
            calls = [
                block
                for event in events
                if event.get(constants.KEY_TYPE) == test_constants.VALUE_ASSISTANT
                for block in event.get(test_constants.KEY_MESSAGE, {}).get(
                    constants.KEY_CONTENT, []
                )
                if block.get(constants.KEY_TYPE) == test_constants.VALUE_TOOL_USE
            ]
            assert any(c[constants.KEY_NAME].endswith("index_directory") for c in calls), (
                result.stdout
            )
            assert any(c[constants.KEY_NAME].endswith("search_code") for c in calls), result.stdout
            return events

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(run_claude, roots))
        stats = asyncio.run(client.stats())
        (tmp_path / test_constants.PATH_STATS_FIRST_JSON).write_text(json.dumps(stats, indent=2))
        assert len(stats[constants.KEY_PROJECTS]) == 2
        jobs = list(stats[constants.KEY_JOBS].values())
        assert len(jobs) == 2 and all(
            job[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED for job in jobs
        )
        assert max(job[test_constants.KEY_STARTED_AT] for job in jobs) < min(
            job[test_constants.KEY_FINISHED_AT] for job in jobs
        )
        assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_ACQUISITIONS] == 1
        assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_DOWNLOADS] == 1
        assert stats[constants.KEY_SHARED][test_constants.KEY_MODEL_LOADS] == 1
        assert stats[constants.KEY_SHARED][constants.KEY_MAX_CONCURRENT_INFERENCE] == 1
        assert stats[constants.KEY_SHARED][constants.KEY_MODEL][constants.KEY_BACKEND] == backend
        assert (
            stats[constants.KEY_SHARED][constants.KEY_MODEL][constants.KEY_FALLBACK_REASON] is None
        )
        assert sum(p[constants.KEY_CACHE_HITS] for p in stats[constants.KEY_PROJECTS].values()) >= 1
        audit = settings.root / test_constants.PATH_DOWNLOAD_TRANSFERS_JSONL
        transfers = [json.loads(line) for line in audit.read_text().splitlines()]
        assert transfers and all(event[test_constants.KEY_BYTES] > 0 for event in transfers)
        names = [event[test_constants.KEY_BLOB] for event in transfers]
        assert len(names) == len(set(names)), "An artifact was transferred more than once"
        blobs = model_blob_fingerprints(settings.root)
        assert len(blobs) == stats[constants.KEY_SHARED][test_constants.KEY_DOWNLOADED_FILES]
        for root in roots:
            result = search_project(client, str(root), root.name)
            assert all(
                Path(hit[test_constants.KEY_FILE_PATH]).is_relative_to(root)
                for hit in result[constants.KEY_RESULTS]
            )
            assert any(
                root.name in hit[constants.KEY_NAME] for hit in result[constants.KEY_RESULTS]
            )
        process.terminate()
        process.wait(test_constants.SLOW_PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
        process = subprocess.Popen(
            [*command[:-2], test_constants.OPTION_OFFLINE], stdout=log, stderr=log, env=env
        )
        wait_healthy(process, client, log)
        for root in roots:
            result = search_project(client, str(root), root.name)
            assert result[constants.KEY_RESULTS]
        after = asyncio.run(client.stats())
        assert after[constants.KEY_SHARED][test_constants.KEY_MODEL_DOWNLOADS] == 1
        assert audit.read_text().splitlines() == [
            json.dumps(event, sort_keys=True) for event in transfers
        ]
        assert blobs == model_blob_fingerprints(settings.root)
        for root in roots:
            (root / f"{root.name}.py").unlink()
            (root / test_constants.PATH_UPDATED_PY).write_text(
                f'def {root.name}_updated(): return "changed"\n'
            )

        async def update():
            return await asyncio.gather(
                *(
                    client.request(
                        constants.HTTP_POST,
                        constants.INDEX_ENDPOINT,
                        data={constants.KEY_DIRECTORY_PATH: str(root), constants.KEY_WAIT: True},
                    )
                    for root in roots
                )
            )

        updated = asyncio.run(update())
        assert all(
            job[test_constants.KEY_RESULT][constants.KEY_CHANGES]
            == {constants.KEY_ADDED: 1, constants.KEY_DELETED: 1, constants.KEY_MODIFIED: 0}
            for job in updated
        )
    finally:
        process.terminate()
        process.wait(test_constants.SLOW_PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
        log.close()
        shutil.rmtree(auth_dir)
