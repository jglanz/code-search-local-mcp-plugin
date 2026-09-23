"""Textual reports share the exact same snapshot as JSON output."""

import json

from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static


def report(snapshot):
    table = Table(
        title="Code Search Local — " + ("online" if snapshot.get("online") else "offline snapshot"),
        expand=True,
    )
    table.add_column("Scope", style="cyan", overflow="fold")
    table.add_column("Statistic", style="bold", overflow="fold")
    table.add_column("Value", overflow="fold")

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
        "Service",
        {
            key: value
            for key, value in snapshot.items()
            if key not in ("projects", "jobs", "shared")
        },
    )
    rows("Shared model", snapshot.get("shared", {}))
    for project, stats in snapshot.get("projects", {}).items():
        rows(project, stats)
    for job, stats in snapshot.get("jobs", {}).items():
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
            yield Static(report(self.snapshot), id="report")
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
            self.notify(str(error), severity="error", timeout=10)
