# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
tests/test_parsing.py
---------------------
Unit tests for Module 5 (Tree-sitter Parser + Chunker).

Run with:
    python -m unittest tests/test_parsing.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Bootstrap: mock structlog
os.environ.setdefault("LLM_PROVIDER", "ollama")
_structlog_mock = MagicMock()
_structlog_mock.get_logger.return_value = MagicMock()
sys.modules["structlog"] = _structlog_mock


from app.parsing.tree_sitter_parser import (
    ParsedClass,
    ParsedFile,
    ParsedFunction,
    ParsedImport,
    ParserUnavailableError,
    _PARSERS_AVAILABLE,
    parse_file,
)
from app.parsing.chunker import (
    CodeChunk,
    chunk_parsed_file,
    compute_fingerprint,
    mask_secrets,
    split_with_overlap,
)


class TestSecretMasking(unittest.TestCase):
    def test_mask_aws_keys(self):
        # Starts with AKIA followed by 16 chars
        text = 'aws_access_key_id = "AKIA1234567890123456"'
        masked = mask_secrets(text)
        self.assertEqual(masked, 'aws_access_key_id = "[REDACTED]"')

    def test_mask_api_tokens(self):
        text = 'const api_key = "abcdefghijklmnopqrstuvwxyz";'
        masked = mask_secrets(text)
        self.assertEqual(masked, 'const api_key = "[REDACTED]";')

    def test_mask_passwords(self):
        text = 'password = "mysecretpassword123"'
        masked = mask_secrets(text)
        self.assertEqual(masked, 'password = "[REDACTED]"')

    def test_false_positive_preservation(self):
        # Short strings or strings not assigned to typical secret keys
        text = 'greeting = "hello world this is long enough"'
        self.assertEqual(mask_secrets(text), text)

    def test_masking_before_fingerprinting_dedup_case(self):
        """
        Two functions identical except for leaked secrets must compute the
        same fingerprint.
        """
        f1_body = 'def connect():\n    pwd = "secretpassword"\n    return pwd'
        f2_body = 'def connect():\n    pwd = "differentpassword"\n    return pwd'
        
        masked1 = mask_secrets(f1_body)
        masked2 = mask_secrets(f2_body)
        
        self.assertEqual(masked1, masked2, "After masking, bodies must be identical")
        
        fp1 = compute_fingerprint("src/db.py", "connect", masked1)
        fp2 = compute_fingerprint("src/db.py", "connect", masked2)
        
        self.assertEqual(fp1, fp2, "Fingerprints must match for identical-post-mask functions")

    def test_fingerprint_includes_normalized_path(self):
        """
        Identical masked functions in different files must have different fingerprints.
        """
        body = 'def setup():\n    pass'
        fp1 = compute_fingerprint("src/a.py", "setup", body)
        fp2 = compute_fingerprint("src/b.py", "setup", body)
        self.assertNotEqual(fp1, fp2)


class TestChunkSplitter(unittest.TestCase):
    def test_no_split_needed(self):
        text = "x = 1\ny = 2\n"
        pieces = split_with_overlap(text, max_tokens=10, overlap_tokens=2)
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0], text)

    def test_split_with_overlap(self):
        # 10 lines of 10 chars each = 100 chars
        lines = [f"line {i:04d}\n" for i in range(10)]
        text = "".join(lines)
        # Token count = len // 4.
        # Let's say max_tokens = 10 (40 chars, 4 lines).
        # overlap_tokens = 5 (20 chars, 2 lines).
        pieces = split_with_overlap(text, max_tokens=10, overlap_tokens=5)
        self.assertGreater(len(pieces), 1)
        # Ensure pieces reconstruct most of the text (overlap means sum of lengths > original)
        self.assertGreater(sum(len(p) for p in pieces), len(text))
        # Each piece shouldn't exceed max chars significantly
        for p in pieces:
            self.assertLessEqual(len(p), 40 + 15)  # Some line length buffer


@unittest.skipIf(not _PARSERS_AVAILABLE, "tree-sitter parsers not available")
class TestTreeSitterPython(unittest.TestCase):
    def test_parse_functions(self):
        content = '''
import os
from math import sqrt, pi

def simple_func(a, b=1):
    """A simple function."""
    return sqrt(a + b)

class MyClass(os.PathLike):
    def __init__(self, x):
        self.x = x
        self.do_thing()
        
    def do_thing(self):
        pass
'''
        parsed = parse_file("test.py", content, "python")
        self.assertIsNotNone(parsed)
        
        self.assertEqual(len(parsed.functions), 1)
        f = parsed.functions[0]
        self.assertEqual(f.name, "simple_func")
        self.assertEqual(f.params, ["a", "b"])
        self.assertEqual(f.docstring, "A simple function.")
        self.assertEqual(f.calls, ["sqrt"])

        self.assertEqual(len(parsed.classes), 1)
        c = parsed.classes[0]
        self.assertEqual(c.name, "MyClass")
        self.assertEqual(c.base_classes, ["os.PathLike"])
        self.assertEqual(len(c.methods), 2)
        
        m_init = c.methods[0]
        self.assertEqual(m_init.name, "__init__")
        self.assertEqual(m_init.params, ["self", "x"])
        self.assertEqual(m_init.calls, ["do_thing"])

        self.assertEqual(len(parsed.imports), 2)
        self.assertEqual(parsed.imports[0].module, "os")
        self.assertEqual(parsed.imports[1].module, "math")
        self.assertEqual(parsed.imports[1].names, ["sqrt", "pi"])

    def test_parse_syntax_error_returns_none_or_partial(self):
        content = "def missing_colon()\n    pass"
        # tree-sitter is very robust, it might parse it partially.
        # But if it throws or gives weird AST, we still don't crash.
        parsed = parse_file("err.py", content, "python")
        # Should complete without raising exception
        pass


@unittest.skipIf(not _PARSERS_AVAILABLE, "tree-sitter parsers not available")
class TestTreeSitterJavascript(unittest.TestCase):
    def test_parse_js(self):
        content = '''
import { useState } from 'react';
import lodash from 'lodash';

function TopLevel(x, y) {
    console.log(x);
}

const ArrowLevel = (z) => {
    TopLevel(z);
};

class User {
    constructor(name) {
        this.name = name;
    }
    getName() {
        return this.name;
    }
}
'''
        parsed = parse_file("test.js", content, "javascript")
        self.assertIsNotNone(parsed)
        
        # Depending on how Arrow functions are parsed, we should have 2 functions
        f_names = [f.name for f in parsed.functions]
        self.assertIn("TopLevel", f_names)
        self.assertIn("ArrowLevel", f_names)
        
        c = parsed.classes[0]
        self.assertEqual(c.name, "User")
        self.assertEqual(len(c.methods), 2)
        
        i_mods = [i.module for i in parsed.imports]
        self.assertIn("react", i_mods)
        self.assertIn("lodash", i_mods)


class TestChunkingProcess(unittest.TestCase):
    def test_chunk_functions_and_classes(self):
        # We don't need tree-sitter here, just mock ParsedFile
        parsed = ParsedFile(
            file_path="src/main.py",
            language="python",
            functions=[
                ParsedFunction(name="func1", start_line=1, end_line=2),
                ParsedFunction(name="func2", start_line=4, end_line=5)
            ],
            classes=[
                ParsedClass(name="SmallClass", start_line=7, end_line=9, methods=[
                    ParsedFunction(name="meth1", start_line=8, end_line=9)
                ])
            ],
            imports=[]
        )
        content = "def func1():\n    pass\n\ndef func2():\n    pass\n\nclass SmallClass:\n    def meth1():\n        pass\n"
        
        chunks = chunk_parsed_file(
            parsed=parsed,
            content=content,
            file_path="/abs/src/main.py",
            display_path="src/main.py",
            normalized_path="src/main.py"
        )
        
        # 2 functions + 1 class (since SmallClass is < 200 lines, methods are kept with the class)
        self.assertEqual(len(chunks), 3)
        types = {c.type for c in chunks}
        self.assertEqual(types, {"function", "class"})
        
        c_class = next(c for c in chunks if c.type == "class")
        self.assertIn("# File: src/main.py | Class: SmallClass", c_class.chunk_text)

    def test_chunk_large_class_splits_methods(self):
        # Class with > 200 lines
        parsed = ParsedFile(
            file_path="src/large.py",
            language="python",
            functions=[],
            classes=[
                ParsedClass(name="LargeClass", start_line=1, end_line=250, methods=[
                    ParsedFunction(name="meth1", start_line=10, end_line=15),
                    ParsedFunction(name="meth2", start_line=20, end_line=25)
                ])
            ],
            imports=[]
        )
        # Fake content with 250 lines
        lines = [f"line {i}" for i in range(260)]
        content = "\n".join(lines)
        
        chunks = chunk_parsed_file(
            parsed=parsed,
            content=content,
            file_path="/abs/src/large.py",
            display_path="src/large.py",
            normalized_path="src/large.py"
        )
        
        # Since class > 200 lines, the class itself isn't chunked, but its methods are!
        self.assertEqual(len(chunks), 2)
        for c in chunks:
            self.assertEqual(c.type, "method")
            self.assertEqual(c.class_name, "LargeClass")
            self.assertIn("# File: src/large.py | Class: LargeClass.meth", c.chunk_text)

    def test_zero_methods_returns_empty(self):
        parsed = ParsedFile(file_path="src/empty.py", language="python")
        chunks = chunk_parsed_file(parsed, "", "/a/empty.py", "empty.py", "empty.py")
        self.assertEqual(len(chunks), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
