"""Check operational literals and repeated blocks without executing project code.

Pylint supplies the duplicate finder. The AST pass covers dictionary keys, path
operations, CLI options, environment names, regexes and explicit timing budgets.
Review still checks semantic duplication and contracts outside these syntax forms.
"""

import ast
import io
from collections import defaultdict
from itertools import chain
from pathlib import Path

import click
from pylint.checkers.symilar import Symilar

SOURCE_ROOTS = ("src", "scripts", "tests")
INPUT_FIXTURE_DIRECTORIES = frozenset({"test_data", "fixtures"})
PYTHON_GLOB = "*.py"
CONSTANTS_FILENAME = "constants.py"
KEY_METHODS = frozenset({"get", "pop", "setdefault"})
PATH_METHODS = frozenset({"Path", "glob", "rglob", "with_name", "with_suffix"})
ENV_METHODS = frozenset({"setenv", "delenv"})
REGEX_METHODS = frozenset({"compile", "search", "match", "fullmatch", "sub", "findall"})
REGEX_MODULE = "re"
CLI_OPTION_METHOD = "option"
TIME_METHODS = frozenset({"sleep", "wait", "wait_for", "join"})
TIME_KEYWORDS = frozenset({"timeout", "connect", "sock_read", "delay"})
REPEATED_BLOCK_LINES = 5
REPEATED_BLOCK_OCCURRENCES = 3
PAIRED_BLOCK_LINES = 8
PAIRED_BLOCK_OCCURRENCES = 2
PYLINT_MINIMUM_LINES = REPEATED_BLOCK_LINES - 1  # Pylint compares strictly greater-than.
EXIT_FAILURE = 1


def source_files(root):
    return sorted(
        path
        for directory in SOURCE_ROOTS
        for path in (root / directory).rglob(PYTHON_GLOB)
        if not INPUT_FIXTURE_DIRECTORIES.intersection(path.relative_to(root).parts)
    )


def is_constant_definition(node, parents):
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if all(isinstance(target, ast.Name) and target.id.isupper() for target in targets):
                return True
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
    return False


def called_name(call):
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return call.func.id if isinstance(call.func, ast.Name) else None


def literal_reason(node, parent):
    if isinstance(node.value, str) and node.value:
        if isinstance(parent, ast.Dict) and node in parent.keys:
            return "dictionary key"
        if isinstance(parent, ast.Subscript) and parent.slice is node:
            return "dictionary key"
        if isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div):
            return "path component"
        if isinstance(parent, ast.Call) and parent.args and parent.args[0] is node:
            name = called_name(parent)
            if name in KEY_METHODS:
                return "dictionary key"
            if name in PATH_METHODS:
                return "path or glob"
            if name in ENV_METHODS:
                return "environment name"
            if name == CLI_OPTION_METHOD:
                return "CLI option"
            if (
                name in REGEX_METHODS
                and isinstance(parent.func, ast.Attribute)
                and isinstance(parent.func.value, ast.Name)
                and parent.func.value.id == REGEX_MODULE
            ):
                return "regular expression"
    if type(node.value) in (int, float):
        if isinstance(parent, ast.keyword) and parent.arg in TIME_KEYWORDS:
            return "timing budget"
        if isinstance(parent, ast.Call) and called_name(parent) in TIME_METHODS:
            return "timing budget"
    return None


def operational_literals(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    return [
        (node.lineno, reason)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and not is_constant_definition(node, parents)
        and (reason := literal_reason(node, parents.get(node)))
    ]


def qualifying_duplicates(files):
    finder = Symilar(
        min_lines=PYLINT_MINIMUM_LINES,
        ignore_comments=True,
        ignore_docstrings=True,
        ignore_imports=True,
        ignore_signatures=True,
    )
    for path in files:
        if path.name != CONSTANTS_FILENAME:
            finder.append_stream(str(path), io.StringIO(path.read_text()))
    # Pylint's display aggregation keeps pairs. Merge shared occurrences so three
    # copies of a five-line block also meet our rule, including within one file.
    groups = defaultdict(list)
    matches = chain(
        finder._iter_sims(),
        *(finder._find_common(lineset, lineset) for lineset in finder.linesets),
    )
    for match in matches:
        left = (match.fst_lset, match.fst_file_start, match.fst_file_end)
        right = (match.snd_lset, match.snd_file_start, match.snd_file_end)
        if left == right:
            continue
        if left[0] is right[0] and max(left[1], right[1]) < min(left[2], right[2]):
            continue
        occurrences = {left, right}
        distinct = []
        for previous in groups[match.cmn_lines_nb]:
            if previous & occurrences:
                occurrences.update(previous)
            else:
                distinct.append(previous)
        groups[match.cmn_lines_nb] = [*distinct, occurrences]
    return [
        (lines, occurrences)
        for lines, matches in groups.items()
        for occurrences in matches
        if lines >= PAIRED_BLOCK_LINES
        and len(occurrences) >= PAIRED_BLOCK_OCCURRENCES
        or lines >= REPEATED_BLOCK_LINES
        and len(occurrences) >= REPEATED_BLOCK_OCCURRENCES
    ]


@click.command()
def main():
    """Audit application code, scripts and tests; parser input fixtures are data."""
    root = Path(__file__).resolve().parent.parent
    files = source_files(root)
    violations = []
    for path in files:
        violations.extend(
            f"{path.relative_to(root)}:{line}: name this {reason} with a constant"
            for line, reason in operational_literals(path)
        )
    for lines, occurrences in qualifying_duplicates(files):
        locations = ", ".join(f"{item.name}:{start + 1}" for item, start, _ in sorted(occurrences))
        violations.append(f"{lines} duplicated lines: {locations}")
    for violation in violations:
        click.echo(violation, err=True)
    if violations:
        raise SystemExit(EXIT_FAILURE)
    click.echo(f"Operational-literal and duplicate-block checks passed ({len(files)} files).")


if __name__ == "__main__":
    main()
