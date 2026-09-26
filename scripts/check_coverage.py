"""Enforce independent line and branch thresholds from pyproject.toml."""

import json
import tomllib
from pathlib import Path

import click

from code_search_local import constants

PERCENT_SCALE = 100
KEY_COVERAGE = "coverage"
KEY_TOTALS = "totals"
REPORT_ARGUMENT = "report"
DEFAULT_REPORT_FILENAME = "coverage.json"
COVERAGE_FIELDS = (
    ("line", "covered_lines", "num_statements"),
    ("branch", "covered_branches", "num_branches"),
)


@click.command()
@click.argument(
    REPORT_ARGUMENT,
    type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_REPORT_FILENAME,
)
def main(report):
    policy = tomllib.loads(
        (Path(__file__).resolve().parents[1] / constants.PATH_PYPROJECT_TOML).read_text()
    )[constants.KEY_TOOL][constants.APPLICATION_NAME][KEY_COVERAGE]
    totals = json.loads(report.read_text())[KEY_TOTALS]
    failed = False
    for kind, covered, total in COVERAGE_FIELDS:
        percent = (
            PERCENT_SCALE * totals[covered] / totals[total] if totals[total] else PERCENT_SCALE
        )
        click.echo(f"{kind}: {percent:.2f}% (required {policy[kind]}%)")
        failed |= percent < policy[kind]
    if failed:
        raise click.ClickException("Coverage is below the required floor")


if __name__ == "__main__":
    main()
