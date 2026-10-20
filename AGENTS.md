# Repository instructions

Read [CLAUDE.md](CLAUDE.md) for the repository's architecture, environment, testing
and service-management guidance. The repository is a pnpm monorepo: the Python service
(`packages/code-search-local`, run through Hatch), the API contract and its generated
TypeScript schemas (`packages/code-search-local-api`), and the web dashboard
(`packages/code-search-local-webapp`, run through pnpm).

## Mandatory rules

- [Named constants and duplicated-code extraction](.agents/rules/constants-and-duplication.md):
  operational literals must be defined as named constants (docstrings and prose may remain inline). Extract blocks of 5+ code lines
  at 3+ total occurrences, or 8+ code lines at 2+ total occurrences, into a shared
  method or function. Read the rule for its complete scope and counting criteria.
  It applies to Python and TypeScript.
- [TypeScript style guide](STYLE.md): binds every TypeScript package and workspace script.
- API models are defined only in `packages/code-search-local-api/openapi.yaml`. Never
  hand-write or commit generated models; regenerate them with `hatch run generate` (Python)
  and `pnpm run generate` or `pnpm compile` (TypeScript).
