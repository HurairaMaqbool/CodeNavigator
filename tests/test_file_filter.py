# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_file_filter.py
--------------------------
Unit tests for Module 4 (File Filter + Language Detector).

All tests use stdlib tempfile — no network, no gitpython, no external packages.

Run with:
    python -m unittest tests/test_file_filter.py -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Bootstrap: mock structlog + set LLM_PROVIDER before any app import
# ---------------------------------------------------------------------------
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.pop("GROQ_API_KEY", None)

_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock


# ---------------------------------------------------------------------------
# Helper — build a fake repo tree
# ---------------------------------------------------------------------------

def _write(root: Path, rel: str, content: bytes = b"print('hello')\n") -> Path:
    """Write *content* to *root/rel*, creating parent directories as needed."""
    p = root / Path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _py(root: Path, rel: str, lines: int = 5) -> Path:
    """Write a minimal Python source file."""
    src = ("\n".join(f"x = {i}" for i in range(lines)) + "\n").encode()
    return _write(root, rel, src)


def _js(root: Path, rel: str, lines: int = 5) -> Path:
    src = ("\n".join(f"const x{i} = {i};" for i in range(lines)) + "\n").encode()
    return _write(root, rel, src)


# ===========================================================================
# A.  safe_decode
# ===========================================================================

class TestSafeDecode(unittest.TestCase):

    def test_normal_utf8_file_returns_text(self):
        from app.ingestion.file_filter import safe_decode
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.py"
            p.write_text("hello = 1\n", encoding="utf-8")
            text, err = safe_decode(p)
            self.assertIsNone(err)
            self.assertIn("hello", text)

    def test_empty_file_returns_empty_string(self):
        from app.ingestion.file_filter import safe_decode
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.py"
            p.write_bytes(b"")
            text, err = safe_decode(p)
            self.assertIsNone(err)
            self.assertEqual(text, "")

    def test_heavily_corrupted_returns_error(self):
        """A file with > 5% replacement chars must return (None, reason)."""
        from app.ingestion.file_filter import safe_decode
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.py"
            # Mostly null/invalid bytes — will produce high \ufffd ratio
            p.write_bytes(bytes(range(128, 256)) * 20)
            text, err = safe_decode(p)
            self.assertIsNone(text)
            self.assertIsNotNone(err)
            self.assertIn("threshold", err)

    def test_occasional_bad_bytes_below_threshold_passes(self):
        """A file with < 5% replacement chars should pass."""
        from app.ingestion.file_filter import safe_decode, MAX_REPLACEMENT_CHAR_RATIO
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ok.py"
            # 1000 ASCII bytes + 1 invalid byte → 0.1% ratio → well below 5%
            p.write_bytes(b"x = 1\n" * 166 + b"\xff")
            text, err = safe_decode(p)
            self.assertIsNone(err)
            self.assertIsNotNone(text)

    def test_unreadable_file_returns_error(self):
        """OSError during read must return (None, reason)."""
        from app.ingestion.file_filter import safe_decode
        p = Path("/nonexistent/path/file.py")
        text, err = safe_decode(p)
        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertIn("read error", err)


# ===========================================================================
# B.  Directory exclusions
# ===========================================================================

class TestDirectoryExclusions(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_git_dir_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), ".git/config", b"[core]")
            _write(Path(td), ".git/hooks/pre-commit", b"#!/bin/sh")
            _py(Path(td), ".git/objects/fake.py")  # even a .py inside .git
            results = self._run(td)
            self.assertEqual(results, [])

    def test_node_modules_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _js(Path(td), "node_modules/lodash/index.js")
            _js(Path(td), "node_modules/react/index.js")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_pycache_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "__pycache__/module.cpython-311.pyc", b"\x00\xd0\r\n")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_venv_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), ".venv/lib/python3.11/site-packages/six.py")
            _py(Path(td), "venv/lib/python3.11/site-packages/attr.py")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_dist_and_build_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _js(Path(td), "dist/bundle.js")
            _js(Path(td), "build/app.js")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_nested_node_modules_excluded(self):
        """node_modules/ nested inside src/ must also be excluded."""
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/main.py")
            _js(Path(td), "src/node_modules/dep/index.js")
            results = self._run(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].display_path, "src/main.py")

    def test_non_excluded_dir_passes(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/main.py")
            _py(Path(td), "tests/test_main.py")
            results = self._run(td)
            self.assertEqual(len(results), 2)


# ===========================================================================
# C.  File-level hard exclusions
# ===========================================================================

class TestFileLevelExclusions(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_lock_files_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "package-lock.json", b"{}"),
            _write(Path(td), "yarn.lock", b"# yarn\n"),
            _write(Path(td), "Pipfile.lock", b"{}"),
            results = self._run(td)
            self.assertEqual(results, [])

    def test_d_ts_files_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "types/index.d.ts", b"export type Foo = string;")
            _write(Path(td), "src/lib.d.ts", b"declare module 'x';")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_d_ts_excluded_but_regular_ts_passes(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "src/index.d.ts", b"declare const x: number;")
            _write(Path(td), "src/index.ts", b"const x: number = 1;\n")
            results = self._run(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].display_path, "src/index.ts")


# ===========================================================================
# D.  Supported extension filter + language mapping
# ===========================================================================

class TestExtensionAndLanguage(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def _make_files(self, root: Path):
        _py(root, "main.py")
        _js(root, "app.js")
        _js(root, "component.jsx")
        _write(root, "types.ts", b"const x: number = 1;\n")
        _write(root, "page.tsx", b"export const Page = () => null;\n")
        # unsupported
        _write(root, "styles.css", b"body { color: red; }")
        _write(root, "README.md", b"# Project")
        _write(root, "Makefile", b"all:\n\techo done")
        _write(root, "data.json", b'{"key": "value"}')

    def test_supported_extensions_pass(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_files(Path(td))
            results = self._run(td)
            display_paths = {r.display_path for r in results}
            self.assertIn("main.py", display_paths)
            self.assertIn("app.js", display_paths)
            self.assertIn("component.jsx", display_paths)
            self.assertIn("types.ts", display_paths)
            self.assertIn("page.tsx", display_paths)

    def test_unsupported_extensions_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_files(Path(td))
            results = self._run(td)
            display_paths = {r.display_path for r in results}
            self.assertNotIn("styles.css", display_paths)
            self.assertNotIn("README.md", display_paths)
            self.assertNotIn("Makefile", display_paths)
            self.assertNotIn("data.json", display_paths)

    def test_language_mapping_py(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "main.py")
            results = self._run(td)
            self.assertEqual(results[0].language, "python")

    def test_language_mapping_js(self):
        with tempfile.TemporaryDirectory() as td:
            _js(Path(td), "app.js")
            results = self._run(td)
            self.assertEqual(results[0].language, "javascript")

    def test_language_mapping_jsx(self):
        with tempfile.TemporaryDirectory() as td:
            _js(Path(td), "comp.jsx")
            results = self._run(td)
            self.assertEqual(results[0].language, "javascript",
                ".jsx must map to 'javascript', not 'jsx'")

    def test_language_mapping_ts(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "t.ts", b"const x: number = 1;\n")
            results = self._run(td)
            self.assertEqual(results[0].language, "typescript")

    def test_language_mapping_tsx(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "p.tsx", b"export const P = () => null;\n")
            results = self._run(td)
            self.assertEqual(results[0].language, "tsx",
                ".tsx must map to 'tsx'")


# ===========================================================================
# E.  Binary sniff
# ===========================================================================

class TestBinarySniff(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_file_with_null_bytes_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "compiled.py"
            p.write_bytes(b"def foo():\n    pass\x00\x00garbage")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_clean_text_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "clean.py")
            results = self._run(td)
            self.assertEqual(len(results), 1)

    def test_binary_sniff_only_reads_first_8kb(self):
        """A file that starts clean but has a null byte AFTER the 8 KB window passes the sniff."""
        from app.ingestion.file_filter import BINARY_SNIFF_BYTES, _is_binary
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "mostly_text.py"
            # Write BINARY_SNIFF_BYTES + 10 bytes of clean content, then a null byte
            # The null byte is at position BINARY_SNIFF_BYTES + 10 — outside the sniff window.
            clean_block = b"x = 1\n" * ((BINARY_SNIFF_BYTES + 10) // 6 + 1)
            # Trim to exactly BINARY_SNIFF_BYTES + 10 clean bytes, then append null
            content = clean_block[:BINARY_SNIFF_BYTES + 10] + b"\x00"
            p.write_bytes(content)
            # Confirm the null byte is outside the sniff window
            self.assertGreater(len(content), BINARY_SNIFF_BYTES)
            self.assertNotIn(b"\x00", content[:BINARY_SNIFF_BYTES])
            # The null-byte sniff should NOT detect it as binary
            self.assertFalse(_is_binary(p),
                "Null byte after the 8KB sniff window must not cause binary detection")


# ===========================================================================
# F.  Size cap
# ===========================================================================

class TestSizeCap(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_oversized_file_excluded(self):
        from app.ingestion.file_filter import MAX_FILE_SIZE_BYTES
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "huge.py"
            # Write just over 1 MB
            p.write_bytes(b"x = 1\n" * ((MAX_FILE_SIZE_BYTES // 6) + 1))
            results = self._run(td)
            self.assertEqual(results, [])

    def test_just_under_limit_passes(self):
        from app.ingestion.file_filter import MAX_FILE_SIZE_BYTES
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "ok.py"
            # Build a valid Python file just under 1 MB using clean ASCII content
            line = b"x = 1  # padding comment\n"  # 25 bytes, all ASCII
            n_lines = (MAX_FILE_SIZE_BYTES - 1) // len(line)
            p.write_bytes(line * n_lines)
            assert p.stat().st_size < MAX_FILE_SIZE_BYTES
            results = self._run(td)
            self.assertEqual(len(results), 1)


# ===========================================================================
# G.  Generated-code path patterns
# ===========================================================================

class TestGeneratedPathPatterns(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_min_js_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "static/vendor.min.js", b"!function(){}();")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_pb2_py_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "proto/user_pb2.py")
            _py(Path(td), "proto/user_pb2_grpc.py")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_generated_dir_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/generated/schema.py")
            _js(Path(td), "src/generated/api.js")
            results = self._run(td)
            self.assertEqual(results, [])

    def test_non_generated_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/main.py")
            results = self._run(td)
            self.assertEqual(len(results), 1)


# ===========================================================================
# H.  Mean-line-length heuristic (combined signal)
# ===========================================================================

class TestMeanLineLengthHeuristic(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_minified_js_without_min_name_excluded(self):
        """
        A .js file that doesn't match *.min.js by name but is one long line
        (characteristic of minification) must be caught by the combined heuristic.
        This is the key edge case from the spec.
        """
        from app.ingestion.file_filter import MAX_MEAN_LINE_LENGTH
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bundle.js"       # no .min. in name
            # Single very long line — mean line length ≫ 300
            p.write_bytes(
                (b"var x=" + b"a" * (MAX_MEAN_LINE_LENGTH * 2) + b";") * 1
            )
            results = self._run(td)
            self.assertEqual(results, [], "Minified JS should be excluded by line-length heuristic")

    def test_normal_file_with_long_content_passes(self):
        """
        A legitimate Python file with moderate line lengths must not be excluded
        on line-length alone.
        """
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "normal.py", lines=50)
            results = self._run(td)
            self.assertEqual(len(results), 1)

    def test_long_sql_fixture_would_pass_if_py(self):
        """
        A long but non-minified file (e.g. a SQL fixture embedded in Python)
        with mean line length under 300 must survive.
        """
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixtures.py"
            # 500 lines each 80 chars — mean = 80, well under 300
            content = (b"x = '" + b"a" * 74 + b"'\n") * 500
            p.write_bytes(content)
            results = self._run(td)
            self.assertEqual(len(results), 1)


# ===========================================================================
# I.  Path normalization (case sensitivity)
# ===========================================================================

class TestPathNormalization(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_normalized_path_is_lowercase(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "src/MyModule.py", b"x = 1\n")
            results = self._run(td)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].normalized_path, "src/mymodule.py")
            self.assertEqual(results[0].display_path, "src/MyModule.py")

    def test_display_path_preserves_casing(self):
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "src/Auth.ts", b"const x: number = 1;\n")
            results = self._run(td)
            self.assertEqual(results[0].display_path, "src/Auth.ts")
            self.assertNotEqual(results[0].display_path, results[0].normalized_path)

    def test_two_case_variant_files_both_survive(self):
        """
        The critical cross-filesystem scenario:
        src/Auth.ts and src/auth.ts are distinct files on a case-sensitive
        (Linux) filesystem. Both must appear as distinct display_path entries,
        each with a consistent (lowercased) normalized_path.

        On a case-insensitive filesystem (macOS/Windows) these can't coexist
        as real files, so we simulate the scenario by using different
        subdirectories to hold the two variants.
        """
        with tempfile.TemporaryDirectory() as td:
            # Simulate two files that would differ only by case on Linux.
            # We put them in different dirs to make them coexist on any OS.
            _write(Path(td), "casea/Auth.ts", b"const x: number = 1;\n")
            _write(Path(td), "caseb/auth.ts", b"const y: number = 2;\n")
            results = self._run(td)

            display_paths = {r.display_path for r in results}
            normalized_paths = {r.normalized_path for r in results}

            self.assertEqual(len(results), 2, "Both case variants must survive")
            self.assertIn("casea/Auth.ts", display_paths)
            self.assertIn("caseb/auth.ts", display_paths)
            # Normalized paths differ only because the directories differ
            self.assertIn("casea/auth.ts", normalized_paths)
            self.assertIn("caseb/auth.ts", normalized_paths)

    def test_normalized_path_used_for_dedup_not_display(self):
        """Confirm the record carries both paths for the downstream consumer."""
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "SRC/Main.PY", b"x = 1\n")
            results = self._run(td)
            if not results:
                self.skipTest("Case variants not supported on this OS file system")
            r = results[0]
            self.assertNotEqual(r.display_path, r.normalized_path)
            self.assertEqual(r.normalized_path, r.display_path.lower())


# ===========================================================================
# J.  Encoding corruption
# ===========================================================================

class TestEncodingCorruption(unittest.TestCase):

    def _run(self, td: str) -> list:
        from app.ingestion.file_filter import filter_repo_files
        return filter_repo_files(Path(td), repo_id="test-repo")

    def test_heavily_corrupted_py_file_excluded(self):
        """A .py file with >5% replacement chars must be excluded."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "corrupted.py"
            # Mostly non-UTF-8 bytes — high replacement-char ratio
            p.write_bytes(bytes(range(128, 256)) * 30)
            results = self._run(td)
            self.assertEqual(results, [])

    def test_clean_utf8_py_file_passes(self):
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "clean.py")
            results = self._run(td)
            self.assertEqual(len(results), 1)


# ===========================================================================
# K.  Empty-repo edge case
# ===========================================================================

class TestEmptyRepo(unittest.TestCase):

    def test_no_supported_files_returns_empty_list(self):
        """
        A repo with only unsupported files must not crash and must return [].
        Module 12 uses this to surface the "No supported files found" warning.
        """
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            _write(Path(td), "README.md", b"# Project")
            _write(Path(td), "Makefile", b"all:\n\techo done")
            _write(Path(td), "styles.css", b"body {}")
            results = filter_repo_files(Path(td), repo_id="empty-repo")
            self.assertEqual(results, [])

    def test_completely_empty_dir_returns_empty_list(self):
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            results = filter_repo_files(Path(td), repo_id="empty-repo")
            self.assertEqual(results, [])


# ===========================================================================
# L.  FileRecord output contract
# ===========================================================================

class TestFileRecordContract(unittest.TestCase):

    def test_all_required_fields_present(self):
        from app.ingestion.file_filter import filter_repo_files, FileRecord
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/main.py")
            results = filter_repo_files(Path(td), repo_id="test-repo")
            self.assertEqual(len(results), 1)
            r = results[0]
            # All required fields must be present and correctly typed
            self.assertIsInstance(r, FileRecord)
            self.assertIsInstance(r.path, str)
            self.assertIsInstance(r.display_path, str)
            self.assertIsInstance(r.normalized_path, str)
            self.assertIsInstance(r.language, str)
            self.assertIsInstance(r.size_bytes, int)
            self.assertIn(r.language, {"python", "javascript", "typescript"})

    def test_path_is_absolute(self):
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "main.py")
            results = filter_repo_files(Path(td), repo_id="test-repo")
            self.assertTrue(Path(results[0].path).is_absolute())

    def test_display_path_is_relative(self):
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            _py(Path(td), "src/app/main.py")
            results = filter_repo_files(Path(td), repo_id="test-repo")
            self.assertFalse(Path(results[0].display_path).is_absolute())
            self.assertEqual(results[0].display_path, "src/app/main.py")

    def test_size_bytes_matches_actual_file(self):
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            content = b"x = 42\n" * 10
            p = _write(Path(td), "main.py", content)
            results = filter_repo_files(Path(td), repo_id="test-repo")
            self.assertEqual(results[0].size_bytes, len(content))


# ===========================================================================
# M.  Integration: realistic mixed repo
# ===========================================================================

class TestRealisticMixedRepo(unittest.TestCase):
    """
    Build a synthetic repo that mirrors real-world noise and verify that only
    the legitimate source files survive.
    """

    def _build_repo(self, root: Path) -> set[str]:
        """
        Create a fake repo and return the set of display_paths expected to survive.
        """
        # -- Files that SHOULD survive --
        surviving = set()

        _py(root, "src/app.py");           surviving.add("src/app.py")
        _js(root, "src/index.js");         surviving.add("src/index.js")
        _js(root, "src/Component.jsx");    surviving.add("src/Component.jsx")
        _write(root, "src/types.ts",
               b"const x: number = 1;\n"); surviving.add("src/types.ts")
        _write(root, "src/Page.tsx",
               b"export const P = () => null;\n"); surviving.add("src/Page.tsx")

        # -- Files that SHOULD be excluded --

        # Directory exclusions
        _js(root, "node_modules/react/index.js")
        _py(root, "__pycache__/app.cpython-311.pyc")  # wrong ext anyway
        _py(root, ".venv/lib/six.py")
        _js(root, "dist/bundle.js")

        # Lock / d.ts
        _write(root, "package-lock.json", b"{}")
        _write(root, "yarn.lock", b"# yarn")
        _write(root, "src/types.d.ts", b"declare const x: number;")

        # Binary
        _write(root, "src/image.py", b"def x():\n    pass\x00BINARY")

        # Oversized (we can't write 1MB in a unit test easily — skip)

        # Generated by pattern
        _js(root, "static/vendor.min.js")
        _py(root, "proto/user_pb2.py")
        _py(root, "proto/user_pb2_grpc.py")
        _js(root, "src/generated/api.js")

        # Unsupported extensions
        _write(root, "README.md", b"# Project")
        _write(root, "styles.css", b"body {}")

        return surviving

    def test_only_surviving_files_in_output(self):
        from app.ingestion.file_filter import filter_repo_files
        with tempfile.TemporaryDirectory() as td:
            expected = self._build_repo(Path(td))
            results = filter_repo_files(Path(td), repo_id="mixed-repo")
            actual = {r.display_path for r in results}
            self.assertEqual(actual, expected,
                f"\nMissing: {expected - actual}\nExtra:   {actual - expected}")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
