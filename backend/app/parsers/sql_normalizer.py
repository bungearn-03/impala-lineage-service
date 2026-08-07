"""Pure SQL text normalization: canonical re-rendering with a safe fallback.

This module performs no I/O and imports nothing from the rest of the app, so
it can be unit-tested in isolation. ``normalize_sql`` is meant to always
return *something* usable for downstream parsing steps rather than raising,
even when the input SQL is malformed or uses constructs sqlglot's parser
cannot handle.
"""

from __future__ import annotations

import re

import sqlglot

# Conservative regex-based fallback used only when sqlglot itself cannot
# parse the statement. This intentionally does not try to be a full SQL
# tokenizer -- it just strips comments and collapses whitespace so callers
# get a best-effort, still-readable string instead of an exception.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_sql(sql: str, dialect: str = "hive") -> str:
    """Return a canonical, comment-free re-rendering of ``sql``.

    Tries ``sqlglot.transpile(sql, read=dialect, write=dialect,
    pretty=False)`` first, which both validates the SQL and strips
    comments/normalizes whitespace as a side effect of re-rendering the
    parsed AST back to text.

    If sqlglot cannot parse the statement (``sqlglot.errors.ParseError`` or
    any other parse-related exception), falls back to a conservative
    regex-based pass that strips ``--`` line comments and ``/* */`` block
    comments and collapses whitespace, so callers always get something
    usable rather than a propagated exception.
    """
    text = _strip_trailing_semicolons(sql or "")
    if not text:
        return text

    try:
        statements = sqlglot.transpile(text, read=dialect, write=dialect, pretty=False)
        if statements:
            return statements[0]
        return text
    except Exception:
        return _fallback_normalize(text)


def _strip_trailing_semicolons(text: str) -> str:
    text = text.strip()
    while text.endswith(";"):
        text = text[:-1].strip()
    return text


def _fallback_normalize(text: str) -> str:
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    text = _LINE_COMMENT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return _strip_trailing_semicolons(text)
