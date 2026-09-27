"""Deterministic feature extraction from a unified git diff.

Everything here is pure text processing: no subprocess calls, no network
access, no randomness. The same diff text always produces the same
:class:`DiffStats`, which is what lets the rest of codepoem build a poem
from a seed derived purely from the diff itself.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Matches the start of a per-file section: "diff --git a/path b/path"
_DIFF_GIT_RE = re.compile(r"^diff --git a/(?P<a>.*) b/(?P<b>.*)$")
# Matches "--- a/path" / "--- /dev/null" style old-file markers.
_OLD_FILE_RE = re.compile(r"^--- (?:a/(?P<path>.*)|(?P<dev_null>/dev/null))$")
# Matches "+++ b/path" / "+++ /dev/null" style new-file markers.
_NEW_FILE_RE = re.compile(r"^\+\+\+ (?:b/(?P<path>.*)|(?P<dev_null>/dev/null))$")
_RENAME_FROM_RE = re.compile(r"^rename from (?P<path>.*)$")
_RENAME_TO_RE = re.compile(r"^rename to (?P<path>.*)$")
_BINARY_RE = re.compile(r"^Binary files (?P<a>.*) and (?P<b>.*) differ$")
_HUNK_HEADER_RE = re.compile(r"^@@ .*@@")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Words too common in code or English prose to be useful as "top keywords".
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "her",
        "was", "one", "our", "out", "day", "get", "has", "him", "his", "how",
        "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did",
        "its", "let", "put", "say", "she", "too", "use", "with", "this",
        "that", "from", "have", "were", "been", "will", "self", "true",
        "false", "none", "null", "def", "return", "import", "from", "class",
        "if", "else", "elif", "for", "while", "try", "except", "finally",
        "pass", "raise", "yield", "lambda", "async", "await", "const",
        "let", "var", "function", "export", "default", "require", "print",
        "log", "console", "then", "when", "where", "which", "into", "over",
        "under", "then", "also", "such", "only", "just", "than", "then",
    }
)

_MIN_KEYWORD_LEN = 3
_DEFAULT_TOP_N = 10


@dataclass(frozen=True)
class FileChange:
    """A single file touched by the diff."""

    path: str
    status: str  # "added" | "deleted" | "modified" | "renamed"
    lines_added: int = 0
    lines_removed: int = 0
    old_path: str | None = None  # set only when status == "renamed"
    binary: bool = False


@dataclass(frozen=True)
class DiffStats:
    """Deterministic features extracted from a unified diff."""

    files: list[FileChange] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    keywords: list[str] = field(default_factory=list)

    @property
    def files_touched(self) -> int:
        return len(self.files)


class _FileAccumulator:
    """Mutable working state for the file currently being parsed."""

    __slots__ = (
        "old_path",
        "new_path",
        "is_new",
        "is_deleted",
        "is_renamed",
        "is_binary",
        "added",
        "removed",
    )

    def __init__(self) -> None:
        self.old_path: str | None = None
        self.new_path: str | None = None
        self.is_new = False
        self.is_deleted = False
        self.is_renamed = False
        self.is_binary = False
        self.added = 0
        self.removed = 0

    def resolve_path(self) -> str:
        return self.new_path or self.old_path or "unknown"

    def status(self) -> str:
        if self.is_deleted:
            return "deleted"
        if self.is_renamed:
            return "renamed"
        if self.is_new:
            return "added"
        return "modified"

    def to_file_change(self) -> FileChange:
        return FileChange(
            path=self.resolve_path(),
            status=self.status(),
            lines_added=self.added,
            lines_removed=self.removed,
            old_path=self.old_path if self.is_renamed else None,
            binary=self.is_binary,
        )


def parse_diff(text: str, top_n: int = _DEFAULT_TOP_N) -> DiffStats:
    """Parse a unified git diff and extract deterministic features.

    Unknown or malformed input never raises: it is simply treated as
    containing no recognisable diff content, so an empty or garbage diff
    yields an empty :class:`DiffStats` rather than an exception.
    """

    files: list[FileChange] = []
    word_counts: Counter[str] = Counter()
    total_added = 0
    total_removed = 0

    current: _FileAccumulator | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            files.append(current.to_file_change())
        current = None

    if text is None:
        text = ""

    for raw_line in text.splitlines():
        m = _DIFF_GIT_RE.match(raw_line)
        if m:
            flush()
            current = _FileAccumulator()
            current.old_path = m.group("a")
            current.new_path = m.group("b")
            continue

        if current is None:
            # Content outside any "diff --git" block (e.g. a bare patch
            # produced with `git diff --no-prefix` against one file) is
            # still worth tracking once we see file markers.
            m = _OLD_FILE_RE.match(raw_line)
            if m and (m.group("path") or m.group("dev_null")):
                current = _FileAccumulator()
                if m.group("dev_null"):
                    current.is_new = True
                else:
                    current.old_path = m.group("path")
                continue
            continue

        m = _BINARY_RE.match(raw_line)
        if m:
            current.is_binary = True
            continue

        m = _RENAME_FROM_RE.match(raw_line)
        if m:
            current.is_renamed = True
            current.old_path = m.group("path")
            continue

        m = _RENAME_TO_RE.match(raw_line)
        if m:
            current.is_renamed = True
            current.new_path = m.group("path")
            continue

        if raw_line.startswith("new file mode"):
            current.is_new = True
            continue

        if raw_line.startswith("deleted file mode"):
            current.is_deleted = True
            continue

        m = _OLD_FILE_RE.match(raw_line)
        if m:
            if m.group("dev_null"):
                current.is_new = True
            else:
                current.old_path = m.group("path")
            continue

        m = _NEW_FILE_RE.match(raw_line)
        if m:
            if m.group("dev_null"):
                current.is_deleted = True
            else:
                current.new_path = m.group("path")
            continue

        if _HUNK_HEADER_RE.match(raw_line):
            continue

        if raw_line.startswith("\\"):
            # "\ No newline at end of file" and similar markers.
            continue

        if raw_line.startswith("+") :
            current.added += 1
            total_added += 1
            _collect_keywords(raw_line[1:], word_counts)
            continue

        if raw_line.startswith("-"):
            current.removed += 1
            total_removed += 1
            _collect_keywords(raw_line[1:], word_counts)
            continue

        # Context line, index line, mode line, etc: no feature signal.

    flush()

    keywords = _top_keywords(word_counts, top_n)

    return DiffStats(
        files=files,
        lines_added=total_added,
        lines_removed=total_removed,
        keywords=keywords,
    )


def _collect_keywords(content: str, counter: Counter[str]) -> None:
    for word in _WORD_RE.findall(content):
        lower = word.lower()
        if len(lower) < _MIN_KEYWORD_LEN:
            continue
        if lower in _STOPWORDS:
            continue
        if lower.isdigit():
            continue
        counter[lower] += 1


def _top_keywords(counter: Counter[str], top_n: int) -> list[str]:
    # Sort by (descending count, ascending word) so ties break the same
    # way on every run regardless of dict/Counter iteration order.
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _count in ranked[:top_n]]
