# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved

"""
app/ingestion/language_registry.py
----------------------------------
Single source of truth for supported source-file extensions and languages.

Imported by file_filter.py, tree_sitter_parser.py, and query_expansion heuristics
so allowlists cannot drift out of sync across modules.
"""
from __future__ import annotations

# Extension → tree-sitter / parser language id
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".txt": "text",
    ".sh": "bash",
    ".dockerfile": "dockerfile",
    ".ps1": "powershell",
    ".bat": "batch",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "env",
}

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(EXTENSION_TO_LANGUAGE.keys())

# Extensions skipped by query-expansion heuristics (broader than ingest filter).
QUERY_EXPANSION_SKIP_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".go", ".java", ".rs", ".md", ".json",
})


def language_for_path(path: str) -> str | None:
    """Return parser language for a file path, or None if unsupported."""
    from pathlib import Path

    suffix = Path(path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)
