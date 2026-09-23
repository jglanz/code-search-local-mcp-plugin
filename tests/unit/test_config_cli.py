import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from code_search_local.cli import main
from code_search_local.config import Settings, canonical_project
from code_search_local.service import token_for
from code_search_local.storage import State
from code_search_local.tui import StatsApp, report


@pytest.mark.parametrize(
    "kwargs",
    [
        {"backend": "unknown"},
        {"host": "0.0.0.0"},
        {"port": 0},
        {"port": 65536},
        {"gpu_index": -1},
        {"chunk_workers": 0},
    ],
)
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_settings_precedence_and_paths(tmp_path, monkeypatch):
    Settings(backend="rocm", port=1234).save()
    monkeypatch.setenv("CODE_SEARCH_BACKEND", "cuda")
    monkeypatch.setenv("CODE_SEARCH_GPU_INDEX", "2")
    monkeypatch.setenv("CODE_SEARCH_WATCH", "no")
    monkeypatch.setenv("CODE_SEARCH_CPU_FALLBACK", "yes")
    settings = Settings.load(backend="cpu")
    assert settings.backend == "cpu" and settings.port == 1234
    assert settings.gpu_index == 2 and not settings.watch and settings.allow_fallback
    assert Settings(host="::1").url == "http://[::1]:8000"
    assert not Settings(backend="cuda").allow_fallback
    assert Settings().allow_fallback
    assert canonical_project(".") == str(Path.cwd())
    monkeypatch.setenv("CODE_SEARCH_WATCH", "invalid")
    with pytest.raises(ValueError, match="Invalid boolean"):
        Settings.load()
    result = CliRunner().invoke(main, ["doctor"])
    assert result.exit_code == 1
    assert "Invalid boolean" in result.stderr


def snapshot_fixture(tmp_path):
    root = tmp_path / "storage"
    root.mkdir(exist_ok=True)
    state = State(root)
    project = str(tmp_path / "project")
    with state.edit() as value:
        value["projects"][project] = {
            "files": 2,
            "cache_hits": 3,
            "cache_misses": 1,
            "model": {"backend": "cpu"},
            "last_indexed": None,
        }
    state.close()
    token_for(root, create=True)
    return root, project


def test_stats_json_filter_offline_and_invalid_combination(tmp_path, monkeypatch):
    from code_search_local.client import Client

    root, project = snapshot_fixture(tmp_path)
    monkeypatch.setattr(Client, "stats", AsyncMock(side_effect=OSError("offline")))
    runner = CliRunner()
    result = runner.invoke(main, ["stats", "--json", "--project", project])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert not data["online"]
    assert data["projects"][project]["cache_hit_ratio"] == 0.75
    assert not result.stderr
    assert runner.invoke(main, ["stats", "--live", "--json"]).exit_code == 2
    unknown = runner.invoke(main, ["stats", "--json", "--project", "/does/not/exist"])
    assert unknown.exit_code == 1
    assert "not registered" in unknown.stderr


@pytest.mark.parametrize(
    "args,method,path",
    [
        (["index", ".", "--no-wait", "--rebuild", "--pattern", "*.py"], "POST", "/api/v1/index"),
        (["search", "hello", "--project", ".", "-k", "3"], "POST", "/api/v1/search"),
        (["job", "123", "--project", "."], "GET", "/api/v1/jobs/123"),
        (["job", "123", "--project", ".", "--cancel"], "DELETE", "/api/v1/jobs/123"),
    ],
)
def test_cli_delegates_to_shared_service(args, method, path, monkeypatch):
    from code_search_local.client import Client

    call = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(Client, "request", call)
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["success"]
    assert call.call_args.args == (method, path)
    call.side_effect = OSError("not running")
    assert CliRunner().invoke(main, args).exit_code == 1


def test_doctor_lightweight():
    result = CliRunner().invoke(main, ["doctor", "--backend", "rocm", "--gpu-index", "1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["settings"]["backend"] == "rocm"


async def test_textual_report_and_live_updates(tmp_path):
    root, project = snapshot_fixture(tmp_path)
    from code_search_local.storage import offline_stats

    data = offline_stats(root)

    class Feed:
        async def snapshots(self):
            yield {**data, "online": True, "sequence": 100}

    app = StatsApp(data, Feed())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.snapshot["sequence"] == 100
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
        "stats",
        AsyncMock(return_value={"projects": {}, "shared": {}, "jobs": {}, "online": True}),
    )
    calls = []
    monkeypatch.setattr(
        StatsApp, "run", lambda self, **kwargs: calls.append((self.subscriber, kwargs))
    )
    runner = CliRunner()
    assert runner.invoke(main, ["stats"]).exit_code == 0
    assert calls[-1][0] is None and calls[-1][1]["inline"]
    assert runner.invoke(main, ["stats", "--live"]).exit_code == 0
    assert calls[-1][0] is not None and not calls[-1][1]["inline"]


def test_doctor_inference_and_module_entry_point(tmp_path, monkeypatch):
    import runpy

    import code_search_local.models as models
    from tests.fakes import FakeModel

    monkeypatch.setattr(models, "SentenceModel", FakeModel)
    settings = tmp_path / "candidate.json"
    Settings().save()
    from dataclasses import asdict

    settings.write_text(json.dumps(asdict(Settings())))
    result = CliRunner().invoke(main, ["doctor", "--settings-file", str(settings), "--inference"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["shape"] == [1, 64]

    def fail(*args, **kwargs):
        raise RuntimeError("invalid runtime")

    monkeypatch.setattr(models, "SentenceModel", fail)
    assert CliRunner().invoke(main, ["doctor", "--inference"]).exit_code == 1
    monkeypatch.setattr(sys, "argv", ["code-search-local", "--version"])
    with pytest.raises(SystemExit) as exit:
        runpy.run_module("code_search_local", run_name="__main__")
    assert exit.value.code == 0


def test_warmup_uses_service_request(monkeypatch):
    from code_search_local import cli

    calls = []
    monkeypatch.setattr(cli, "request", lambda *args: calls.append(args))
    result = CliRunner().invoke(main, ["warmup"])
    assert result.exit_code == 0
    assert calls == [("POST", "/api/v1/model")]


def test_live_starts_offline_and_fetches_after_recovery(tmp_path, monkeypatch):
    import asyncio

    from code_search_local.client import Client

    snapshot_fixture(tmp_path)
    calls = AsyncMock(side_effect=[OSError("offline"), OSError("offline"), {"online": True}])
    monkeypatch.setattr(Client, "stats", calls)

    def run(app, **kwargs):
        assert not app.snapshot["online"]
        assert not asyncio.run(app.subscriber.fetch())["online"]
        assert asyncio.run(app.subscriber.fetch())["online"]

    monkeypatch.setattr(StatsApp, "run", run)
    result = CliRunner().invoke(main, ["stats", "--live"])
    assert result.exit_code == 0, result.output
