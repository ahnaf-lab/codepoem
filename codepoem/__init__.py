"""codepoem: turn a git diff into a short, deterministic poem."""

from .diffparser import DiffStats, FileChange, parse_diff
from .poemgen import (
    FORM_FREE_VERSE,
    FORM_HAIKU,
    FORM_LIMERICK,
    Poem,
    generate_poem,
)
from .reveal import RevealFrame, TypewriterReveal

__all__ = [
    "DiffStats",
    "FileChange",
    "parse_diff",
    "Poem",
    "generate_poem",
    "FORM_HAIKU",
    "FORM_LIMERICK",
    "FORM_FREE_VERSE",
    "RevealFrame",
    "TypewriterReveal",
]
