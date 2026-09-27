"""Tests for codepoem.diffparser."""

from __future__ import annotations

import unittest

from codepoem.diffparser import DiffStats, FileChange, parse_diff

SIMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index e69de29..4b825dc 100644
--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,4 @@
 def greet():
-    print("hello")
+    print("hello world")
+    print("goodbye")
     return None
"""

NEW_FILE_DIFF = """\
diff --git a/new_module.py b/new_module.py
new file mode 100644
index 0000000..abcd123
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def widget():
+    return "widget widget factory"
"""

DELETED_FILE_DIFF = """\
diff --git a/old_module.py b/old_module.py
deleted file mode 100644
index abcd123..0000000
--- a/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def legacy():
-    return "legacy"
"""

RENAMED_FILE_DIFF = """\
diff --git a/src/old_name.py b/src/new_name.py
similarity index 100%
rename from src/old_name.py
rename to src/new_name.py
"""

MULTI_FILE_DIFF = """\
diff --git a/a.py b/a.py
index 1111111..2222222 100644
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
 pass
+widget = widget_factory()
diff --git a/b.py b/b.py
index 3333333..4444444 100644
--- a/b.py
+++ b/b.py
@@ -1,2 +1,1 @@
-widget = None
 pass
"""

BINARY_DIFF = """\
diff --git a/image.png b/image.png
index 1111111..2222222 100644
Binary files a/image.png and b/image.png differ
"""


class ParseDiffTests(unittest.TestCase):
    def test_returns_diff_stats(self) -> None:
        result = parse_diff(SIMPLE_DIFF)
        self.assertIsInstance(result, DiffStats)

    def test_counts_added_and_removed_lines(self) -> None:
        result = parse_diff(SIMPLE_DIFF)
        self.assertEqual(result.lines_added, 2)
        self.assertEqual(result.lines_removed, 1)

    def test_detects_touched_file_and_status(self) -> None:
        result = parse_diff(SIMPLE_DIFF)
        self.assertEqual(result.files_touched, 1)
        change = result.files[0]
        self.assertIsInstance(change, FileChange)
        self.assertEqual(change.path, "foo.py")
        self.assertEqual(change.status, "modified")
        self.assertEqual(change.lines_added, 2)
        self.assertEqual(change.lines_removed, 1)

    def test_detects_new_file(self) -> None:
        result = parse_diff(NEW_FILE_DIFF)
        self.assertEqual(result.files_touched, 1)
        self.assertEqual(result.files[0].status, "added")
        self.assertEqual(result.files[0].path, "new_module.py")
        self.assertEqual(result.lines_added, 2)
        self.assertEqual(result.lines_removed, 0)

    def test_detects_deleted_file(self) -> None:
        result = parse_diff(DELETED_FILE_DIFF)
        self.assertEqual(result.files_touched, 1)
        self.assertEqual(result.files[0].status, "deleted")
        self.assertEqual(result.files[0].path, "old_module.py")
        self.assertEqual(result.lines_removed, 2)

    def test_detects_renamed_file(self) -> None:
        result = parse_diff(RENAMED_FILE_DIFF)
        self.assertEqual(result.files_touched, 1)
        change = result.files[0]
        self.assertEqual(change.status, "renamed")
        self.assertEqual(change.path, "src/new_name.py")
        self.assertEqual(change.old_path, "src/old_name.py")

    def test_multiple_files_are_all_captured(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF)
        self.assertEqual(result.files_touched, 2)
        paths = {f.path for f in result.files}
        self.assertEqual(paths, {"a.py", "b.py"})
        self.assertEqual(result.lines_added, 1)
        self.assertEqual(result.lines_removed, 1)

    def test_binary_file_is_marked_and_has_no_line_counts(self) -> None:
        result = parse_diff(BINARY_DIFF)
        self.assertEqual(result.files_touched, 1)
        change = result.files[0]
        self.assertTrue(change.binary)
        self.assertEqual(change.lines_added, 0)
        self.assertEqual(change.lines_removed, 0)

    def test_keywords_are_extracted_from_changed_content(self) -> None:
        result = parse_diff(NEW_FILE_DIFF)
        self.assertIn("widget", result.keywords)

    def test_keywords_exclude_common_stopwords(self) -> None:
        result = parse_diff(SIMPLE_DIFF)
        for stopword in ("def", "return", "print"):
            self.assertNotIn(stopword, result.keywords)

    def test_keyword_ranking_is_deterministic_across_runs(self) -> None:
        first = parse_diff(MULTI_FILE_DIFF).keywords
        second = parse_diff(MULTI_FILE_DIFF).keywords
        self.assertEqual(first, second)

    def test_keywords_respect_top_n_limit(self) -> None:
        result = parse_diff(MULTI_FILE_DIFF, top_n=1)
        self.assertLessEqual(len(result.keywords), 1)

    def test_empty_diff_yields_empty_stats(self) -> None:
        result = parse_diff("")
        self.assertEqual(result.files_touched, 0)
        self.assertEqual(result.lines_added, 0)
        self.assertEqual(result.lines_removed, 0)
        self.assertEqual(result.keywords, [])

    def test_garbage_input_does_not_raise(self) -> None:
        result = parse_diff("this is not a diff at all\njust some text\n")
        self.assertEqual(result.files_touched, 0)
        self.assertEqual(result.lines_added, 0)

    def test_none_input_is_treated_as_empty(self) -> None:
        result = parse_diff(None)  # type: ignore[arg-type]
        self.assertEqual(result.files_touched, 0)


if __name__ == "__main__":
    unittest.main()
