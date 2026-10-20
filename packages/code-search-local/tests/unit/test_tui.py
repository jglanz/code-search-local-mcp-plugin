"""Statistics TUI: section renderers, inline report, live bindings and CLI wiring."""

import asyncio
import io
import json
import math
import sqlite3
import sys
from datetime import datetime
from itertools import cycle, pairwise
from unittest.mock import AsyncMock

import click
import pytest
import zmq
from click.testing import CliRunner
from rich.console import Console
from textual.worker import WorkerState

from code_search_local import constants, tui
from code_search_local.cli import main
from code_search_local.client import Client
from code_search_local.config import canonical_project
from code_search_local.storage import State, offline_stats
from code_search_local.tui import (
    StatsApp,
    decimal,
    inline_report,
    job_row,
    jobs_table,
    joined,
    local_time,
    percent,
    progress,
    projects_table,
    rate,
    summary_panel,
)
from tests import constants as test_constants
from tests.helpers import invoke_on_terminal

CONSOLE_WIDTH = 220
TERMINAL_SIZE = (160, 60)
PLAIN_REPORT_COLUMNS = 120
# Longer than any test: only cancellation ends a backoff that sleeps this long.
BACKOFF_HOLD_SECONDS = 60
ESCAPE = "\x1b"
SECTION_TITLES = (
    "Summary",
    "Projects — hit rate % (hits/misses)",
    "Top paths",
    "Index jobs",
    "Code Search Local — offline snapshot",
)
# Every failure the live view recovers from, in the order the fake subscriber raises them.
FOLLOW_ERRORS = (
    OSError,
    RuntimeError,
    KeyError,
    ValueError,
    sqlite3.OperationalError,
    zmq.ZMQError,
)
# A service response whose body is not JSON, as the HTTP client reports it.
MALFORMED_RESPONSE = json.JSONDecodeError("Expecting value", "<html>", 0)
ROOT = "/work/project"
MODEL_NAME = "example/embedder"
JOB_ID = "0123456789abcdef0123456789abcdef"
INDEXED_AT = "2026-01-02T03:04:05+00:00"
PATH_HIT = "src/hit.py"
PATH_MISS = "src/miss.py"
LONG_ERROR = "x" * (constants.TUI_ERROR_CHARACTERS * 2)
RELEVANCE = (constants.KEY_SEARCH_RELEVANCE_HITS, constants.KEY_SEARCH_RELEVANCE_MISSES)


def rendered(renderable):
    console = Console(file=io.StringIO(), record=True, width=CONSOLE_WIDTH)
    console.print(renderable)
    return console.export_text()


def full_snapshot(tmp_path):
    """An offline snapshot with a model, search history and one running job."""
    state = State(tmp_path)
    with state.edit() as value:
        value[constants.KEY_SHARED][constants.KEY_SEARCH_HIT_MIN_SCORE] = (
            constants.DEFAULT_SEARCH_HIT_MIN_SCORE
        )
        value[constants.KEY_SHARED][constants.KEY_MODEL] = {
            constants.KEY_MODEL: MODEL_NAME,
            constants.KEY_REVISION: constants.DEFAULT_MODEL_REVISION,
            constants.KEY_BACKEND: constants.BACKEND_CPU,
            constants.KEY_DEVICE: constants.BACKEND_CPU,
        }
        value[constants.KEY_PROJECTS][ROOT] = {
            constants.KEY_FILES: 7,
            constants.KEY_CHUNKS: 21,
            constants.KEY_SEARCHES: 4,
            constants.KEY_INDEXED_AT: INDEXED_AT,
            constants.KEY_SEARCH_RELEVANCE_HITS: 3,
            constants.KEY_SEARCH_RELEVANCE_MISSES: 1,
        }
        state.record_search_paths(
            ROOT,
            [
                {constants.KEY_RELATIVE_PATH: PATH_HIT, constants.KEY_SCORE: 0.9},
                {constants.KEY_RELATIVE_PATH: PATH_MISS, constants.KEY_SCORE: 0.1},
            ],
            constants.DEFAULT_SEARCH_HIT_MIN_SCORE,
            INDEXED_AT,
        )
        value[constants.KEY_JOBS][JOB_ID] = {
            constants.KEY_JOB_ID: JOB_ID,
            constants.KEY_PROJECT_PATH: ROOT,
            constants.KEY_STATUS: constants.STATUS_RUNNING,
            constants.KEY_QUEUED_AT: INDEXED_AT,
            constants.KEY_FILES_PROCESSED: 3,
            constants.KEY_FILES_TOTAL: 4,
        }
    state.close()
    return offline_stats(tmp_path)


class Feed:
    """A subscriber whose first subscriptions fail with ``errors``; later ones yield snapshots."""

    def __init__(self, *snapshots, errors=()):
        self.items, self.errors = snapshots, list(errors)
        self.subscriptions = 0

    async def snapshots(self):
        self.subscriptions += 1
        if self.errors:
            raise self.errors.pop(0)
        for snapshot in self.items:
            yield snapshot


def recorded_notifications(app):
    """Replace the app's notifications with a list of (message, severity, markup)."""
    notes = []
    app.notify = lambda message, *, severity, timeout, markup: notes.append(
        (message, severity, markup)
    )
    return notes


def test_rate_number_and_time_formatting():
    assert percent(0, 0) == constants.TUI_MISSING_VALUE
    assert rate({}, *RELEVANCE) == constants.TUI_MISSING_VALUE + " (0/0)"
    assert rate(dict(zip(RELEVANCE, (0, 2))), *RELEVANCE) == "0.0% (0/2)"
    assert rate(dict(zip(RELEVANCE, (1, 2))), *RELEVANCE) == "33.3% (1/2)"
    assert decimal(None, constants.TUI_SCORE_DECIMALS) == constants.TUI_MISSING_VALUE
    assert decimal(0.5, constants.TUI_SCORE_DECIMALS) == "0.500"
    assert decimal(1.26, constants.TUI_DURATION_DECIMALS, " s") == "1.3 s"
    assert joined(" / ", None, "") == constants.TUI_MISSING_VALUE
    assert local_time(None) == constants.TUI_MISSING_VALUE
    assert local_time("not a time") == "not a time"
    assert local_time(INDEXED_AT) == datetime.fromisoformat(INDEXED_AT).astimezone().strftime(
        constants.TUI_DATETIME_FORMAT
    )


def test_job_progress_error_truncation_and_limit():
    assert progress(3, None) == constants.TUI_MISSING_VALUE
    assert progress(0, 0) == constants.TUI_MISSING_VALUE
    assert "75.0%" in rendered(progress(3, 4))
    row = job_row(JOB_ID, {constants.KEY_ERROR: LONG_ERROR})
    assert row[0] == JOB_ID[: constants.TUI_JOB_ID_CHARACTERS]
    assert row[3] == "0 / " + constants.TUI_MISSING_VALUE
    assert len(row[-1].plain) == constants.TUI_ERROR_CHARACTERS
    assert row[-1].plain.endswith("…")
    jobs = {
        str(number): {constants.KEY_QUEUED_AT: f"2026-01-01T00:00:{number:02d}"}
        for number in range(constants.TUI_JOBS_LIMIT + 1)
    }
    table = jobs_table({constants.KEY_JOBS: jobs})
    assert table.row_count == constants.TUI_JOBS_LIMIT
    assert f"Newest {constants.TUI_JOBS_LIMIT} of {len(jobs)}" in table.caption
    newest = str(constants.TUI_JOBS_LIMIT)
    assert rendered(table).index(" " + newest + " ") < rendered(table).index(" 1 ")


def test_inline_report_renders_every_section(tmp_path):
    data = full_snapshot(tmp_path)
    text = rendered(inline_report(data))
    for expected in (
        "Summary",
        "offline snapshot",
        f"{MODEL_NAME} @ {constants.DEFAULT_MODEL_REVISION}",
        "0.500",
        f"{constants.BACKEND_CPU} / {constants.BACKEND_CPU}",
        "75.0% (3/1)",
        PATH_HIT,
        PATH_MISS,
        JOB_ID[: constants.TUI_JOB_ID_CHARACTERS],
        constants.KEY_SEARCH_RELEVANCE_HIT_RATIO,
        constants.KEY_TOP_PATHS,
    ):
        assert expected in text
    project_line = next(
        line for line in rendered(projects_table(data)).splitlines() if ROOT in line
    )
    active_jobs = project_line.split("│")[-2]
    assert active_jobs.strip() == "1"


def test_empty_and_legacy_snapshots_render_placeholders():
    empty = rendered(inline_report({}))
    for expected in ("No projects registered", "No search results recorded", "No index jobs"):
        assert expected in empty
    legacy = {
        constants.KEY_ONLINE: True,
        constants.KEY_SHARED: {constants.KEY_MODEL_RESIDENT: True},
        constants.KEY_PROJECTS: {ROOT: {constants.KEY_FILES: 1}},
        constants.KEY_JOBS: {JOB_ID: {constants.KEY_STATUS: constants.STATUS_QUEUED}},
    }
    text = rendered(inline_report(legacy))
    assert "Code Search Local — online" in text
    assert constants.TUI_LABEL_ONLINE in text and constants.TUI_LABEL_YES in text
    assert "0 / " + constants.TUI_MISSING_VALUE in text
    assert constants.TUI_MISSING_VALUE + " (0/0)" in text
    stopped = {constants.KEY_SHARED: {constants.KEY_MODEL_RESIDENT: False}}
    assert constants.TUI_LABEL_NO in rendered(summary_panel(stopped))


async def test_live_refresh_details_toggle_and_subtitle(tmp_path):
    data = full_snapshot(tmp_path)
    fresh = {**data, constants.KEY_ONLINE: True, constants.KEY_SEQUENCE: 7}
    fetch = AsyncMock(return_value=fresh)
    app = StatsApp(data, Feed(), fetch=fetch)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
        assert app.sub_title.startswith(constants.TUI_LABEL_OFFLINE)
        await pilot.press(constants.TUI_KEY_REFRESH)
        await app.workers.wait_for_complete()
        fetch.assert_awaited_once()
        assert app.snapshot is fresh
        assert app.sub_title.startswith(constants.TUI_LABEL_ONLINE)
        summary = app.get_widget_by_id(constants.TUI_SUMMARY_WIDGET_ID).content
        assert constants.TUI_LABEL_ONLINE in rendered(summary)
        details = app.get_widget_by_id(constants.REPORT_WIDGET_ID)
        await pilot.press(constants.TUI_KEY_TOGGLE_DETAILS)
        assert not details.display
        await pilot.press(constants.TUI_KEY_TOGGLE_DETAILS)
        assert details.display


@pytest.mark.parametrize("key", [constants.TUI_KEY_QUIT, constants.TUI_KEY_ESCAPE])
async def test_live_quit_keys(key):
    app = StatsApp({}, Feed())
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.press(key)
        await pilot.pause()
        assert app.return_code == 0


@pytest.mark.parametrize(
    "error", [sqlite3.OperationalError("database is locked"), MALFORMED_RESPONSE]
)
async def test_refresh_errors_notify(error):
    fetch = AsyncMock(side_effect=error)
    app = StatsApp({}, Feed({constants.KEY_ONLINE: True}), fetch)
    notes = recorded_notifications(app)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await app.workers.wait_for_complete()
        assert app.sub_title.startswith(constants.TUI_LABEL_ONLINE)
        await pilot.press(constants.TUI_KEY_REFRESH)
        await app.workers.wait_for_complete()
        assert app.is_running
    assert notes == [(str(error), constants.KEY_ERROR, False)]


async def test_follow_recovers_from_a_malformed_response(monkeypatch):
    fresh = {constants.KEY_ONLINE: True, constants.KEY_SEQUENCE: 3}
    feed = Feed(fresh, errors=[MALFORMED_RESPONSE])
    app = StatsApp({constants.KEY_ONLINE: True}, feed)
    notes = recorded_notifications(app)
    monkeypatch.setattr(tui, "sleep", AsyncMock())
    async with app.run_test(size=TERMINAL_SIZE):
        await app.workers.wait_for_complete()
        assert app.snapshot is fresh
    assert notes == [(str(MALFORMED_RESPONSE), constants.KEY_ERROR, False)]
    assert feed.subscriptions == 2


async def test_follow_recovers_with_capped_backoff(monkeypatch):
    # Enough failures to reach the cap and then stay at it.
    growth = math.ceil(
        math.log(
            constants.TUI_FOLLOW_RETRY_MAX_SECONDS / constants.TUI_FOLLOW_RETRY_INITIAL_SECONDS,
            constants.TUI_FOLLOW_RETRY_MULTIPLIER,
        )
    )
    errors = [
        kind(f"failure {number}") for number, kind in zip(range(growth + 2), cycle(FOLLOW_ERRORS))
    ]
    fresh = {constants.KEY_ONLINE: True, constants.KEY_SEQUENCE: 9}
    feed = Feed(fresh, errors=errors)
    app = StatsApp({constants.KEY_ONLINE: True}, feed)
    notes = recorded_notifications(app)
    delays, subtitles = [], []

    async def backoff(delay):
        delays.append(delay)
        subtitles.append(app.sub_title)

    monkeypatch.setattr(tui, "sleep", backoff)
    async with app.run_test(size=TERMINAL_SIZE):
        await app.workers.wait_for_complete()
        assert app.snapshot is fresh
        assert app.sub_title.startswith(constants.TUI_LABEL_ONLINE)
    assert notes == [(str(error), constants.KEY_ERROR, False) for error in errors]
    assert feed.subscriptions == len(errors) + 1
    assert all(subtitle.startswith(constants.TUI_LABEL_OFFLINE) for subtitle in subtitles)
    assert delays[0] == constants.TUI_FOLLOW_RETRY_INITIAL_SECONDS
    assert all(
        later
        == min(
            earlier * constants.TUI_FOLLOW_RETRY_MULTIPLIER, constants.TUI_FOLLOW_RETRY_MAX_SECONDS
        )
        for earlier, later in pairwise(delays)
    )
    assert delays[-2:] == [constants.TUI_FOLLOW_RETRY_MAX_SECONDS] * 2


async def test_quit_while_backing_off_cancels_follower(monkeypatch):
    waiting = asyncio.Event()

    async def backoff(delay):
        waiting.set()
        await asyncio.sleep(BACKOFF_HOLD_SECONDS)

    monkeypatch.setattr(tui, "sleep", backoff)
    app = StatsApp({}, Feed(errors=[OSError("socket closed")]))
    recorded_notifications(app)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await waiting.wait()
        (follower,) = app.workers
        await pilot.press(constants.TUI_KEY_QUIT)
        await pilot.pause()
    assert app.return_code == 0
    assert follower.state is WorkerState.CANCELLED


async def test_refresh_is_unavailable_without_fetch():
    app = StatsApp({}, Feed())
    assert not app.check_action(constants.TUI_ACTION_REFRESH, ())
    assert app.check_action(constants.TUI_ACTION_TOGGLE_DETAILS, ())
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.press(constants.TUI_KEY_REFRESH)
        await app.workers.wait_for_complete()
        assert app.snapshot == {}


async def test_inline_mode_exits_with_every_section(tmp_path):
    data = full_snapshot(tmp_path)
    app = StatsApp(data)
    messages = []
    exit_app = app.exit
    app.exit = lambda message: messages.append(message) or exit_app(message=message)
    async with app.run_test(size=TERMINAL_SIZE) as pilot:
        await pilot.pause()
    text = rendered(messages[0])
    assert "Summary" in text and PATH_HIT in text and constants.KEY_TOP_PATHS in text


def test_cli_passes_fetch_and_project(tmp_path, monkeypatch):
    project = tmp_path / constants.KEY_PROJECT
    project.mkdir()
    stats = AsyncMock(return_value={constants.KEY_ONLINE: True})
    apps = []
    monkeypatch.setattr(Client, constants.KEY_STATS, stats)
    monkeypatch.setattr(StatsApp, "run", lambda app, **options: apps.append((app, options)))
    for args in (
        [constants.KEY_STATS],
        [constants.KEY_STATS, constants.OPTION_LIVE],
        [constants.KEY_STATS, constants.OPTION_PROJECT, str(project)],
    ):
        invoke_on_terminal(monkeypatch, main, args)
    (inline, inline_options), (live, live_options), (filtered, _) = apps
    assert inline.subscriber is None and inline.fetch is not None
    assert inline_options[test_constants.KEY_INLINE]
    assert not live_options[test_constants.KEY_INLINE]
    assert live.subscriber.fetch is live.fetch
    assert stats.await_args_list[-1].args == (canonical_project(project),)
    assert filtered.subscriber is None


@pytest.mark.parametrize("columns", [None, PLAIN_REPORT_COLUMNS])
def test_cli_writes_plain_report_without_terminal(tmp_path, monkeypatch, columns):
    data = full_snapshot(tmp_path)
    monkeypatch.setattr(Client, constants.KEY_STATS, AsyncMock(return_value=data))
    monkeypatch.setattr(StatsApp, "run", lambda app, **options: pytest.fail("Textual ran"))
    # No standard stream is a terminal, so only COLUMNS can set the width.
    monkeypatch.setattr(sys, "__stdout__", io.StringIO())
    if columns is None:
        monkeypatch.delenv(test_constants.ENV_COLUMNS, raising=False)
    else:
        monkeypatch.setenv(test_constants.ENV_COLUMNS, str(columns))
    result = CliRunner().invoke(main, [constants.KEY_STATS])
    assert result.exit_code == 0, result.output
    assert ESCAPE not in result.stdout
    for expected in (*SECTION_TITLES, PATH_HIT, JOB_ID[: constants.TUI_JOB_ID_CHARACTERS]):
        assert expected in result.stdout
    width = columns or constants.TUI_PLAIN_REPORT_FALLBACK_SIZE[0]
    assert max(map(len, result.stdout.splitlines())) == width
    assert not result.stderr


def test_cli_live_requires_terminal(monkeypatch):
    stats = AsyncMock(return_value={constants.KEY_ONLINE: True})
    monkeypatch.setattr(Client, constants.KEY_STATS, stats)
    result = CliRunner().invoke(main, [constants.KEY_STATS, constants.OPTION_LIVE])
    assert result.exit_code == click.UsageError.exit_code
    assert "--live requires a terminal on stdout" in result.stderr
    stats.assert_not_awaited()
