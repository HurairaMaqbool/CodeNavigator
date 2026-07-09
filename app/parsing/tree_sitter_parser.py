# Copyright (c) 2026 Huraira Maqbool
# All Rights Reserved
# Unauthorized copying, modification, distribution, reverse engineering,
# or commercial use of this file is strictly prohibited.

"""
app/parsing/tree_sitter_parser.py
-----------------------------------
Parse a source file with tree-sitter and return structured metadata about
functions, classes, and imports.

Responsibility boundary
-----------------------
This module receives a file path + pre-decoded content string from Module 4
and returns a :class:`ParsedFile`.  It does NOT:
  - clone anything (Module 3),
  - filter or classify files (Module 4),
  - chunk, embed, or write to any store (Modules 5-7).

Tree-sitter availability
------------------------
``tree-sitter``, ``tree-sitter-python``, ``tree-sitter-javascript``, and
``tree-sitter-typescript`` are optional at import time.  Calling
:func:`parse_file` when they are missing raises :class:`ParserUnavailableError`
rather than crashing the whole ingestion run.

Per-file parse failures
-----------------------
A file that fails to parse (syntax error, unexpected tree-sitter exception,
encoding edge case) must NOT crash the ingestion run.  :func:`parse_file`
returns ``None`` and logs the failure.  The ingestion orchestrator (Module 9)
treats a ``None`` return as "skip this file" and continues with the remaining
files.  This is intentional: repositories do contain occasionally
syntax-broken or partially-committed files (e.g. merge conflicts, detached
notebook outputs), and crashing the whole job for one bad file would be a
poor user experience.

Supported languages (v1)
------------------------
- ``python``      — tree-sitter-python
- ``javascript``  — tree-sitter-javascript  (covers .js and .jsx)
- ``typescript``  — tree-sitter-typescript  (covers .ts and .tsx)

What is deliberately NOT parsed (v1 scope)
------------------------------------------
- Nested function definitions (functions inside functions).
  Reason: the added complexity in AST traversal is not justified by the
  retrieval-quality signal in v1; most meaningful code lives at the
  module/class level.
- Anonymous immediately-invoked functions.
- TypeScript-specific syntax beyond what the JavaScript grammar shares
  (e.g. decorators, complex generic constraints).  The grammar handles these
  gracefully — we just don't extract extra metadata from them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.observability.logging_config import logger

# ---------------------------------------------------------------------------
# Optional tree-sitter imports — graceful degradation when deps are missing
# ---------------------------------------------------------------------------

_PARSERS_AVAILABLE = False
_IMPORT_ERROR_MSG = ""

try:
    from tree_sitter import Language, Parser  # type: ignore[import]
    import tree_sitter_python as _tspython                       # type: ignore[import]
    import tree_sitter_javascript as _tsjavascript               # type: ignore[import]
    import tree_sitter_typescript as _tstypescript               # type: ignore[import]

    _PY_LANGUAGE = Language(_tspython.language())
    _JS_LANGUAGE = Language(_tsjavascript.language())
    _TS_LANGUAGE = Language(_tstypescript.language_typescript())
    _TSX_LANGUAGE = Language(_tstypescript.language_tsx())

    try:
        import tree_sitter_go as _tsgo
        _GO_LANGUAGE: Language | None = Language(_tsgo.language())
    except (ImportError, AttributeError):
        _GO_LANGUAGE = None

    try:
        import tree_sitter_java as _tsjava
        _JAVA_LANGUAGE: Language | None = Language(_tsjava.language())
    except (ImportError, AttributeError):
        _JAVA_LANGUAGE = None

    try:
        import tree_sitter_rust as _tsrust
        _RUST_LANGUAGE: Language | None = Language(_tsrust.language())
    except (ImportError, AttributeError):
        _RUST_LANGUAGE = None

    _PARSERS_AVAILABLE = True
except ImportError as _e:
    _IMPORT_ERROR_MSG = str(_e)
    Language = Parser = None  # type: ignore[assignment, misc]
    _PY_LANGUAGE = _JS_LANGUAGE = _TS_LANGUAGE = _TSX_LANGUAGE = None
    _GO_LANGUAGE = _JAVA_LANGUAGE = _RUST_LANGUAGE = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParserUnavailableError(RuntimeError):
    """Raised when tree-sitter packages are not installed."""


# ---------------------------------------------------------------------------
# Output dataclasses  (the ParsedFile contract)
# ---------------------------------------------------------------------------

@dataclass
class ParsedFunction:
    """
    A single function or method extracted from a source file.

    Fields
    ------
    name        Identifier as written in source.
    start_line  1-indexed, inclusive.
    end_line    1-indexed, inclusive.
    params      Parameter names only — types and defaults stripped.
                For Python ``self``/``cls`` are included.
    docstring   First string literal in the function body, cleaned of quotes.
                ``None`` if no docstring is present — never a fabricated placeholder.
    calls       Names of functions/methods called inside the body.
                Cross-file resolution is Module 7's job; we only record the names
                as they appear at call sites.
    """
    name: str
    start_line: int
    end_line: int
    params: list[str] = field(default_factory=list)
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)


@dataclass
class ParsedClass:
    """
    A single class extracted from a source file.

    Fields
    ------
    methods     Top-level method definitions (not nested classes).
    base_classes Unresolved base-class names as they appear in the source.
    """
    name: str
    start_line: int
    end_line: int
    methods: list[ParsedFunction] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    """
    A single import statement.

    For ``import os``:           module="os",  names=[]
    For ``from os import path``: module="os",  names=["path"]
    For ``from os import *``:    module="os",  names=["*"]
    """
    module: str
    names: list[str] = field(default_factory=list)
    line: int = 0


@dataclass
class ParsedFile:
    """
    Structured metadata for one source file.

    ``file_path`` is the display_path (original casing, relative to repo root)
    passed in from Module 4.  The chunker and all downstream consumers use this
    field to label chunks.

    ``functions`` contains only *top-level* functions (module/script scope).
    Class methods are stored inside their :class:`ParsedClass` objects, not here.

    ``normalized_path`` is an optional normalized/lowercased path used by the
    confidence module for case-insensitive matching.
    """
    file_path: str
    language: str
    functions: list[ParsedFunction] = field(default_factory=list)
    classes: list[ParsedClass] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    normalized_path: str = ""


# ---------------------------------------------------------------------------
# Shared AST helpers (language-agnostic)
# ---------------------------------------------------------------------------

def _node_text(node: Any) -> str:
    """Decode a tree-sitter node's byte text to str, replacing errors."""
    raw = getattr(node, "text", b"")
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _find_nodes(root: Any, *types: str):
    """
    Yield all descendant nodes (BFS) whose ``.type`` is in *types*.

    BFS order means parent nodes appear before children, which is important for
    separating top-level functions from methods inside classes.
    """
    queue: list[Any] = [root]
    while queue:
        node = queue.pop(0)
        if node.type in types:
            yield node
        queue.extend(node.children)


def _collect_call_names(node: Any, calls: set[str], call_node_type: str) -> None:
    """
    Recursively accumulate function/method names from call expressions.

    *call_node_type* differs by language:
    - Python:      ``"call"``
    - JS / TS:     ``"call_expression"``
    """
    if node.type == call_node_type:
        func_node = node.child_by_field_name("function")
        if func_node is not None:
            if func_node.type == "identifier":
                calls.add(_node_text(func_node))
            elif func_node.type in ("attribute", "member_expression"):
                # obj.method() — record the method name, not the object
                attr = func_node.child_by_field_name("attribute")
                if attr is None:
                    attr = func_node.child_by_field_name("property")
                if attr is not None:
                    calls.add(_node_text(attr))
    for child in node.children:
        _collect_call_names(child, calls, call_node_type)


# ---------------------------------------------------------------------------
# Python parser helpers
# ---------------------------------------------------------------------------

def _parse_python_params(params_node: Any) -> list[str]:
    """
    Extract parameter names from a Python ``parameters`` node.

    Strips type annotations (``:``) and default values (``=``).
    Handles ``*args``, ``**kwargs``, and bare ``*`` (positional-only separator).
    """
    if params_node is None:
        return []
    params: list[str] = []
    for child in params_node.named_children:
        t = child.type
        if t == "identifier":
            params.append(_node_text(child))
        elif t in ("default_parameter", "typed_parameter", "typed_default_parameter"):
            # First named child is always the identifier
            nc = child.named_children
            if nc:
                params.append(_node_text(nc[0]))
        elif t == "list_splat_pattern":
            nc = child.named_children
            params.append(("*" + _node_text(nc[0])) if nc else "*")
        elif t == "dictionary_splat_pattern":
            nc = child.named_children
            params.append(("**" + _node_text(nc[0])) if nc else "**")
        # bare ``*`` keyword_separator: skip
    return [p for p in params if p]


def _extract_python_docstring(block_node: Any) -> str | None:
    """
    Extract the docstring from a Python ``block`` node.

    The docstring is the first statement of the block if and only if it is a
    bare string expression (``expression_statement > string``).
    Returns ``None`` when no docstring is present — never a fabricated string.
    """
    if block_node is None:
        return None
    for child in block_node.named_children:
        if child.type == "expression_statement":
            for sub in child.named_children:
                if sub.type == "string":
                    return _clean_docstring(_node_text(sub))
        # Only check the very first named child
        break
    return None


def _clean_docstring(raw: str) -> str:
    """Strip surrounding quote delimiters from a Python string literal."""
    for q in ('"""', "'''"):
        if raw.startswith(q) and raw.endswith(q) and len(raw) >= len(q) * 2:
            return raw[len(q):-len(q)].strip()
    for q in ('"', "'"):
        if raw.startswith(q) and raw.endswith(q) and len(raw) >= 2:
            return raw[1:-1].strip()
    return raw.strip()


def _parse_python_function_node(node: Any) -> ParsedFunction | None:
    """Parse a single Python ``function_definition`` node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node)
    params = _parse_python_params(node.child_by_field_name("parameters"))
    body = node.child_by_field_name("body")
    docstring = _extract_python_docstring(body)
    calls: set[str] = set()
    if body is not None:
        _collect_call_names(body, calls, "call")
    return ParsedFunction(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        params=params,
        docstring=docstring,
        calls=sorted(calls),
    )


def _parse_python_class_node(node: Any) -> ParsedClass | None:
    """Parse a Python ``class_definition`` node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node)

    # Base classes: inside the argument_list child
    base_classes: list[str] = []
    args_node = node.child_by_field_name("argument_list") or node.child_by_field_name("superclasses")
    if args_node is not None:
        for bc in args_node.named_children:
            if bc.type in ("identifier", "attribute", "dotted_name"):
                base_classes.append(_node_text(bc))

    # Methods: function_definitions inside the body block
    body = node.child_by_field_name("body")
    methods: list[ParsedFunction] = []
    if body is not None:
        for child in body.named_children:
            if child.type == "function_definition":
                mf = _parse_python_function_node(child)
                if mf is not None:
                    methods.append(mf)
            elif child.type == "decorated_definition":
                # @decorator\ndef method(): ...
                for sub in child.named_children:
                    if sub.type == "function_definition":
                        mf = _parse_python_function_node(sub)
                        if mf is not None:
                            methods.append(mf)

    return ParsedClass(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        methods=methods,
        base_classes=base_classes,
    )


def _parse_python(
    tree: Any,
    content: str,
) -> tuple[list[ParsedFunction], list[ParsedClass], list[ParsedImport]]:
    """Extract functions, classes, and imports from a parsed Python tree."""
    root = tree.root_node
    functions: list[ParsedFunction] = []
    classes: list[ParsedClass] = []
    imports: list[ParsedImport] = []

    # Collect class name→node so we can skip their methods in the top-level scan
    class_nodes: set[int] = set()

    # ── Classes ──────────────────────────────────────────────────────────────
    for node in _find_nodes(root, "class_definition"):
        # Only top-level classes (direct child of module)
        if node.parent and node.parent.type in ("module", "block"):
            if node.parent.type == "module":
                pc = _parse_python_class_node(node)
                if pc is not None:
                    classes.append(pc)
                    class_nodes.add(id(node))

    # ── Top-level functions (not methods) ────────────────────────────────────
    for node in root.named_children:
        if node.type == "function_definition":
            pf = _parse_python_function_node(node)
            if pf is not None:
                functions.append(pf)
        elif node.type == "decorated_definition":
            for child in node.named_children:
                if child.type == "function_definition":
                    pf = _parse_python_function_node(child)
                    if pf is not None:
                        functions.append(pf)

    # ── Imports ──────────────────────────────────────────────────────────────
    for node in _find_nodes(root, "import_statement", "import_from_statement"):
        line = node.start_point[0] + 1
        if node.type == "import_statement":
            for child in node.named_children:
                if child.type in ("dotted_name", "aliased_import"):
                    mod_node = child.named_children[0] if child.type == "aliased_import" else child
                    imports.append(ParsedImport(module=_node_text(mod_node), names=[], line=line))
        elif node.type == "import_from_statement":
            mod_node = node.child_by_field_name("module_name")
            module = _node_text(mod_node) if mod_node else ""
            names: list[str] = []
            for child in node.named_children:
                if child.type == "dotted_name" and child != mod_node:
                    names.append(_node_text(child))
                elif child.type == "aliased_import":
                    nc = child.named_children
                    if nc:
                        names.append(_node_text(nc[0]))
                elif child.type == "import_star":
                    names.append("*")
            if module:
                imports.append(ParsedImport(module=module, names=names, line=line))

    return functions, classes, imports


# ---------------------------------------------------------------------------
# JavaScript / TypeScript parser helpers
# ---------------------------------------------------------------------------

def _parse_js_params(params_node: Any) -> list[str]:
    """Extract parameter names from a JS/TS ``formal_parameters`` node."""
    if params_node is None:
        return []
    params: list[str] = []
    for child in params_node.named_children:
        t = child.type
        if t == "identifier":
            params.append(_node_text(child))
        elif t == "assignment_pattern":
            # param = default → grab the left side (identifier)
            left = child.child_by_field_name("left")
            if left is not None and left.type == "identifier":
                params.append(_node_text(left))
        elif t == "rest_pattern":
            nc = child.named_children
            if nc:
                params.append("..." + _node_text(nc[0]))
        elif t in ("object_pattern", "array_pattern"):
            # Destructured param — record as-is for now
            params.append(_node_text(child))
    return [p for p in params if p]


def _parse_js_function_declaration(node: Any) -> ParsedFunction | None:
    """Parse a JS/TS ``function_declaration`` or ``function`` node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node)
    params = _parse_js_params(node.child_by_field_name("parameters"))
    body = node.child_by_field_name("body")
    calls: set[str] = set()
    if body is not None:
        _collect_call_names(body, calls, "call_expression")
    return ParsedFunction(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        params=params,
        docstring=None,  # JS has no standard docstring convention in the AST
        calls=sorted(calls),
    )


def _parse_js_arrow_in_declaration(decl_node: Any) -> ParsedFunction | None:
    """
    Parse ``const foo = (x) => ...`` style arrow functions.

    Only handles the common top-level pattern:
        (lexical_declaration | variable_declaration)
          variable_declarator
            name: identifier
            value: arrow_function | function_expression
    """
    for declarator in _find_nodes(decl_node, "variable_declarator"):
        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        if value_node.type not in ("arrow_function", "function_expression", "function"):
            continue
        name = _node_text(name_node)
        params = _parse_js_params(value_node.child_by_field_name("parameters") or
                                  value_node.child_by_field_name("parameter"))
        body = value_node.child_by_field_name("body")
        calls: set[str] = set()
        if body is not None:
            _collect_call_names(body, calls, "call_expression")
        return ParsedFunction(
            name=name,
            start_line=decl_node.start_point[0] + 1,
            end_line=decl_node.end_point[0] + 1,
            params=params,
            docstring=None,
            calls=sorted(calls),
        )
    return None


def _parse_js_class_node(node: Any) -> ParsedClass | None:
    """Parse a JS/TS ``class_declaration`` or ``class`` node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node)

    # Base classes: from the class_heritage node
    base_classes: list[str] = []
    heritage = node.child_by_field_name("heritage")
    if heritage is not None:
        for child in heritage.named_children:
            if child.type == "identifier":
                base_classes.append(_node_text(child))

    # Methods: method_definition inside class_body
    body = node.child_by_field_name("body")
    methods: list[ParsedFunction] = []
    if body is not None:
        for child in body.named_children:
            if child.type == "method_definition":
                m = _parse_js_method(child)
                if m is not None:
                    methods.append(m)

    return ParsedClass(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        methods=methods,
        base_classes=base_classes,
    )


def _parse_js_method(node: Any) -> ParsedFunction | None:
    """Parse a ``method_definition`` inside a JS/TS class body."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = _node_text(name_node)
    params = _parse_js_params(node.child_by_field_name("parameters"))
    body = node.child_by_field_name("body")
    calls: set[str] = set()
    if body is not None:
        _collect_call_names(body, calls, "call_expression")
    return ParsedFunction(
        name=name,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        params=params,
        docstring=None,
        calls=sorted(calls),
    )


def _unwrap_export(node: Any) -> Any:
    """
    If *node* is an ``export_statement``, return its exported declaration.
    Otherwise return *node* unchanged.
    """
    if node.type == "export_statement":
        for child in node.named_children:
            if child.type not in ("export", "default", "export_clause"):
                return child
    return node


def _parse_javascript(
    tree: Any,
    content: str,
) -> tuple[list[ParsedFunction], list[ParsedClass], list[ParsedImport]]:
    """Extract functions, classes, and imports from a JS/TS tree."""
    root = tree.root_node
    functions: list[ParsedFunction] = []
    classes: list[ParsedClass] = []
    imports: list[ParsedImport] = []

    for node in root.named_children:
        actual = _unwrap_export(node)

        if actual.type == "function_declaration":
            pf = _parse_js_function_declaration(actual)
            if pf is not None:
                functions.append(pf)

        elif actual.type in ("lexical_declaration", "variable_declaration"):
            pf = _parse_js_arrow_in_declaration(actual)
            if pf is not None:
                functions.append(pf)

        elif actual.type in ("class_declaration", "class"):
            pc = _parse_js_class_node(actual)
            if pc is not None:
                classes.append(pc)

        elif actual.type == "import_statement":
            line = actual.start_point[0] + 1
            # from: import_clause > named_imports / namespace_import / identifier
            # module: string (the 'from' target)
            source_node = actual.child_by_field_name("source")
            module = _clean_docstring(_node_text(source_node)) if source_node else ""

            names: list[str] = []
            clause = actual.child_by_field_name("import")
            if clause is not None:
                for imp in _find_nodes(clause, "identifier", "import_specifier"):
                    if imp.type == "identifier":
                        names.append(_node_text(imp))
                    elif imp.type == "import_specifier":
                        nc = imp.named_children
                        if nc:
                            names.append(_node_text(nc[0]))

            if module:
                imports.append(ParsedImport(module=module, names=names, line=line))

    return functions, classes, imports


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_parser(language: str) -> Parser | None:
    """Factory method to get the appropriate Tree-Sitter parser."""
    if not _PARSERS_AVAILABLE:
        raise ParserUnavailableError(
            "tree-sitter packages are not installed. "
            f"Original import error: {_IMPORT_ERROR_MSG}. "
            "Run: pip install -r requirements.txt"
        )
    
    if language == "python":
        ts_language = _PY_LANGUAGE
    elif language == "javascript":
        ts_language = _JS_LANGUAGE
    elif language == "typescript":
        ts_language = _TS_LANGUAGE
    elif language == "tsx":
        ts_language = _TSX_LANGUAGE
    elif language == "go":
        ts_language = _GO_LANGUAGE
    elif language == "java":
        ts_language = _JAVA_LANGUAGE
    elif language == "rust":
        ts_language = _RUST_LANGUAGE
    else:
        return None
        
    if ts_language is None:
        return None

    parser = Parser(ts_language)
    return parser

def parse_file(
    file_path: str,
    content: str | None = None,
    language: str | None = None,
) -> ParsedFile | None:
    """
    Parse *content* (or read from *file_path*) using the tree-sitter grammar for *language*.

    Parameters
    ----------
    file_path:
        The file path to be parsed.
    content:
        Optional file content. If None, read from file_path.
    language:
        Optional language name. If None, auto-detected from file extension.

    Returns
    -------
    ParsedFile | None
        None on any parse failure.
    """
    if content is None:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("file_read_failed_for_parser", file_path=file_path, error=str(exc))
            return None

    if language is None:
        suffix = Path(file_path).suffix.lower()
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".go": "go",
            ".java": "java",
            ".rs": "rust",
        }
        language = ext_map.get(suffix)
        if not language:
            # Treat as filter-layer bug and fail loudly in tests
            raise ValueError(f"Unsupported language extension: {suffix}")

    log = logger.bind(file_path=file_path, language=language)

    parser = get_parser(language)
    if not parser:
        if language in ("go", "java", "rust"):
            log.info("falling_back_to_regex_parser", language=language)
            return _parse_file_regex_fallback(file_path, content, language)
        log.warning("unsupported_language_for_parser", language=language)
        return None

    try:
        tree = parser.parse(content.encode("utf-8"))

        if tree.root_node.has_error:
            log.warning("file_parse_syntax_errors", reason="Syntax errors detected by tree-sitter")

        if language == "python":
            functions, classes, imports = _parse_python(tree, content)
        else:
            # javascript, typescript, and tsx share the same traversal logic
            functions, classes, imports = _parse_javascript(tree, content)

        parsed = ParsedFile(
            file_path=file_path,
            language=language,
            functions=functions,
            classes=classes,
            imports=imports,
            normalized_path=file_path.lower(),
        )
        log.debug(
            "file_parsed",
            n_functions=len(functions),
            n_classes=len(classes),
            n_imports=len(imports),
        )
        return parsed

    except Exception as exc:  # noqa: BLE001
        # Intentionally broad: any tree-sitter exception (syntax error,
        # internal error, unexpected node shape) must not abort the run.
        log.warning(
            "file_parse_failed",
            reason=str(exc),
            exc_info=True,
        )
        return None


def _parse_file_regex_fallback(file_path: str, content: str, language: str) -> ParsedFile:
    """
    Regex-based fallback parser for Go, Java, and Rust when tree-sitter grammars are missing.
    Ensures these files can be chunked and indexed rather than skipped entirely.
    """
    functions: list[ParsedFunction] = []
    classes: list[ParsedClass] = []
    imports: list[ParsedImport] = []

    lines = content.splitlines()
    
    # 1. Imports
    if language == "go":
        in_import_block = False
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if line_stripped.startswith('import "') or line_stripped.startswith("import `"):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    mod = parts[1].strip('"`')
                    imports.append(ParsedImport(module=mod, names=[], line=line_num))
            elif line_stripped == "import (":
                in_import_block = True
            elif in_import_block and line_stripped == ")":
                in_import_block = False
            elif in_import_block:
                mod = line_stripped.strip('"`')
                if mod:
                    imports.append(ParsedImport(module=mod, names=[], line=line_num))
    elif language == "java":
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if line_stripped.startswith("import ") and line_stripped.endswith(";"):
                parts = line_stripped[7:-1].strip().split()
                if parts:
                    imports.append(ParsedImport(module=parts[-1], names=[], line=line_num))
    elif language == "rust":
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if line_stripped.startswith("use ") and line_stripped.endswith(";"):
                mod = line_stripped[4:-1].strip()
                imports.append(ParsedImport(module=mod, names=[], line=line_num))

    # 2. Functions & Classes / Structs
    if language == "go":
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if line_stripped.startswith("func "):
                parts = line_stripped.split()
                # Find the part that has '(' which is the start of parameters
                for idx_p, part in enumerate(parts):
                    if idx_p > 0 and "(" in part:
                        name = part.split("(")[0]
                        if name:
                            functions.append(ParsedFunction(name=name, start_line=line_num, end_line=line_num + 5))
                            break
                        else:
                            # Receiver matched, e.g. parts = ["func", "(u", "*User)", "String()"]
                            if idx_p + 2 < len(parts):
                                # check parts[idx_p + 1] or parts[idx_p + 2]
                                next_part = parts[idx_p + 1]
                                if ")" in next_part:
                                    if idx_p + 2 < len(parts):
                                        next_part = parts[idx_p + 2]
                                name2 = next_part.split("(")[0]
                                if name2:
                                    functions.append(ParsedFunction(name=name2, start_line=line_num, end_line=line_num + 5))
                                    break
            elif "struct" in line_stripped and line_stripped.startswith("type "):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    classes.append(ParsedClass(name=parts[1], start_line=line_num, end_line=line_num + 10))

    elif language == "java":
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if "class " in line_stripped or "interface " in line_stripped:
                parts = line_stripped.split()
                try:
                    idx_cls = parts.index("class")
                    name = parts[idx_cls + 1].split("{")[0]
                    classes.append(ParsedClass(name=name, start_line=line_num, end_line=line_num + 15))
                except ValueError:
                    try:
                        idx_inf = parts.index("interface")
                        name = parts[idx_inf + 1].split("{")[0]
                        classes.append(ParsedClass(name=name, start_line=line_num, end_line=line_num + 15))
                    except ValueError:
                        pass
            elif "(" in line_stripped and ")" in line_stripped and "new " not in line_stripped and "=" not in line_stripped and not line_stripped.endswith(";"):
                parts = line_stripped.split("(")
                before_paren = parts[0].strip().split()
                if before_paren and not any(k in before_paren for k in ["if", "for", "while", "switch", "return"]):
                    name = before_paren[-1]
                    if name.isidentifier():
                        functions.append(ParsedFunction(name=name, start_line=line_num, end_line=line_num + 10))

    elif language == "rust":
        for idx, line in enumerate(lines):
            line_num = idx + 1
            line_stripped = line.strip()
            if line_stripped.startswith("fn ") or (line_stripped.startswith("pub fn ") or line_stripped.startswith("pub(crate) fn ")):
                parts = line_stripped.split("fn ")
                if len(parts) >= 2:
                    name = parts[1].split("(")[0].strip()
                    if name.isidentifier():
                        functions.append(ParsedFunction(name=name, start_line=line_num, end_line=line_num + 8))
            elif "struct " in line_stripped or "enum " in line_stripped:
                parts = line_stripped.split()
                try:
                    idx_struct = parts.index("struct")
                    name = parts[idx_struct + 1].split("{")[0].split(";")[0]
                    classes.append(ParsedClass(name=name, start_line=line_num, end_line=line_num + 12))
                except ValueError:
                    try:
                        idx_enum = parts.index("enum")
                        name = parts[idx_enum + 1].split("{")[0]
                        classes.append(ParsedClass(name=name, start_line=line_num, end_line=line_num + 12))
                    except ValueError:
                        pass

    return ParsedFile(
        file_path=file_path,
        language=language,
        functions=functions,
        classes=classes,
        imports=imports,
        normalized_path=file_path.lower(),
    )


def extract_definitions(ast: Any) -> list[dict[str, Any]]:
    """
    Walk the AST and collect function, class, and import nodes.
    Returns list of dicts with: {name, type, start_line, end_line}.
    Line numbers are 1-indexed.
    """
    if isinstance(ast, ParsedFile):
        # Allow passing the parsed output representation directly
        results = []
        for f in ast.functions:
            results.append({"name": f.name, "type": "function", "start_line": f.start_line, "end_line": f.end_line})
        for c in ast.classes:
            results.append({"name": c.name, "type": "class", "start_line": c.start_line, "end_line": c.end_line})
        for i in ast.imports:
            results.append({"name": i.module, "type": "import", "start_line": i.line, "end_line": i.line})
        return results

    if hasattr(ast, "root_node"):
        root = ast.root_node
    else:
        root = ast

    if not root:
        return []

    # Map node types to normalized type
    type_map = {
        # Python
        "function_definition": "function",
        "class_definition": "class",
        "import_statement": "import",
        "import_from_statement": "import",
        # Javascript / TypeScript
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "arrow_function": "function",
        "method_definition": "function",
        "class_declaration": "class",
        "class": "class",
        # Go
        "function_declaration": "function",
        "method_declaration": "function",
        "import_declaration": "import",
        # Java
        "method_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "class",
        "import_declaration": "import",
        # Rust
        "function_item": "function",
        "struct_item": "class",
        "enum_item": "class",
        "impl_item": "class",
        "use_declaration": "import",
    }

    results = []

    def walk(node):
        ntype = node.type
        if ntype in type_map:
            name = ""
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _node_text(name_node)
            else:
                for child in node.named_children:
                    if child.type == "identifier":
                        name = _node_text(child)
                        break
            if not name:
                name = ntype

            results.append({
                "name": name,
                "type": type_map[ntype],
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
            })
        
        for child in node.children:
            walk(child)

    walk(root)
    return results
