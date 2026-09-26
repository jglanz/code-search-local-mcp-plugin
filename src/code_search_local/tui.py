"""Textual reports share the exact same snapshot as JSON output."""

import json

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from code_search_local import constants


def report(snapshot):
    table = Table(
        title="Code Search Local — "
        + (constants.KEY_ONLINE if snapshot.get(constants.KEY_ONLINE) else "offline snapshot"),
        expand=True,
    )
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


class StatsApp(App):
    TITLE = "Code Search Local"
    CSS = "#report { height: auto; padding: 0 1; }"
    BINDINGS = [("q", "quit", "Quit"), ("escape", "quit", "Quit")]

    def __init__(self, snapshot, subscriber=None):
        super().__init__()
        self.snapshot, self.subscriber = snapshot, subscriber

    def compose(self) -> ComposeResult:
        if self.subscriber:
            yield Header()
        with VerticalScroll():
            yield Static(report(self.snapshot), id=constants.REPORT_WIDGET_ID)
        if self.subscriber:
            yield Footer()

    async def on_mount(self):
        if self.subscriber:
            self.run_worker(self.follow(), exclusive=True)
        else:
            self.call_after_refresh(lambda: self.exit(message=report(self.snapshot)))

    async def follow(self):
        try:
            async for snapshot in self.subscriber.snapshots():
                self.snapshot = snapshot
                self.query_one("#report", Static).update(report(snapshot))
        except (OSError, RuntimeError) as error:
            self.notify(
                str(error),
                severity=constants.KEY_ERROR,
                timeout=constants.TUI_ERROR_TIMEOUT_SECONDS,
            )
