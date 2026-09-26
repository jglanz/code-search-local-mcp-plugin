import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from code_search_local import constants
from code_search_local.cli import main
from code_search_local.config import Settings, canonical_project
from code_search_local.service import token_for
from code_search_local.storage import State
from code_search_local.tui import StatsApp, report
from tests import constants as test_constants


@pytest.mark.parametrize(
    "kwargs",
    [
        {constants.KEY_BACKEND: constants.STATUS_UNKNOWN},
        {constants.KEY_HOST: "0.0.0.0"},
        {test_constants.KEY_PORT: 0},
        {test_constants.KEY_PORT: 65536},
        {constants.KEY_GPU_INDEX: -1},
        {constants.KEY_CHUNK_WORKERS: 0},
    ],
)
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_settings_precedence_and_paths(tmp_path, monkeypatch):
    Settings(backend=constants.BACKEND_ROCM, port=1234).save()
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_BACKEND, constants.BACKEND_CUDA)
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_GPU_INDEX, "2")
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_WATCH, constants.BOOLEAN_NO)
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_CPU_FALLBACK, constants.BOOLEAN_YES)
    settings = Settings.load(backend=constants.BACKEND_CPU)
    assert settings.backend == constants.BACKEND_CPU and settings.port == 1234
    assert settings.gpu_index == 2 and not settings.watch and settings.allow_fallback
    assert Settings(host=constants.LOOPBACK_IPV6).url == "http://[::1]:8000"
    assert not Settings(backend=constants.BACKEND_CUDA).allow_fallback
    assert Settings().allow_fallback
    assert canonical_project(constants.KEY_PROJECT_ROOT) == str(Path.cwd())
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_WATCH, "invalid")
    with pytest.raises(ValueError, match="Invalid boolean"):
        Settings.load()
    result = CliRunner().invoke(main, [constants.COMMAND_DOCTOR])
    assert result.exit_code == 1
    assert "Invalid boolean" in result.stderr


def snapshot_fixture(tmp_path):
    root = tmp_path / constants.KEY_STORAGE
    root.mkdir(exist_ok=True)
    state = State(root)
    project = str(tmp_path / constants.KEY_PROJECT)
    with state.edit() as value:
        value[constants.KEY_PROJECTS][project] = {
            constants.KEY_FILES: 2,
            constants.KEY_CACHE_HITS: 3,
            constants.KEY_CACHE_MISSES: 1,
            constants.KEY_MODEL: {constants.KEY_BACKEND: constants.BACKEND_CPU},
            test_constants.KEY_LAST_INDEXED: None,
        }
    state.close()
    token_for(root, create=True)
    return root, project


def test_stats_json_filter_offline_and_invalid_combination(tmp_path, monkeypatch):
    from code_search_local.client import Client

    root, project = snapshot_fixture(tmp_path)
    monkeypatch.setattr(Client, constants.KEY_STATS, AsyncMock(side_effect=OSError("offline")))
    runner = CliRunner()
    result = runner.invoke(
        main, [constants.KEY_STATS, constants.OPTION_JSON, constants.OPTION_PROJECT, project]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not data[constants.KEY_ONLINE]
    assert data[constants.KEY_PROJECTS][project][constants.KEY_CACHE_HIT_RATIO] == 0.75
    assert not result.stderr
    assert (
        runner.invoke(
            main, [constants.KEY_STATS, constants.OPTION_LIVE, constants.OPTION_JSON]
        ).exit_code
        == 2
    )
    unknown = runner.invoke(
        main,
        [constants.KEY_STATS, constants.OPTION_JSON, constants.OPTION_PROJECT, "/does/not/exist"],
    )
    assert unknown.exit_code == 1
    assert "not registered" in unknown.stderr


@pytest.mark.parametrize(
    "args,method,path",
    [
        (
            [
                "index",
                constants.KEY_PROJECT_ROOT,
                test_constants.OPTION_NO_WAIT,
                test_constants.OPTION_REBUILD,
                constants.OPTION_PATTERN,
                "*.py",
            ],
            constants.HTTP_POST,
            constants.INDEX_ENDPOINT,
        ),
        (
            [
                "search",
                "hello",
                constants.OPTION_PROJECT,
                constants.KEY_PROJECT_ROOT,
                constants.SHORT_OPTION_K,
                "3",
            ],
            constants.HTTP_POST,
            constants.SEARCH_ENDPOINT,
        ),
        (
            [
                "search",
                "hello",
                constants.OPTION_PROJECT,
                constants.KEY_PROJECT_ROOT,
                constants.OPTION_MAX_RESULTS,
                "3",
            ],
            constants.HTTP_POST,
            constants.SEARCH_ENDPOINT,
        ),
        (
            ["job", "123", constants.OPTION_PROJECT, constants.KEY_PROJECT_ROOT],
            constants.HTTP_GET,
            "/api/v1/jobs/123",
        ),
        (
            [
                "job",
                "123",
                constants.OPTION_PROJECT,
                constants.KEY_PROJECT_ROOT,
                constants.OPTION_CANCEL,
            ],
            constants.HTTP_DELETE,
            "/api/v1/jobs/123",
        ),
    ],
)
def test_cli_delegates_to_shared_service(args, method, path, monkeypatch):
    from code_search_local.client import Client

    call = AsyncMock(return_value={test_constants.KEY_SUCCESS: True})
    monkeypatch.setattr(Client, "request", call)
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[test_constants.KEY_SUCCESS]
    assert call.call_args.args == (method, path)
    if path == constants.SEARCH_ENDPOINT:
        assert call.call_args.kwargs[test_constants.KEY_DATA][constants.KEY_K] == 3
    call.side_effect = OSError("not running")
    assert CliRunner().invoke(main, args).exit_code == 1


def test_doctor_lightweight():
    result = CliRunner().invoke(
        main,
        [
            constants.COMMAND_DOCTOR,
            constants.OPTION_BACKEND,
            constants.BACKEND_ROCM,
            constants.OPTION_GPU_INDEX,
            constants.ENV_ENABLED,
        ],
    )
    assert result.exit_code == 0
    assert (
        json.loads(result.stdout)[constants.KEY_SETTINGS][constants.KEY_BACKEND]
        == constants.BACKEND_ROCM
    )


async def test_textual_report_and_live_updates(tmp_path):
    root, project = snapshot_fixture(tmp_path)
    from code_search_local.storage import offline_stats

    data = offline_stats(root)

    class Feed:
        async def snapshots(self):
            yield {**data, constants.KEY_ONLINE: True, constants.KEY_SEQUENCE: 100}

    app = StatsApp(data, Feed())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.snapshot[constants.KEY_SEQUENCE] == 100
        assert app.query_one("#report")
        await pilot.press("q")
    single = StatsApp(data)
    async with single.run_test() as pilot:
        await pilot.pause()
    assert report(data).row_count > 10


def test_cli_textual_modes(tmp_path, monkeypatch):
    from code_search_local.client import Client

    monkeypatch.setattr(
        Client,
        constants.KEY_STATS,
        AsyncMock(
            return_value={
                constants.KEY_PROJECTS: {},
                constants.KEY_SHARED: {},
                constants.KEY_JOBS: {},
                constants.KEY_ONLINE: True,
            }
        ),
    )
    calls = []
    monkeypatch.setattr(
        StatsApp, "run", lambda self, **kwargs: calls.append((self.subscriber, kwargs))
    )
    runner = CliRunner()
    assert runner.invoke(main, [constants.KEY_STATS]).exit_code == 0
    assert calls[-1][0] is None and calls[-1][1][test_constants.KEY_INLINE]
    assert runner.invoke(main, [constants.KEY_STATS, constants.OPTION_LIVE]).exit_code == 0
    assert calls[-1][0] is not None and not calls[-1][1][test_constants.KEY_INLINE]


def test_doctor_inference_and_module_entry_point(tmp_path, monkeypatch):
    import runpy

    import code_search_local.models as models
    from tests.fakes import FakeModel

    monkeypatch.setattr(models, "SentenceModel", FakeModel)
    settings = tmp_path / test_constants.PATH_CANDIDATE_JSON
    Settings().save()
    from dataclasses import asdict

    settings.write_text(json.dumps(asdict(Settings())))
    result = CliRunner().invoke(
        main,
        [
            constants.COMMAND_DOCTOR,
            constants.OPTION_SETTINGS_FILE,
            str(settings),
            constants.OPTION_INFERENCE,
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[test_constants.KEY_SHAPE] == [1, 64]

    def fail(*args, **kwargs):
        raise RuntimeError("invalid runtime")

    monkeypatch.setattr(models, "SentenceModel", fail)
    assert (
        CliRunner().invoke(main, [constants.COMMAND_DOCTOR, constants.OPTION_INFERENCE]).exit_code
        == 1
    )
    monkeypatch.setattr(sys, "argv", [constants.APPLICATION_NAME, test_constants.OPTION_VERSION])
    with pytest.raises(SystemExit) as exit:
        runpy.run_module(constants.PACKAGE_NAME, run_name="__main__")
    assert exit.value.code == 0


def test_warmup_uses_service_request(monkeypatch):
    from code_search_local import cli

    calls = []
    monkeypatch.setattr(cli, "request", lambda *args: calls.append(args))
    result = CliRunner().invoke(main, ["warmup"])
    assert result.exit_code == 0
    assert calls == [(constants.HTTP_POST, constants.MODEL_ENDPOINT)]


def test_live_starts_offline_and_fetches_after_recovery(tmp_path, monkeypatch):
    import asyncio

    from code_search_local.client import Client

    snapshot_fixture(tmp_path)
    calls = AsyncMock(
        side_effect=[OSError("offline"), OSError("offline"), {constants.KEY_ONLINE: True}]
    )
    monkeypatch.setattr(Client, constants.KEY_STATS, calls)

    def run(app, **kwargs):
        assert not app.snapshot[constants.KEY_ONLINE]
        assert not asyncio.run(app.subscriber.fetch())[constants.KEY_ONLINE]
        assert asyncio.run(app.subscriber.fetch())[constants.KEY_ONLINE]

    monkeypatch.setattr(StatsApp, "run", run)
    result = CliRunner().invoke(main, [constants.KEY_STATS, constants.OPTION_LIVE])
    assert result.exit_code == 0, result.output
