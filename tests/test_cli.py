import io
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from codepoem.cli import GitError, build_parser, get_diff_text, main


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


_SIMPLE_DIFF = (
    "diff --git a/foo.py b/foo.py\n"
    "--- a/foo.py\n"
    "+++ b/foo.py\n"
    "@@ -1,2 +1,3 @@\n"
    " def greet():\n"
    "-    print('hi')\n"
    "+    print('hello world')\n"
    "+    return None\n"
)


class GetDiffTextTests(unittest.TestCase):
    def test_no_ref_runs_git_diff(self):
        with patch("codepoem.cli.subprocess.run") as run:
            run.return_value = _completed(stdout=_SIMPLE_DIFF)
            text = get_diff_text(None)

        self.assertEqual(text, _SIMPLE_DIFF)
        called_args = run.call_args.args[0]
        self.assertEqual(called_args, ["git", "diff"])

    def test_ref_runs_git_show_with_patch(self):
        with patch("codepoem.cli.subprocess.run") as run:
            run.return_value = _completed(stdout=_SIMPLE_DIFF)
            text = get_diff_text("HEAD~1")

        self.assertEqual(text, _SIMPLE_DIFF)
        called_args = run.call_args.args[0]
        self.assertEqual(called_args, ["git", "show", "--patch", "HEAD~1"])

    def test_ref_that_looks_like_a_flag_is_rejected_before_running_git(self):
        with patch("codepoem.cli.subprocess.run") as run:
            with self.assertRaises(GitError):
                get_diff_text("--upload-pack=evil")
            run.assert_not_called()

    def test_nonzero_git_exit_raises_git_error_with_stderr_message(self):
        with patch("codepoem.cli.subprocess.run") as run:
            run.return_value = _completed(
                returncode=128, stderr="fatal: bad revision 'nope'"
            )
            with self.assertRaises(GitError) as ctx:
                get_diff_text("nope")

        self.assertIn("bad revision", str(ctx.exception))

    def test_missing_git_executable_raises_git_error(self):
        with patch("codepoem.cli.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(GitError):
                get_diff_text(None)

    def test_timeout_raises_git_error(self):
        timeout = subprocess.TimeoutExpired(cmd=["git", "diff"], timeout=10)
        with patch("codepoem.cli.subprocess.run", side_effect=timeout):
            with self.assertRaises(GitError):
                get_diff_text(None)


class BuildParserTests(unittest.TestCase):
    def test_defaults(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.ref)
        self.assertIsNone(args.form)
        self.assertFalse(args.no_anim)

    def test_ref_and_flags_parsed(self):
        args = build_parser().parse_args(["HEAD", "--form", "haiku", "--no-anim"])
        self.assertEqual(args.ref, "HEAD")
        self.assertEqual(args.form, "haiku")
        self.assertTrue(args.no_anim)

    def test_unknown_form_is_rejected(self):
        with self.assertRaises(SystemExit):
            with redirect_stderr(io.StringIO()):
                build_parser().parse_args(["--form", "sonnet"])


class MainTests(unittest.TestCase):
    def test_no_anim_prints_plain_poem_text_and_returns_zero(self):
        with patch("codepoem.cli.get_diff_text", return_value=_SIMPLE_DIFF):
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = main(["--no-anim"])

        self.assertEqual(exit_code, 0)
        printed = out.getvalue()
        self.assertTrue(printed.strip())
        # No curses control sequences should ever appear in plain output.
        self.assertNotIn("\x1b[", printed)

    def test_no_anim_output_is_deterministic_across_runs(self):
        with patch("codepoem.cli.get_diff_text", return_value=_SIMPLE_DIFF):
            out1 = io.StringIO()
            with redirect_stdout(out1):
                main(["--no-anim"])
            out2 = io.StringIO()
            with redirect_stdout(out2):
                main(["--no-anim"])

        self.assertEqual(out1.getvalue(), out2.getvalue())

    def test_explicit_form_is_honoured(self):
        with patch("codepoem.cli.get_diff_text", return_value=_SIMPLE_DIFF):
            out = io.StringIO()
            with redirect_stdout(out):
                main(["--no-anim", "--form", "limerick"])

        # A limerick is always 5 lines.
        lines = [line for line in out.getvalue().splitlines() if line]
        self.assertEqual(len(lines), 5)

    def test_non_tty_stdout_falls_back_to_plain_text_without_no_anim(self):
        # redirect_stdout swaps in a StringIO, which is never a tty, so this
        # exercises the isatty() fallback path without --no-anim.
        with patch("codepoem.cli.get_diff_text", return_value=_SIMPLE_DIFF):
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertTrue(out.getvalue().strip())

    def test_git_error_prints_to_stderr_and_returns_one(self):
        with patch(
            "codepoem.cli.get_diff_text",
            side_effect=GitError("fatal: not a git repository"),
        ):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = main([])

        self.assertEqual(exit_code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("not a git repository", err.getvalue())

    def test_empty_diff_still_produces_a_poem(self):
        with patch("codepoem.cli.get_diff_text", return_value=""):
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = main(["--no-anim"])

        self.assertEqual(exit_code, 0)
        self.assertTrue(out.getvalue().strip())


if __name__ == "__main__":
    unittest.main()
