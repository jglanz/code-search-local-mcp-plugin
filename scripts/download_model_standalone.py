"""Compatibility entry point; use code-search-local directly for new integrations."""

import sys

from code_search_local.cli import main

if __name__ == "__main__":
    main(args=["warmup", *sys.argv[1:]])
