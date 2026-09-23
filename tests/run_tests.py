"""Run the declared test suite using pytest's own argument parser."""

import sys

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:]))
