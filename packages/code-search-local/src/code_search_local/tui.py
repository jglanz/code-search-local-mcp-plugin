"""Textual reports share the exact same snapshot as JSON output.

Every renderer tolerates snapshots that predate a key (older or offline state), an empty
service and a shared section without a loaded model: absent values render as a placeholder.
"""

import json
import shutil
import sqlite3
from asyncio import sleep
from datetime import datetime
from itertools import chain, zip_longest

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from code_search_local import constants
from code_search_local.storage import hit_ratio

# (label, hits key, misses key) of the search-quality rates, in display order.
RATES = (
    ("Relevance", constants.KEY_SEARCH_RELEVANCE_HITS, constants.KEY_SEARCH_RELEVANCE_MISSES),
    ("Non-empty results", constants.KEY_SEARCH_RESULT_HITS, constants.KEY_SEARCH_RESULT_MISSES),
    ("Query cache", constants.KEY_QUERY_CACHE_HITS, constants.KEY_QUERY_CACHE_MISSES),
)
TOTALS = (
    ("Projects", constants.KEY_PROJECTS),
    ("Files", constants.KEY_FILES),
    ("Chunks", constants.KEY_CHUNKS),
    ("Searches", constants.KEY_SEARCHES),
    ("Search failures", constants.KEY_SEARCH_FAILURES),
)
# Column (header, right-aligned) pairs of each section table.
PROJECT_COLUMNS = (
    ("Project", False),
    ("Files", True),
    ("Chunks", True),
    ("Last indexed", False),
    ("Searches", True),
    *((label, True) for label, _, _ in RATES),
    ("Active jobs", True),
)
TOP_PATH_COLUMNS = (
    ("Project", False),
    ("Path", False),
    ("Appearances", True),
    ("Hits", True),
    ("Misses", True),
    ("Hit ratio", True),
    ("Top-ranked", True),
    ("Best score", True),
)
JOB_COLUMNS = (
    ("Job", False),
    ("Project", False),
    ("Status", False),
    ("Files", True),
    ("Progress", False),
    ("Duration", True),
    ("Error", False),
)
ACTIVE_JOB_STATUSES = frozenset({constants.STATUS_QUEUED, constants.STATUS_RUNNING})
JOB_STATUS_STYLES = {
    constants.STATUS_QUEUED: constants.TUI_STYLE_YELLOW,
    constants.STATUS_RUNNING: constants.TUI_STYLE_YELLOW,
    constants.STATUS_SUCCEEDED: constants.TUI_STYLE_GREEN,
    constants.STATUS_FAILED: constants.TUI_STYLE_RED,
    constants.STATUS_CANCELLED: constants.TUI_STYLE_DIM,
    constants.STATUS_INTERRUPTED: constants.TUI_STYLE_DIM,
}
RESIDENT_LABELS = {True: constants.TUI_LABEL_YES, False: constants.TUI_LABEL_NO}
# Fetching falls back to the offline database, which reports these failures. A response
# body that is not valid JSON raises ValueError.
FETCH_ERRORS = (OSError, RuntimeError, KeyError, ValueError, sqlite3.Error)


def or_missing(value):
    return constants.TUI_MISSING_VALUE if value is None else value


def cell(value):
    """Plain values become Text, so paths and errors are never parsed as markup."""
    return Text(str(value)) if isinstance(value, (str, int, float)) else value


def joined(separator, *values):
    """Join the present values, or the placeholder when none is present."""
    return separator.join(str(value) for value in values if value) or constants.TUI_MISSING_VALUE


def percent(hits, misses):
    """Hit rate as a percentage; the placeholder before any hit or miss."""
    if not hits + misses:
        return constants.TUI_MISSING_VALUE
    return f"{hit_ratio(hits, misses):.{constants.TUI_PERCENT_DECIMALS}%}"


def rate(counters, hits_key, misses_key):
    hits, misses = counters.get(hits_key, 0), counters.get(misses_key, 0)
    return f"{percent(hits, misses)} ({hits}/{misses})"


def decimal(value, places, unit=""):
    """Fixed-point number with an optional unit; the placeholder when absent."""
    if value is None:
        return constants.TUI_MISSING_VALUE
    return f"{value:.{places}f}{unit}"


def local_time(value):
    """Show an ISO timestamp in local time; unparseable values pass through unchanged."""
    if not value:
        return constants.TUI_MISSING_VALUE
    try:
        return datetime.fromisoformat(value).astimezone().strftime(constants.TUI_DATETIME_FORMAT)
    except (TypeError, ValueError):
        return str(value)


def connection(snapshot):
    if snapshot.get(constants.KEY_ONLINE):
        return Text(constants.TUI_LABEL_ONLINE, style=constants.TUI_STYLE_GREEN)
    return Text(constants.TUI_LABEL_OFFLINE + " snapshot", style=constants.TUI_STYLE_RED)


def subtitle(snapshot):
    """Connection state and the local time at which this snapshot was shown."""
    return f"{connection(snapshot).plain} · updated " + datetime.now().strftime(
        constants.TUI_TIME_FORMAT
    )


def new_table(title, columns, sections, empty):
    """Build a section table; each row group in ``sections`` ends with a rule."""
    table = Table(title=title, expand=True, caption=None if any(sections) else empty)
    for header, numeric in columns:
        table.add_column(
            header,
            justify=constants.TUI_JUSTIFY_RIGHT if numeric else constants.TUI_JUSTIFY_LEFT,
            overflow=constants.TUI_CELL_OVERFLOW,
        )
    for rows in sections:
        for index, row in enumerate(rows):
            table.add_row(*map(cell, row), end_section=index == len(rows) - 1)
    return table


def summary_panel(snapshot):
    """Service identity, model placement, threshold, totals and the three hit rates."""
    shared = snapshot.get(constants.KEY_SHARED) or {}
    model = shared.get(constants.KEY_MODEL) or {}
    totals = snapshot.get(constants.KEY_TOTALS) or {}
    resident = shared.get(constants.KEY_MODEL_RESIDENT)
    service = (
        ("Connection", connection(snapshot)),
        ("Daemon", or_missing(snapshot.get(constants.KEY_DAEMON_ID))),
        ("Started", local_time(snapshot.get(constants.KEY_STARTED_AT))),
        (
            "Model",
            joined(" @ ", model.get(constants.KEY_MODEL), model.get(constants.KEY_REVISION)),
        ),
        (
            "Backend / device",
            joined(" / ", model.get(constants.KEY_BACKEND), model.get(constants.KEY_DEVICE)),
        ),
        ("Model resident", RESIDENT_LABELS.get(resident, constants.TUI_MISSING_VALUE)),
        (
            "Search hit threshold",
            decimal(shared.get(constants.KEY_SEARCH_HIT_MIN_SCORE), constants.TUI_SCORE_DECIMALS),
        ),
    )
    statistics = (
        *((label, or_missing(totals.get(key))) for label, key in TOTALS),
        *((label + " hit rate", rate(totals, hits, misses)) for label, hits, misses in RATES),
    )
    grid = Table.grid(padding=constants.TUI_GRID_PADDING)
    for style in (constants.TUI_STYLE_BOLD, None) * 2:
        grid.add_column(style=style)
    for left, right in zip_longest(service, statistics, fillvalue=("", "")):
        grid.add_row(*map(cell, chain(left, right)))
    return Panel(grid, title="Summary")


def projects_table(snapshot):
    jobs = (snapshot.get(constants.KEY_JOBS) or {}).values()
    rows = [
        (
            root,
            or_missing(stats.get(constants.KEY_FILES)),
            or_missing(stats.get(constants.KEY_CHUNKS)),
            local_time(stats.get(constants.KEY_INDEXED_AT)),
            or_missing(stats.get(constants.KEY_SEARCHES)),
            *(rate(stats, hits, misses) for _, hits, misses in RATES),
            sum(
                job.get(constants.KEY_PROJECT_PATH) == root
                and job.get(constants.KEY_STATUS) in ACTIVE_JOB_STATUSES
                for job in jobs
            ),
        )
        for root, stats in (snapshot.get(constants.KEY_PROJECTS) or {}).items()
    ]
    return new_table(
        "Projects — hit rate % (hits/misses)", PROJECT_COLUMNS, [rows], "No projects registered"
    )


def top_path_row(project, row):
    appearances = row.get(constants.KEY_APPEARANCES, 0)
    hits = row.get(constants.KEY_HITS, 0)
    misses = row.get(constants.KEY_MISSES, appearances - hits)
    return (
        project,
        or_missing(row.get(constants.KEY_PATH)),
        appearances,
        hits,
        misses,
        percent(hits, misses),
        row.get(constants.KEY_TOP_RANKED, 0),
        decimal(row.get(constants.KEY_BEST_SCORE), constants.TUI_SCORE_DECIMALS),
    )


def top_paths_table(snapshot):
    """The most often returned paths of each project; the project names its first row."""
    sections = [
        [
            top_path_row(root if index == 0 else "", row)
            for index, row in enumerate(stats.get(constants.KEY_TOP_PATHS) or [])
        ]
        for root, stats in (snapshot.get(constants.KEY_PROJECTS) or {}).items()
    ]
    return new_table("Top paths", TOP_PATH_COLUMNS, sections, "No search results recorded")


def progress(processed, total):
    """Bar and percentage; the placeholder until the job knows its file count."""
    if not total:
        return constants.TUI_MISSING_VALUE
    bar = Table.grid(padding=constants.TUI_GRID_PADDING)
    bar.add_row(
        ProgressBar(total=total, completed=processed, width=constants.TUI_PROGRESS_BAR_WIDTH),
        Text(percent(processed, total - processed)),
    )
    return bar


def job_row(job_id, job):
    processed = job.get(constants.KEY_FILES_PROCESSED, 0)
    total = job.get(constants.KEY_FILES_TOTAL)
    status = job.get(constants.KEY_STATUS) or constants.TUI_MISSING_VALUE
    error = Text(job.get(constants.KEY_ERROR) or constants.TUI_MISSING_VALUE)
    error.truncate(constants.TUI_ERROR_CHARACTERS, overflow=constants.TUI_TRUNCATE_OVERFLOW)
    return (
        job.get(constants.KEY_JOB_ID, job_id)[: constants.TUI_JOB_ID_CHARACTERS],
        or_missing(job.get(constants.KEY_PROJECT_PATH)),
        Text(status, style=JOB_STATUS_STYLES.get(status, "")),
        f"{processed} / {or_missing(total)}",
        progress(processed, total),
        decimal(job.get(constants.KEY_DURATION_SECONDS), constants.TUI_DURATION_DECIMALS, " s"),
        error,
    )


def jobs_table(snapshot):
    """Newest jobs first, bounded so a long-lived service keeps the view readable."""
    jobs = sorted(
        (snapshot.get(constants.KEY_JOBS) or {}).items(),
        key=lambda item: item[1].get(constants.KEY_QUEUED_AT) or "",
        reverse=True,
    )
    shown = jobs[: constants.TUI_JOBS_LIMIT]
    table = new_table(
        "Index jobs", JOB_COLUMNS, [[job_row(*item) for item in shown]], "No index jobs"
    )
    if len(shown) < len(jobs):
        table.caption = f"Newest {len(shown)} of {len(jobs)} jobs; details list every job"
    return table


def report(snapshot):
    table = Table(title="Code Search Local — " + connection(snapshot).plain, expand=True)
    table.add_column(
        constants.TOKEN_SCOPE, style=constants.TUI_STYLE_CYAN, overflow=constants.TUI_CELL_OVERFLOW
    )
    table.add_column(
        constants.TOKEN_STATISTIC,
        style=constants.TUI_STYLE_BOLD,
        overflow=constants.TUI_CELL_OVERFLOW,
    )
    table.add_column(constants.TOKEN_VALUE, overflow=constants.TUI_CELL_OVERFLOW)

    def rows(scope, values, prefix=""):
        for key, value in values.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                rows(scope, value, name)
            else:
                rendered = (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, bool)) or value is None
                    else str(value)
                )
                table.add_row(Text(scope), Text(name), Text(rendered))

    rows(
        constants.TOKEN_SERVICE,
        {
            key: value
            for key, value in snapshot.items()
            if key not in (constants.KEY_PROJECTS, constants.KEY_JOBS, constants.KEY_SHARED)
        },
    )
    rows("Shared model", snapshot.get(constants.KEY_SHARED, {}))
    for project, stats in snapshot.get(constants.KEY_PROJECTS, {}).items():
        rows(project, stats)
    for job, stats in snapshot.get(constants.KEY_JOBS, {}).items():
        rows("Job " + job, stats)
    return table


# Widget ID and renderer of each section, top to bottom; the details report comes last.
SECTIONS = (
    (constants.TUI_SUMMARY_WIDGET_ID, summary_panel),
    (constants.TUI_PROJECTS_WIDGET_ID, projects_table),
    (constants.TUI_TOP_PATHS_WIDGET_ID, top_paths_table),
    (constants.TUI_JOBS_WIDGET_ID, jobs_table),
    (constants.REPORT_WIDGET_ID, report),
)


def inline_report(snapshot):
    """Every section, including the complete details, for terminal scrollback."""
    return Group(*(render(snapshot) for _, render in SECTIONS))


def print_report(snapshot, file):
    """Write every section as plain text, for files, pipes and other non-terminals.

    No colour, style or cursor control sequence is written. ``COLUMNS`` sets the width;
    without it, output that is not a terminal uses the named fallback width.
    """
    width = shutil.get_terminal_size(constants.TUI_PLAIN_REPORT_FALLBACK_SIZE).columns
    Console(file=file, width=width, color_system=None).print(inline_report(snapshot))


class StatsApp(App):
    """Inline report without a subscriber; otherwise a live view of subscriber snapshots.

    ``fetch`` is the coroutine function the subscriber uses; ``r`` calls it directly.
    """

    TITLE = "Code Search Local"
    CSS = "Static { height: auto; padding: 0 1; }"
    BINDINGS = [
        Binding(constants.TUI_KEY_QUIT, constants.TUI_ACTION_QUIT, "Quit"),
        Binding(constants.TUI_KEY_ESCAPE, constants.TUI_ACTION_QUIT, "Quit", show=False),
        Binding(constants.TUI_KEY_REFRESH, constants.TUI_ACTION_REFRESH, "Refresh"),
        Binding(constants.TUI_KEY_TOGGLE_DETAILS, constants.TUI_ACTION_TOGGLE_DETAILS, "Details"),
    ]

    def __init__(self, snapshot, subscriber=None, fetch=None):
        super().__init__()
        self.snapshot, self.subscriber, self.fetch = snapshot, subscriber, fetch

    def compose(self) -> ComposeResult:
        if self.subscriber:
            yield Header()
        with VerticalScroll():
            for widget_id, render in SECTIONS:
                yield Static(render(self.snapshot), id=widget_id)
        if self.subscriber:
            yield Footer()

    def check_action(self, action, parameters):
        return action != constants.TUI_ACTION_REFRESH or self.fetch is not None

    async def on_mount(self):
        if self.subscriber:
            self.sub_title = subtitle(self.snapshot)
            self.run_worker(self.follow(), group=constants.TUI_FOLLOW_WORKER_GROUP, exclusive=True)
        else:
            self.call_after_refresh(lambda: self.exit(message=inline_report(self.snapshot)))

    def show(self, snapshot):
        self.snapshot = snapshot
        for widget_id, render in SECTIONS:
            self.get_widget_by_id(widget_id, Static).update(render(snapshot))
        self.sub_title = subtitle(snapshot)

    def notify_error(self, error):
        self.notify(
            str(error),
            severity=constants.KEY_ERROR,
            timeout=constants.TUI_ERROR_TIMEOUT_SECONDS,
            markup=False,
        )

    async def follow(self):
        """Show subscriber snapshots; after a failure, notify, back off and resubscribe.

        Each failed subscription is one notification, and the view stays offline until a
        new subscription yields a snapshot. Quitting cancels the worker, also while it
        waits. A subscription that ends without an error ends following.
        """
        import zmq

        delay = constants.TUI_FOLLOW_RETRY_INITIAL_SECONDS
        while True:
            try:
                async for snapshot in self.subscriber.snapshots():
                    self.show(snapshot)
                    delay = constants.TUI_FOLLOW_RETRY_INITIAL_SECONDS
                return
            except (*FETCH_ERRORS, zmq.ZMQError) as error:
                self.notify_error(error)
                self.show({**self.snapshot, constants.KEY_ONLINE: False})
            await sleep(delay)
            delay = min(
                delay * constants.TUI_FOLLOW_RETRY_MULTIPLIER,
                constants.TUI_FOLLOW_RETRY_MAX_SECONDS,
            )

    async def refresh_now(self):
        try:
            self.show(await self.fetch())
        except FETCH_ERRORS as error:
            self.notify_error(error)

    def action_refresh_now(self):
        self.run_worker(
            self.refresh_now(), group=constants.TUI_REFRESH_WORKER_GROUP, exclusive=True
        )

    def action_toggle_details(self):
        details = self.get_widget_by_id(constants.REPORT_WIDGET_ID)
        details.display = not details.display
