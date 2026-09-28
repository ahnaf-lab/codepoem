"""Curses adapter that plays a poem's typewriter reveal in the terminal.

This module owns the curses window and the timing loop only. All of the
actual reveal logic — what characters are visible after how many ticks,
where the cursor goes, when the animation ends — lives in
:class:`~codepoem.reveal.TypewriterReveal`, which has no dependency on
curses or the wall clock and is what the test suite exercises frame by
frame. Keeping the split this way means the one part that *cannot* be unit
tested without a real terminal (this module) is also the one part with
nothing interesting left to get wrong.
"""

from __future__ import annotations

import curses
import time

from .poemgen import Poem
from .reveal import RevealFrame, TypewriterReveal

# Seconds between ticks. Slow enough to read as a deliberate typewriter
# effect, fast enough that a multi-line poem finishes in a few seconds.
DEFAULT_DELAY = 0.04


def _draw(stdscr: "curses._CursesWindow", frame: RevealFrame) -> None:
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()
    for i, line in enumerate(frame.lines):
        if i >= max_y:
            break
        stdscr.addstr(i, 0, line[: max(max_x - 1, 0)])
    if not frame.done and frame.cursor_line < max_y:
        try:
            stdscr.move(frame.cursor_line, min(frame.cursor_col, max_x - 1))
        except curses.error:
            pass
    stdscr.refresh()


def _run(stdscr: "curses._CursesWindow", poem: Poem, delay: float) -> None:
    curses.curs_set(1)
    stdscr.nodelay(True)

    reveal = TypewriterReveal(poem.lines)
    _draw(stdscr, reveal.frame)

    while not reveal.is_done:
        key = stdscr.getch()
        if key != -1:
            # Any keypress during the animation skips straight to the end
            # instead of consuming that key as "dismiss the finished poem".
            _draw(stdscr, reveal.skip())
            break
        _draw(stdscr, reveal.advance())
        time.sleep(delay)

    stdscr.nodelay(False)
    stdscr.getch()


def render_poem(poem: Poem, delay: float = DEFAULT_DELAY) -> None:
    """Play ``poem``'s typewriter reveal in the terminal, then wait for a key.

    Wrapped in :func:`curses.wrapper`, which initialises the terminal
    before the loop runs and restores it afterwards even if the loop
    raises, so a crash never leaves the caller's shell in a broken state.
    """

    curses.wrapper(_run, poem, delay)
