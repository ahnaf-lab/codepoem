"""Command-line entry point: turn a git diff into a typewritten poem.

The only I/O this module performs is a single, argument-list (never shell)
call to ``git``, so there is nothing for the diff text itself to inject
into. The one piece of user input that reaches the command line — a git
ref — is rejected up front if it could be mistaken for a flag, so
``codepoem --evil-ref`` can never smuggle an option into the underlying
``git show`` call.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Sequence

from .diffparser import parse_diff
from .poemgen import FORMS, STYLES, Poem, generate_poem
from .tui import render_poem

# Generous but finite: a hung `git` (e.g. waiting on a credential prompt for
# a missing object) should not hang codepoem forever.
_GIT_TIMEOUT_SECONDS = 10


class GitError(RuntimeError):
    """Raised when a git ref or diff cannot be resolved."""


def _validate_ref(ref: str) -> None:
    if not ref or ref.startswith("-"):
        raise GitError(f"invalid git ref: {ref!r}")


def _run_git(args: Sequence[str]) -> str:
    """Run ``git`` with a fixed argument list and return its stdout.

    Never invokes a shell and never interpolates ``args`` into a string,
    so there is no command-injection surface regardless of what a ref or
    path contains.
    """

    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError("git command timed out") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or f"git {' '.join(args)} failed"
        raise GitError(message)
    return result.stdout


def get_diff_text(ref: str | None) -> str:
    """Return unified diff text for ``ref``, or the working-tree diff.

    ``ref`` is validated before it ever reaches ``git``; ``None`` means
    "no ref given", which runs plain ``git diff`` (unstaged changes)
    instead of ``git show``.
    """

    if ref is None:
        return _run_git(["diff"])
    _validate_ref(ref)
    return _run_git(["show", "--patch", ref])


def render_plain(poem: Poem) -> str:
    """Render ``poem`` as finished plain text, no animation."""

    return str(poem)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codepoem",
        description=(
            "Read a git diff (working tree, or `git show <ref>`), and turn "
            "it into a short, deterministic poem."
        ),
    )
    parser.add_argument(
        "ref",
        nargs="?",
        default=None,
        help=(
            "a git ref to show (equivalent to `git show <ref>`); if "
            "omitted, uses `git diff` (unstaged working-tree changes)"
        ),
    )
    parser.add_argument(
        "--form",
        choices=FORMS,
        default=None,
        help="force a poem form instead of picking one from the diff",
    )
    parser.add_argument(
        "--style",
        choices=STYLES,
        default=None,
        help="select a style pack for the poem's vocabulary (default: classic)",
    )
    parser.add_argument(
        "--no-anim",
        action="store_true",
        help="print the finished poem as plain text instead of animating it",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        diff_text = get_diff_text(args.ref)
    except GitError as exc:
        print(f"codepoem: {exc}", file=sys.stderr)
        return 1

    stats = parse_diff(diff_text)
    poem = generate_poem(stats, form=args.form, style=args.style)

    # A real animation needs a real terminal to draw into; fall back to
    # plain text whenever stdout is redirected (a pipe, a file, CI logs)
    # so `codepoem | cat` degrades gracefully instead of raising a curses
    # error, in addition to the explicit `--no-anim` opt-out.
    if args.no_anim or not sys.stdout.isatty():
        print(render_plain(poem))
        return 0

    render_poem(poem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
