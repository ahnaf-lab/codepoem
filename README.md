# codepoem

A terminal TUI that reads a git diff, extracts deterministic features from
it, and turns your commit into a short typewritten poem — haiku, limerick or
free verse — using a seeded template engine. No LLM involved: the same diff
always produces the same poem.

This milestone adds the poem generator: a seeded template engine that turns
the diff parser's extracted features (lines added/removed, files touched,
top keywords, renames, binary files) into a haiku, limerick or free-verse
poem. The same diff always produces the same poem — a hash of its own
features seeds Python's `random.Random`, and the form (haiku/limerick/free
verse) is picked deterministically from that seed. Haiku and limerick draw
from hand-written, syllable- and rhyme-checked line pools filtered by which
"themes" the diff exhibits (net growth, deletions, renames, a big sprawling
change, ...); free verse has no meter to protect, so it interpolates live
feature values (file names, keyword, counts) directly.

This milestone also adds the TUI renderer: a typewriter effect that reveals
a generated poem in the terminal one character at a time. It is split into
two pieces on purpose. `codepoem.reveal.TypewriterReveal` is a pure state
machine — no terminal, no `curses`, no wall-clock sleep — that tracks how
many characters have been revealed and produces a `RevealFrame` (the
partially revealed lines, the cursor position, whether the reveal is done)
for any given number of ticks; it is what the test suite exercises frame by
frame. `codepoem.tui` is a thin `curses` adapter that owns the actual window
and timing loop, drives that state machine one tick per frame, and lets any
keypress skip straight to the finished poem.

## Install

Requires Python 3.10+. No third-party dependencies — everything used
(`re`, `dataclasses`, `collections.Counter`, `hashlib`, `random`) is in the
standard library, which is enough to parse a diff and generate a
deterministic poem from it without pulling in a dependency.

```
git clone <this-repo-url>
cd codepoem
python3 -m pip install -e .
```

(Editable install is optional; the package also works by running Python
directly from the repository root.)

## Usage

```python
from codepoem.diffparser import parse_diff

diff_text = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,3 @@
 def greet():
-    print("hi")
+    print("hello world")
+    return None
"""

stats = parse_diff(diff_text)
print(stats.files_touched)   # 1
print(stats.lines_added)     # 2
print(stats.lines_removed)   # 1
print(stats.keywords)        # e.g. ["hello", "world"]
```

Turn those features into a poem with `generate_poem`:

```python
from codepoem.poemgen import generate_poem, FORM_HAIKU

poem = generate_poem(stats)               # form picked deterministically
poem = generate_poem(stats, form=FORM_HAIKU)  # or request one explicitly
print(poem.form)                          # "haiku", "limerick" or "free_verse"
print(poem)                               # the poem, one line per row
```

Calling `generate_poem` again on the same `diff_text` always returns the
same poem — there is no model and no network call involved, just a hash of
the diff's own features used as a random seed.

Play the poem back in the terminal with a typewriter reveal:

```python
from codepoem.tui import render_poem

render_poem(poem)  # opens a curses screen; press any key to skip or exit
```

The reveal itself is driven by a small, terminal-independent state machine
that you can also use directly (for example to drive a different renderer,
or just to inspect what a given tick reveals):

```python
from codepoem.reveal import TypewriterReveal

reveal = TypewriterReveal(poem.lines)
frame = reveal.advance()   # reveals one more character
print(frame.lines)         # each line, revealed up to this tick
print(frame.done)          # True once every line is fully shown
```

Run the test suite with:

```
python3 -m unittest discover -s tests
```

## Status

This project is built autonomously, milestone by milestone, and only ships
changes that pass a full test run.
