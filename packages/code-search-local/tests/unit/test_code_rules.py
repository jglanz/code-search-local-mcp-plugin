"""Executable contracts for the operational-literal scope and duplication thresholds."""

import pytest

from scripts.check_code_rules import operational_literals, qualifying_duplicates

EXAMPLE_FILENAME = "example.py"
COPY_FILENAME = "copy_{index}.py"
LITERAL_CASES = (
    ('"""Docstrings are allowed."""\n', False),
    ('raise ValueError("A useful explanation")\n', False),
    ('KEY_STATUS = "status"\nobj[KEY_STATUS]\n', False),
    ('obj["status"]\n', True),
    ('obj.get("status")\n', True),
    ('data = {"status": result}\n', True),
    ('root / "config.json"\n', True),
    ("time.sleep(0.5)\n", True),
    ("call(timeout=30)\n", True),
    ('@click.option("--project")\ndef run(): pass\n', True),
    ('value = "ordinary sample prose"\n', False),
)
CASE_ARGUMENTS = ("source", "violates")
DUPLICATE_ARGUMENTS = ("lines", "copies", "violates")
DUPLICATE_CASES = ((5, 2, False), (5, 3, True), (8, 2, True), (4, 3, False))
DUPLICATE_FUNCTION_HEADER = "def example():\n"
DUPLICATE_STATEMENTS = (
    "    first = load()\n",
    "    second = transform(first)\n",
    "    third = validate(second)\n",
    "    fourth = serialize(third)\n",
    "    fifth = persist(fourth)\n",
    "    sixth = notify(fifth)\n",
    "    seventh = finish(sixth)\n",
    "    return seventh\n",
)


@pytest.mark.parametrize(CASE_ARGUMENTS, LITERAL_CASES)
def test_operational_literal_scope(tmp_path, source, violates):
    path = tmp_path / EXAMPLE_FILENAME
    path.write_text(source)
    assert bool(operational_literals(path)) is violates


@pytest.mark.parametrize(DUPLICATE_ARGUMENTS, DUPLICATE_CASES)
def test_inclusive_duplication_thresholds(tmp_path, lines, copies, violates):
    paths = []
    for index in range(copies):
        path = tmp_path / COPY_FILENAME.format(index=index)
        path.write_text(DUPLICATE_FUNCTION_HEADER + "".join(DUPLICATE_STATEMENTS[:lines]))
        paths.append(path)
    assert bool(qualifying_duplicates(paths)) is violates


def test_same_file_duplicates_are_detected(tmp_path):
    path = tmp_path / EXAMPLE_FILENAME
    path.write_text(DUPLICATE_FUNCTION_HEADER + "".join(DUPLICATE_STATEMENTS) * 2)
    assert qualifying_duplicates([path])
