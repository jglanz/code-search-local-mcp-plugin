"""Enforce independent line and branch thresholds from pyproject.toml."""

import json
import tomllib
from pathlib import Path

import click


@click.command()
@click.argument("report", type=click.Path(exists=True, path_type=Path), default="coverage.json")
def main(report):
    policy = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())[
        "tool"
    ]["code-search-local"]["coverage"]
    totals = json.loads(report.read_text())["totals"]
    failed = False
    for kind, covered, total in [
        ("line", "covered_lines", "num_statements"),
        ("branch", "covered_branches", "num_branches"),
    ]:
        percent = 100 * totals[covered] / totals[total] if totals[total] else 100
        click.echo(f"{kind}: {percent:.2f}% (required {policy[kind]}%)")
        failed |= percent < policy[kind]
    if failed:
        raise click.ClickException("Coverage is below the required floor")


if __name__ == "__main__":
    main()
