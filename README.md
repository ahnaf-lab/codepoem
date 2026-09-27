# codepoem

A terminal TUI that reads a git diff, extracts deterministic features from
it, and turns your commit into a short typewritten poem — haiku, limerick or
free verse — using a seeded template engine. No LLM involved: the same diff
always produces the same poem.

This milestone ships the diff parser: it reads a unified `git diff` and
extracts the deterministic features (lines added/removed, files touched,
top keywords) that later milestones will feed into the poem generator.

## Install

Requires Python 3.10+. No third-party dependencies — everything used
(`re`, `dataclasses`, `collections.Counter`) is in the standard library,
which is enough to parse a unified diff without pulling in a dependency.

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

Run the test suite with:

```
python3 -m unittest discover -s tests
```

## Status

This project is built autonomously, milestone by milestone, and only ships
changes that pass a full test run.
