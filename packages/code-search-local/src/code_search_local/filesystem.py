"""Shared default exclusions for file discovery and Merkle snapshots."""

DEFAULT_IGNORED_DIRECTORIES = frozenset(
    {
        ".svelte-kit",
        ".mvn",
        ".venv",
        ".gradle",
        ".tox",
        ".next",
        ".terraform",
        ".yarn",
        ".hg",
        "target",
        ".nuxt",
        "bin",
        "build",
        ".direnv",
        ".ipynb_checkpoints",
        ".env",
        ".mypy_cache",
        ".coverage",
        "obj",
        ".vscode",
        ".vercel",
        ".cache",
        ".pnpm-store",
        "out",
        ".angular",
        ".astro",
        ".serverless",
        "env",
        ".pytest_cache",
        "public",
        "__pycache__",
        "coverage",
        ".idea",
        ".docusaurus",
        ".git",
        "venv",
        ".vite",
        ".pytype",
        ".ruff_cache",
        ".svn",
        ".nyc_output",
        ".parcel-cache",
        ".venvs",
        ".turbo",
        "dist",
        "node_modules",
    }
)
DEFAULT_IGNORED_FILES = frozenset(
    {"compile_commands.json", "vcpkg", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"}
)


def default_ignore_patterns(*, include_files=False):
    """Return a fresh set so callers can customize it without changing defaults."""
    patterns = set(DEFAULT_IGNORED_DIRECTORIES)
    if include_files:
        patterns.update(DEFAULT_IGNORED_FILES)
    return patterns
