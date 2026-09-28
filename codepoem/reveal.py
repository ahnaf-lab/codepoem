"""Frame-by-frame state machine for the typewriter reveal effect.

Deliberately separated from any actual terminal drawing (see
:mod:`codepoem.tui`) so the reveal logic — what is visible after N ticks,
where the cursor sits, when the animation is finished — can be unit tested
character by character without a real terminal, curses, or a wall-clock
sleep anywhere in the test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class RevealFrame:
    """A snapshot of what should be on screen after some number of ticks."""

    lines: tuple[str, ...]
    cursor_line: int
    cursor_col: int
    done: bool


class TypewriterReveal:
    """Reveals a sequence of lines one or more characters at a time.

    Each call to :meth:`advance` moves the reveal forward by exactly
    ``chars_per_tick`` characters, counted across the whole poem — a tick
    may spill from the end of one line into the start of the next — and
    returns the resulting :class:`RevealFrame`. The machine is fully
    deterministic and does no I/O of its own: given the same starting
    lines and the same number of ``advance()`` calls, it always lands on
    the same frame, which is what lets tests assert on exact frames rather
    than on timing.
    """

    def __init__(self, lines: Sequence[str], chars_per_tick: int = 1) -> None:
        if chars_per_tick < 1:
            raise ValueError("chars_per_tick must be >= 1")
        self._lines: tuple[str, ...] = tuple(lines)
        self._chars_per_tick = chars_per_tick
        self._revealed = 0  # total characters revealed across all lines

    @property
    def lines(self) -> tuple[str, ...]:
        return self._lines

    @property
    def total_chars(self) -> int:
        return sum(len(line) for line in self._lines)

    @property
    def is_done(self) -> bool:
        return self._revealed >= self.total_chars

    @property
    def ticks_needed(self) -> int:
        """Number of ``advance()`` calls needed to go from start to done."""

        total = self.total_chars
        if total == 0:
            return 0
        full, remainder = divmod(total, self._chars_per_tick)
        return full + (1 if remainder else 0)

    def _frame_at(self, revealed: int) -> RevealFrame:
        remaining = revealed
        rendered: list[str] = []
        cursor_line = 0
        cursor_col = 0
        cursor_set = False
        for i, line in enumerate(self._lines):
            take = min(remaining, len(line))
            rendered.append(line[:take])
            remaining -= take
            if not cursor_set and take < len(line):
                cursor_line, cursor_col = i, take
                cursor_set = True
        if not cursor_set:
            # Fully revealed (or no lines at all): rest the cursor just
            # past the end of the last line, or at the origin if empty.
            if self._lines:
                cursor_line = len(self._lines) - 1
                cursor_col = len(self._lines[-1])
            else:
                cursor_line = 0
                cursor_col = 0
        return RevealFrame(
            lines=tuple(rendered),
            cursor_line=cursor_line,
            cursor_col=cursor_col,
            done=revealed >= self.total_chars,
        )

    @property
    def frame(self) -> RevealFrame:
        """The frame at the current position, without advancing."""

        return self._frame_at(self._revealed)

    def advance(self) -> RevealFrame:
        """Reveal up to ``chars_per_tick`` more characters, then return the frame.

        A no-op once fully revealed — repeated calls keep returning the
        same finished frame — so a caller can tick in a loop without
        checking :attr:`is_done` first.
        """

        if not self.is_done:
            self._revealed = min(
                self._revealed + self._chars_per_tick, self.total_chars
            )
        return self.frame

    def skip(self) -> RevealFrame:
        """Jump straight to the fully revealed frame."""

        self._revealed = self.total_chars
        return self.frame

    def reset(self) -> RevealFrame:
        """Return to the very first frame (nothing revealed yet)."""

        self._revealed = 0
        return self.frame
