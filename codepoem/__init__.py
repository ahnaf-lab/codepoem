"""codepoem: turn a git diff into a short, deterministic poem."""

from .diffparser import DiffStats, FileChange, parse_diff

__all__ = ["DiffStats", "FileChange", "parse_diff"]
