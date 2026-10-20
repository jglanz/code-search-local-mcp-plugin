"""Lazy grammars supplied by the maintained tree-sitter-language-pack."""

from collections.abc import Mapping
from functools import lru_cache

LANGUAGES = {
    "python": "python",
    "javascript": "javascript",
    "jsx": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "svelte": "svelte",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "csharp",
    "markdown": "markdown",
    "solidity": "solidity",
}


@lru_cache(maxsize=len(LANGUAGES))
def language(name):
    from tree_sitter_language_pack import get_language

    return get_language(LANGUAGES[name])


class LanguageMap(Mapping):
    def __getitem__(self, key):
        return language(key)

    def __iter__(self):
        return iter(LANGUAGES)

    def __len__(self):
        return len(LANGUAGES)

    def __contains__(self, key):
        return key in LANGUAGES


def get_availiable_language():
    """Keep the original internal spelling for existing language chunkers."""
    return LanguageMap()


def prefetch_languages():
    from tree_sitter_language_pack import prefetch

    prefetch(list(set(LANGUAGES.values())))
