"""Tests for codepoem.poemgen.

Two kinds of test live here: property tests that check the engine's
guarantees (determinism, correct meter, valid rhyme), and golden-file tests
that pin the exact rendered poem for a handful of fixed sample diffs so a
change to line selection is caught even if it happens to preserve meter.
"""

from __future__ import annotations

import pathlib
import unittest

from codepoem.diffparser import parse_diff
from codepoem.poemgen import (
    FORM_FREE_VERSE,
    FORM_HAIKU,
    FORM_LIMERICK,
    FORMS,
    _HAIKU_5,
    _HAIKU_7,
    _LIMERICK_A_GROUPS,
    _LIMERICK_B_GROUPS,
    Poem,
    choose_form,
    count_syllables,
    generate_poem,
    seed_for,
)

GOLDEN_DIR = pathlib.Path(__file__).parent / "golden"

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

EMPTY_DIFF = ""

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

BINARY_DIFF = """\
diff --git a/image.png b/image.png
index 1111111..2222222 100644
Binary files a/image.png and b/image.png differ
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


def _read_golden(name: str) -> str:
    return (GOLDEN_DIR / f"{name}.txt").read_text().rstrip("\n")


class SyllableCounterTests(unittest.TestCase):
    def test_counts_simple_words(self) -> None:
        self.assertEqual(count_syllables("cat"), 1)
        self.assertEqual(count_syllables("happy"), 2)
        self.assertEqual(count_syllables("beautiful"), 3)

    def test_counts_across_a_phrase(self) -> None:
        self.assertEqual(count_syllables("the cat sat"), 3)

    def test_empty_text_counts_zero(self) -> None:
        self.assertEqual(count_syllables(""), 0)
        self.assertEqual(count_syllables("123 !!!"), 0)


class HaikuPoolMeterTests(unittest.TestCase):
    """Every line in the haiku pools must scan as its declared syllable
    count, under this module's own counter — otherwise line selection
    could silently break the 5-7-5 form."""

    def test_five_syllable_pool_is_five(self) -> None:
        for text, _themes in _HAIKU_5:
            self.assertEqual(
                count_syllables(text), 5, f"{text!r} is not 5 syllables"
            )

    def test_seven_syllable_pool_is_seven(self) -> None:
        for text, _themes in _HAIKU_7:
            self.assertEqual(
                count_syllables(text), 7, f"{text!r} is not 7 syllables"
            )

    def test_pools_have_no_duplicate_lines(self) -> None:
        five_texts = [text for text, _themes in _HAIKU_5]
        seven_texts = [text for text, _themes in _HAIKU_7]
        self.assertEqual(len(five_texts), len(set(five_texts)))
        self.assertEqual(len(seven_texts), len(set(seven_texts)))


class LimerickRhymeTests(unittest.TestCase):
    def test_every_group_has_at_least_two_lines(self) -> None:
        for groups in (_LIMERICK_A_GROUPS, _LIMERICK_B_GROUPS):
            for key, pool in groups.items():
                self.assertGreaterEqual(
                    len(pool), 2, f"rhyme group {key!r} is too small to pick from"
                )

    def test_every_line_in_a_group_ends_with_its_rhyme(self) -> None:
        for key, pool in _LIMERICK_A_GROUPS.items():
            for text, _themes in pool:
                last_word = text.rstrip(".!?").split()[-1]
                self.assertTrue(
                    last_word.endswith(key), f"{text!r} does not rhyme with {key!r}"
                )
        for key, pool in _LIMERICK_B_GROUPS.items():
            for text, _themes in pool:
                last_word = text.rstrip(".!?").split()[-1]
                self.assertTrue(
                    last_word.endswith(key), f"{text!r} does not rhyme with {key!r}"
                )


class GeneratePoemTests(unittest.TestCase):
    def test_returns_poem_with_requested_form(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        for form in FORMS:
            poem = generate_poem(stats, form=form)
            self.assertIsInstance(poem, Poem)
            self.assertEqual(poem.form, form)

    def test_haiku_has_three_lines(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_HAIKU)
        self.assertEqual(len(poem.lines), 3)
        self.assertEqual(count_syllables(poem.lines[0]), 5)
        self.assertEqual(count_syllables(poem.lines[1]), 7)
        self.assertEqual(count_syllables(poem.lines[2]), 5)

    def test_limerick_has_five_lines(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_LIMERICK)
        self.assertEqual(len(poem.lines), 5)

    def test_limerick_rhyme_scheme_is_aabba(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_LIMERICK)
        last_words = [line.rstrip(".!?").split()[-1] for line in poem.lines]
        a1, a2, b1, b2, a3 = last_words

        def rhyme_key(word: str) -> str:
            for key in list(_LIMERICK_A_GROUPS) + list(_LIMERICK_B_GROUPS):
                if word.endswith(key):
                    return key
            return word

        self.assertEqual(rhyme_key(a1), rhyme_key(a2))
        self.assertEqual(rhyme_key(a2), rhyme_key(a3))
        self.assertEqual(rhyme_key(b1), rhyme_key(b2))
        self.assertNotEqual(rhyme_key(a1), rhyme_key(b1))

    def test_free_verse_has_no_fixed_line_count_but_is_non_empty(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_FREE_VERSE)
        self.assertGreater(len(poem.lines), 0)

    def test_unknown_form_is_rejected(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        with self.assertRaises(ValueError):
            generate_poem(stats, form="sonnet")

    def test_default_form_is_deterministic_from_stats(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        first = generate_poem(stats)
        second = generate_poem(stats)
        self.assertEqual(first.form, second.form)
        self.assertEqual(first.lines, second.lines)


class DeterminismTests(unittest.TestCase):
    def test_same_stats_yields_same_seed(self) -> None:
        stats_a = parse_diff(SIMPLE_DIFF)
        stats_b = parse_diff(SIMPLE_DIFF)
        self.assertEqual(seed_for(stats_a), seed_for(stats_b))

    def test_different_diffs_yield_different_seeds(self) -> None:
        seed_a = seed_for(parse_diff(SIMPLE_DIFF))
        seed_b = seed_for(parse_diff(NEW_FILE_DIFF))
        self.assertNotEqual(seed_a, seed_b)

    def test_choose_form_is_pure_function_of_seed(self) -> None:
        seed = seed_for(parse_diff(SIMPLE_DIFF))
        self.assertEqual(choose_form(seed), choose_form(seed))
        self.assertIn(choose_form(seed), FORMS)

    def test_same_diff_produces_same_poem_across_runs(self) -> None:
        stats = parse_diff(MULTI_FILE_DIFF)
        poems = [generate_poem(stats, form=FORM_LIMERICK) for _ in range(5)]
        self.assertTrue(all(p.lines == poems[0].lines for p in poems))


class GoldenFileTests(unittest.TestCase):
    """Fixed sample diffs, pinned against exact recorded poem output."""

    def test_simple_diff_haiku(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_HAIKU)
        self.assertEqual(str(poem), _read_golden("simple_diff_haiku"))

    def test_simple_diff_limerick(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_LIMERICK)
        self.assertEqual(str(poem), _read_golden("simple_diff_limerick"))

    def test_simple_diff_free_verse(self) -> None:
        stats = parse_diff(SIMPLE_DIFF)
        poem = generate_poem(stats, form=FORM_FREE_VERSE)
        self.assertEqual(str(poem), _read_golden("simple_diff_free_verse"))

    def test_empty_diff_haiku(self) -> None:
        stats = parse_diff(EMPTY_DIFF)
        poem = generate_poem(stats, form=FORM_HAIKU)
        self.assertEqual(str(poem), _read_golden("empty_diff_haiku"))

    def test_empty_diff_limerick(self) -> None:
        stats = parse_diff(EMPTY_DIFF)
        poem = generate_poem(stats, form=FORM_LIMERICK)
        self.assertEqual(str(poem), _read_golden("empty_diff_limerick"))

    def test_empty_diff_free_verse(self) -> None:
        stats = parse_diff(EMPTY_DIFF)
        poem = generate_poem(stats, form=FORM_FREE_VERSE)
        self.assertEqual(str(poem), _read_golden("empty_diff_free_verse"))

    def test_new_file_diff_haiku(self) -> None:
        stats = parse_diff(NEW_FILE_DIFF)
        poem = generate_poem(stats, form=FORM_HAIKU)
        self.assertEqual(str(poem), _read_golden("new_file_diff_haiku"))

    def test_deleted_file_diff_limerick(self) -> None:
        stats = parse_diff(DELETED_FILE_DIFF)
        poem = generate_poem(stats, form=FORM_LIMERICK)
        self.assertEqual(str(poem), _read_golden("deleted_file_diff_limerick"))

    def test_renamed_file_diff_free_verse(self) -> None:
        stats = parse_diff(RENAMED_FILE_DIFF)
        poem = generate_poem(stats, form=FORM_FREE_VERSE)
        self.assertEqual(str(poem), _read_golden("renamed_file_diff_free_verse"))

    def test_binary_diff_haiku(self) -> None:
        stats = parse_diff(BINARY_DIFF)
        poem = generate_poem(stats, form=FORM_HAIKU)
        self.assertEqual(str(poem), _read_golden("binary_diff_haiku"))

    def test_multi_file_diff_free_verse(self) -> None:
        stats = parse_diff(MULTI_FILE_DIFF)
        poem = generate_poem(stats, form=FORM_FREE_VERSE)
        self.assertEqual(str(poem), _read_golden("multi_file_diff_free_verse"))


if __name__ == "__main__":
    unittest.main()
