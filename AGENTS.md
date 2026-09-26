# Repository instructions

Read [CLAUDE.md](CLAUDE.md) for the repository's architecture, environment, testing
and service-management guidance.

## Mandatory rules

- [Named constants and duplicated-code extraction](.agents/rules/constants-and-duplication.md):
  operational literals must be defined as named constants (docstrings and prose may remain inline). Extract blocks of 5+ code lines
  at 3+ total occurrences, or 8+ code lines at 2+ total occurrences, into a shared
  method or function. Read the rule for its complete scope and counting criteria.
