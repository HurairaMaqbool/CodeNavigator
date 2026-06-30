"""
app/agent/citation_repair.py
------------------------------
Post-process LLM answers: strip filler, drop ungrounded/irrelevant citations,
fix line numbers from symbol lookup + retrieval metadata, enforce conciseness.
"""
from __future__ import annotations

import re
from typing import Any

from app.agent.symbol_lookup import resolve_symbol_location, symbol_paths

_FILE_CITE = re.compile(
    r"`([\w./\-]+\.(?:py|js|jsx|ts|tsx))(?:[:](\d+)(?:-(\d+))?)?`"
)

_FILLER_START = re.compile(
    r"^\s*(?:In summary|Overall|Therefore|It's worth noting|In addition|"
    r"To summarize|In conclusion|Additionally|Furthermore|Moreover)\b",
    re.IGNORECASE,
)

_REPEAT_OPEN = re.compile(
    r"^\s*(?:As mentioned|As stated|Again,|Also,)\b",
    re.IGNORECASE,
)


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./").lower()


def _hits_by_path(hits: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for h in hits:
        fp = h.get("file_path") or ""
        if not fp:
            continue
        grouped.setdefault(_norm_path(fp), []).append(h)
    return grouped


def _symbols_in_sentence(sent: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"`([^`]+)`", sent):
        token = m.group(1).strip()
        if "." in token and token.endswith((".py", ".js", ".ts", ".tsx")):
            continue
        if token.endswith("()"):
            token = token[:-2]
        if token and token[0].isalpha():
            out.append(token.split(".")[-1])
    for m in re.finditer(r"\bclass\s+([A-Z]\w+)\b", sent):
        out.append(m.group(1))
    for m in re.finditer(r"\b([A-Z]\w+)\s+class\b", sent):
        out.append(m.group(1))
    return list(dict.fromkeys(out))


def _line_str(start: int | None, end: int | None) -> str:
    if start is None:
        return ""
    if end is not None and end != start:
        return f"{start}-{end}"
    return str(start)


def _resolve_citation_lines(
    repo_id: str | None,
    path: str,
    sent: str,
    by_path: dict[str, list[dict[str, Any]]],
) -> str:
    symbols = _symbols_in_sentence(sent)
    path_norm = _norm_path(path)

    if repo_id and symbols:
        for sym in symbols:
            loc = resolve_symbol_location(
                repo_id,
                sym,
                prefer_path=path,
                kind="class" if "class" in sent.lower() or sym[0].isupper() else "function",
            )
            if loc and _norm_path(loc["file_path"]) == path_norm:
                return _line_str(loc.get("start_line"), loc.get("end_line"))

    candidates = by_path.get(path_norm, [])
    if not candidates:
        return ""

    ranked = sorted(candidates, key=lambda h: h.get("rerank_score", 0), reverse=True)
    for sym in symbols:
        for hit in ranked:
            fn = hit.get("function_name") or ""
            base = fn.split(".")[-1] if fn else ""
            if base == sym or fn.startswith(f"{sym}."):
                return _line_str(hit.get("start_line"), hit.get("end_line"))
            chunk = hit.get("chunk") or ""
            if f"class {sym}" in chunk or f"def {sym}" in chunk:
                return _line_str(hit.get("start_line"), hit.get("end_line"))

    hit = ranked[0]
    return _line_str(hit.get("start_line"), hit.get("end_line"))


def _sentence_relevant_to_citations(
    repo_id: str | None,
    sent: str,
    file_mentions: list[tuple[str, str | None, str | None]],
) -> bool:
    """Drop sentences that cite files unrelated to symbols in the sentence."""
    if not file_mentions:
        return True
    symbols = _symbols_in_sentence(sent)
    if not symbols:
        return len(file_mentions) <= 1

    if not repo_id:
        return True

    cited = {_norm_path(p) for p, _, _ in file_mentions}
    for sym in symbols:
        sym_paths = symbol_paths(repo_id, sym)
        if sym_paths & cited:
            return True
    return False


def strip_filler_sentences(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    seen: set[str] = set()
    for sent in parts:
        if not sent.strip():
            continue
        if _FILLER_START.match(sent) or _REPEAT_OPEN.match(sent):
            continue
        norm = re.sub(r"\s+", " ", sent.lower())
        if norm in seen:
            continue
        seen.add(norm)
        kept.append(sent)
    return " ".join(kept).strip()


def enforce_word_limit(text: str, max_words: int = 120) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;") + "."


def inject_missing_citations(
    text: str,
    repo_id: str | None,
    question: str,
    retrieval_hits: list[dict[str, Any]] | None,
) -> str:
    """Add a primary file citation when the answer names a symbol but cites no file."""
    if not text or not repo_id:
        return text
    if _FILE_CITE.search(text):
        return text

    symbols: list[str] = []
    for src in (question, text):
        symbols.extend(re.findall(r"\bclass\s+([A-Z]\w+)\b", src))
        symbols.extend(re.findall(r"\b([A-Z]\w+)\s+class\b", src))
        for m in re.finditer(r"\b([A-Z][a-zA-Z_]\w*)\b", src):
            w = m.group(1)
            if w not in ("HTTP", "URL", "API", "SSL", "The", "It", "See"):
                symbols.append(w)
    symbols = list(dict.fromkeys(symbols))

    for sym in symbols[:3]:
        if sym.lower() not in text.lower() and sym not in question:
            continue
        loc = resolve_symbol_location(
            repo_id,
            sym,
            kind="class" if sym[0].isupper() else "function",
        )
        if not loc:
            continue
        lines = _line_str(loc.get("start_line"), loc.get("end_line"))
        cite = f"`{loc['file_path']}:{lines}`"
        if cite in text:
            return text
        return f"{text.rstrip('.')}. See {cite}."

    return text


def repair_answer_citations(
    text: str,
    retrieval_hits: list[dict[str, Any]] | None,
    *,
    repo_id: str | None = None,
    question: str | None = None,
) -> str:
    if not text:
        return ""

    text = strip_filler_sentences(text)
    hits = retrieval_hits or []
    by_path = _hits_by_path(hits)
    allowed_paths = set(by_path.keys()) if hits else set()

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    repaired_sentences: list[str] = []
    cite_count = 0

    for sent in sentences:
        file_mentions = _FILE_CITE.findall(sent)
        if not file_mentions:
            repaired_sentences.append(sent)
            continue

        if hits:
            grounded = all(_norm_path(p) in allowed_paths for p, _, _ in file_mentions)
            if not grounded:
                continue
            if not _sentence_relevant_to_citations(repo_id, sent, file_mentions):
                continue

        if cite_count >= 3:
            continue

        new_sent = sent
        for path, line_str, end_str in file_mentions:
            correct = _resolve_citation_lines(repo_id, path, sent, by_path)
            if not correct:
                continue
            if line_str:
                old = f"`{path}:{line_str}" + (f"-{end_str}" if end_str else "") + "`"
                new = f"`{path}:{correct}`"
                new_sent = new_sent.replace(old, new)
            else:
                new_sent = new_sent.replace(f"`{path}`", f"`{path}:{correct}`")

        repaired_sentences.append(new_sent)
        cite_count += len(_FILE_CITE.findall(new_sent))

    out = " ".join(repaired_sentences).strip()
    out = inject_missing_citations(out, repo_id, question or "", hits)
    return enforce_word_limit(out, 120)
