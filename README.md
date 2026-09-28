# codepoem

A terminal TUI that reads a git diff, extracts deterministic features from
it, and turns your commit into a short typewritten poem — haiku, limerick or
free verse, in one of several selectable style packs — using a seeded
template engine. No LLM involved: the same diff, form and style always
produce the same poem.

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

This milestone adds the `codepoem` command itself. With no arguments it
reads `git diff` (your unstaged working-tree changes); given a ref, it reads
`git show <ref>` instead — both by calling `git` as a fixed, non-shell
subprocess argument list, so nothing in the diff text or a maliciously
crafted ref can inject an extra command or flag. A ref that looks like an
option (starts with `-`) is rejected before `git` ever runs. By default the
poem plays through the typewriter animation; `--no-anim` prints the
finished poem as plain text instead, which is also what happens
automatically whenever stdout is not a real terminal (for example
`codepoem | cat` or output captured in a script).

This milestone adds style packs: a second, independent axis alongside form.
A style is a complete vocabulary bank of its own — haiku line pools,
limerick rhyme groups, free-verse phrasing — so the same diff, in the same
form, reads differently depending on which style is selected, while the
meter and rhyme rules that make a haiku a haiku or a limerick a limerick
stay exactly the same regardless of style. Three styles ship: `classic`
(the default), `noir` (a detective-story vocabulary), and `cosmic` (a
space-flight vocabulary). Style is selected explicitly with `--style`; it
is never auto-picked from the diff the way form is, but once chosen the
poem's content is still a pure, deterministic function of the diff.

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
directly from the repository root, e.g. `python3 -m codepoem.cli`.)

## Usage

Run it inside a git repository, with no arguments, to turn your current
unstaged changes into a poem with a typewriter reveal:

```
codepoem
```

Pass a ref to render the poem for a specific commit instead (equivalent to
`git show <ref>`):

```
codepoem HEAD
codepoem HEAD~3
codepoem a1b2c3d
```

Add `--no-anim` to print the finished poem as plain text instead of
animating it (this also happens automatically when stdout isn't a
terminal, e.g. when piping to another command):

```
codepoem --no-anim
codepoem --no-anim HEAD
```

Force a specific form instead of letting the diff pick one deterministically:

```
codepoem --no-anim --form haiku
codepoem --no-anim --form limerick
codepoem --no-anim --form free_verse
```

Select a style pack to change the poem's vocabulary (default: `classic`):

```
codepoem --no-anim --style noir
codepoem --no-anim --style cosmic
codepoem --no-anim --form limerick --style noir
```

Or use the library directly from Python:

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
from codepoem.poemgen import generate_poem, FORM_HAIKU, STYLE_NOIR

poem = generate_poem(stats)               # form picked deterministically, classic style
poem = generate_poem(stats, form=FORM_HAIKU)  # or request a form explicitly
poem = generate_poem(stats, form=FORM_HAIKU, style=STYLE_NOIR)  # and a style
print(poem.form)                          # "haiku", "limerick" or "free_verse"
print(poem.style)                         # "classic", "noir" or "cosmic"
print(poem)                               # the poem, one line per row
```

Calling `generate_poem` again on the same `diff_text`, `form` and `style`
always returns the same poem — there is no model and no network call
involved, just a hash of the diff's own features used as a random seed.

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
