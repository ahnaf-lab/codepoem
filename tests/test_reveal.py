import unittest

from codepoem.reveal import RevealFrame, TypewriterReveal


class TestTypewriterRevealFrameByFrame(unittest.TestCase):
    def test_initial_frame_reveals_nothing(self):
        reveal = TypewriterReveal(["hi", "yo"])
        frame = reveal.frame
        self.assertEqual(frame.lines, ("", ""))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (0, 0))
        self.assertFalse(frame.done)

    def test_advances_one_character_per_tick_within_a_line(self):
        reveal = TypewriterReveal(["hi", "yo"])

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("h", ""))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (0, 1))
        self.assertFalse(frame.done)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("hi", ""))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (1, 0))
        self.assertFalse(frame.done)

    def test_crosses_line_boundary_on_the_next_tick(self):
        reveal = TypewriterReveal(["hi", "yo"])
        reveal.advance()  # "h"
        reveal.advance()  # "hi"

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("hi", "y"))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (1, 1))
        self.assertFalse(frame.done)

    def test_final_tick_marks_done_and_rests_cursor_at_line_end(self):
        reveal = TypewriterReveal(["hi", "yo"])
        for _ in range(3):
            reveal.advance()

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("hi", "yo"))
        self.assertTrue(frame.done)
        self.assertEqual((frame.cursor_line, frame.cursor_col), (1, 2))

    def test_advance_past_done_is_a_stable_no_op(self):
        reveal = TypewriterReveal(["hi"])
        reveal.advance()
        reveal.advance()
        self.assertTrue(reveal.is_done)

        frame_a = reveal.advance()
        frame_b = reveal.advance()
        self.assertEqual(frame_a, frame_b)
        self.assertEqual(frame_a.lines, ("hi",))
        self.assertTrue(frame_a.done)

    def test_chars_per_tick_greater_than_one_reveals_in_chunks(self):
        reveal = TypewriterReveal(["abcdef"], chars_per_tick=3)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("abc",))
        self.assertFalse(frame.done)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("abcdef",))
        self.assertTrue(frame.done)

    def test_tick_can_spill_a_multi_char_chunk_across_lines(self):
        # Only 2 chars remain on line 0 ("hi"); a chars_per_tick of 5
        # spends the other 3 continuing straight into line 1.
        reveal = TypewriterReveal(["hi", "there"], chars_per_tick=5)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("hi", "the"))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (1, 3))
        self.assertFalse(frame.done)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("hi", "there"))
        self.assertTrue(frame.done)

    def test_empty_lines_are_skipped_without_consuming_a_tick(self):
        reveal = TypewriterReveal(["a", "", "b"])

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("a", "", ""))
        self.assertEqual((frame.cursor_line, frame.cursor_col), (2, 0))
        self.assertFalse(frame.done)

        frame = reveal.advance()
        self.assertEqual(frame.lines, ("a", "", "b"))
        self.assertTrue(frame.done)

    def test_no_lines_at_all_is_immediately_done(self):
        reveal = TypewriterReveal([])
        frame = reveal.frame
        self.assertEqual(frame.lines, ())
        self.assertEqual((frame.cursor_line, frame.cursor_col), (0, 0))
        self.assertTrue(frame.done)
        self.assertEqual(reveal.ticks_needed, 0)

        # Advancing an already-done, already-empty reveal stays a no-op.
        self.assertEqual(reveal.advance(), frame)

    def test_skip_jumps_straight_to_the_final_frame(self):
        reveal = TypewriterReveal(["hello", "world"])
        reveal.advance()

        frame = reveal.skip()
        self.assertEqual(frame.lines, ("hello", "world"))
        self.assertTrue(frame.done)
        self.assertTrue(reveal.is_done)

    def test_reset_returns_to_the_first_frame(self):
        reveal = TypewriterReveal(["hi"])
        reveal.advance()
        reveal.advance()
        self.assertTrue(reveal.is_done)

        frame = reveal.reset()
        self.assertEqual(frame.lines, ("",))
        self.assertFalse(frame.done)
        self.assertFalse(reveal.is_done)

    def test_ticks_needed_matches_the_actual_number_of_advances(self):
        reveal = TypewriterReveal(["abc", "de"], chars_per_tick=2)
        self.assertEqual(reveal.ticks_needed, 3)

        ticks = 0
        while not reveal.is_done:
            reveal.advance()
            ticks += 1
        self.assertEqual(ticks, reveal.ticks_needed)

    def test_invalid_chars_per_tick_is_rejected(self):
        with self.assertRaises(ValueError):
            TypewriterReveal(["hi"], chars_per_tick=0)

    def test_frame_is_a_plain_comparable_dataclass(self):
        frame = TypewriterReveal(["x"]).frame
        self.assertIsInstance(frame, RevealFrame)
        self.assertEqual(frame, RevealFrame(lines=("",), cursor_line=0, cursor_col=0, done=False))


if __name__ == "__main__":
    unittest.main()
