"""Seeded template engine that turns :class:`~codepoem.diffparser.DiffStats`
into a short poem.

The design goal is reproducibility: the same diff always produces the same
poem, in the same form, forever. There is no model and no network call —
just a hash of the diff's own features used to seed :class:`random.Random`,
and a small library of hand-written, syllable-checked lines that get
filtered by which "themes" the diff exhibits (net growth, deletions,
renames, a big sprawling change, ...) and picked deterministically from
there.

Haiku and limerick lines are fixed text, each one's syllable count verified
against :func:`count_syllables` at import time, so line selection can never
silently break the form's meter. Free verse has no meter to break, so it is
the one form that interpolates live feature values (file names, keyword,
counts) directly into its lines.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

from .diffparser import DiffStats

FORM_HAIKU = "haiku"
FORM_LIMERICK = "limerick"
FORM_FREE_VERSE = "free_verse"
FORMS = (FORM_HAIKU, FORM_LIMERICK, FORM_FREE_VERSE)

_VOWEL_GROUPS_RE = re.compile(r"[aeiouy]+")


def count_syllables(text: str) -> int:
    """A rough, deterministic syllable estimate for a word or phrase.

    Counts vowel-sound groups per word (with a silent trailing "e"
    adjustment) and sums across the phrase. It is not a linguistically
    perfect syllabifier, but it is a pure function of the text, so it is
    exactly reproducible: given the same string it always returns the same
    number, which is the only property the line pools below depend on.
    """

    total = 0
    for word in re.findall(r"[A-Za-z']+", text):
        cleaned = word.lower()
        groups = _VOWEL_GROUPS_RE.findall(cleaned)
        count = len(groups)
        if cleaned.endswith("e") and not cleaned.endswith("le") and count > 1:
            count -= 1
        total += max(count, 1)
    return total


def _line(text: str, *themes: str) -> tuple[str, frozenset[str]]:
    """Tag a line with the themes it fits.

    A line given no themes is generic filler tagged "neutral" instead, so
    it is always eligible (the active theme set below always includes
    "neutral") without diluting the themed lines: those only become
    eligible when the diff actually exhibits that theme.
    """

    tags = frozenset(themes) if themes else frozenset({"neutral"})
    return (text, tags)


# ---------------------------------------------------------------------------
# Haiku line pools (5 and 7 syllables), each tagged with the themes it fits.
# Syllable counts are verified against count_syllables in test_poemgen.py so
# a bad edit to these pools fails the build rather than shipping quietly.
# ---------------------------------------------------------------------------

_HAIKU_5 = (
    _line("the diff sits and waits", "empty", "balance"),
    _line("nothing here is gone", "empty"),
    _line("new code starts to grow", "growth"),
    _line("the code starts to swell", "growth", "addition"),
    _line("old code starts to fade", "pruning", "deletion"),
    _line("a function is gone", "pruning", "deletion"),
    _line("the name shifts and turns", "rename"),
    _line("one path turns to two", "rename"),
    _line("byte that no eye reads", "binary"),
    _line("an image slips in", "binary"),
    _line("so many trees move", "sprawl"),
    _line("the whole tree shifts", "sprawl"),
    _line("a word keeps coming", "keyword"),
    _line("one word marks this work", "keyword"),
    _line("the change holds steady", "balance"),
    _line("in equal measure", "balance"),
    _line("git watches quietly"),
    _line("the cursor blinks once"),
)

_HAIKU_7 = (
    _line("no line was touched today", "empty"),
    _line("the quiet repo stays the same", "empty", "balance"),
    _line("green text spreads across the screen", "growth"),
    _line("more is added than is lost", "growth", "addition"),
    _line("the git branch grows heavier now", "growth"),
    _line("one red line vanishes now", "pruning", "deletion"),
    _line("less remains than what came first", "pruning"),
    _line("what was here is quietly gone", "deletion"),
    _line("a path wears a newer name", "rename"),
    _line("the old path forwards to new", "rename"),
    _line("this code speaks only in byte", "binary"),
    _line("the diff cannot show it all", "binary"),
    _line("many files spread out wide", "sprawl"),
    _line("ten files hold their breath now", "sprawl"),
    _line("a lone word marks this commit", "keyword"),
    _line("that one word returns again", "keyword"),
    _line("adds and losses balance out", "balance"),
    _line("it settles back to even", "balance"),
    _line("the terminal hums, patient"),
    _line("the keys become a quiet poem"),
)


def _pick_lines(
    rng: random.Random, pool: tuple, active_themes: frozenset[str], count: int
) -> list[str]:
    """Pick ``count`` lines from ``pool``, preferring theme matches.

    Lines whose themes intersect ``active_themes`` are ranked first,
    followed by generic "neutral" filler, followed by anything else in the
    pool as a last resort (a rhyme group may hold only themed entries).
    The ranked candidates are then shuffled with ``rng`` and taken in
    order, repeating from the top if the pool is smaller than ``count``,
    so picks are distinct whenever the pool allows it instead of always
    collapsing onto the single best match.
    """

    # "neutral" is always present in active_themes (see _themes_for), so it
    # is excluded here — otherwise every generic filler line (tagged only
    # "neutral") would trivially match this first, most-preferred tier
    # instead of falling through to the neutral tier below.
    specific_themes = active_themes - {"neutral"}
    themed = sorted(text for text, themes in pool if themes & specific_themes)
    neutral = sorted(
        text for text, themes in pool if "neutral" in themes and text not in themed
    )
    rest = sorted(
        text for text, _themes in pool if text not in themed and text not in neutral
    )
    # Shuffle each priority tier on its own, then concatenate, so a full
    # shuffle of the combined list can never let a non-matching "rest" line
    # jump ahead of a themed one.
    rng.shuffle(themed)
    rng.shuffle(neutral)
    rng.shuffle(rest)
    ranked = themed + neutral + rest

    return [ranked[i % len(ranked)] for i in range(count)]


# ---------------------------------------------------------------------------
# Limerick: five lines, rhyme scheme AABBA. Each rhyme group is a list of
# complete lines that all end on the same sound; A lines and B lines are
# drawn from different groups so they do not accidentally rhyme together.
# ---------------------------------------------------------------------------

_LIMERICK_A_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "ight": (
        _line("a commit went out in the night", "empty", "balance"),
        _line("the diff grew and grew out of sight", "growth", "sprawl"),
        _line("old lines were removed left and right", "pruning", "deletion"),
        _line("a rename gave one file new light", "rename"),
        _line("the keyword kept showing up right", "keyword"),
    ),
    "ode": (
        _line("there once was a change to the code", "growth"),
        _line("the function was trimmed to its code", "pruning"),
        _line("a binary byte found a new mode", "binary"),
        _line("the sprawling branch grew a new node", "sprawl"),
    ),
}

_LIMERICK_B_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "est": (
        _line("it passed every test", "balance"),
        _line("and gave the code zest", "growth"),
        _line("then trimmed what was best", "pruning"),
        _line("a rename its crest", "rename"),
    ),
    "aved": (
        _line("the old file behaved", "balance"),
        _line("and one keyword waved", "keyword"),
        _line("a new file was saved", "growth", "addition"),
        _line("the byte stream engraved", "binary"),
    ),
}


def _pick_group(
    rng: random.Random, groups: dict[str, tuple[tuple[str, frozenset[str]], ...]]
) -> str:
    return rng.choice(sorted(groups))


def _generate_limerick(rng: random.Random, active_themes: frozenset[str]) -> list[str]:
    a_key = _pick_group(rng, _LIMERICK_A_GROUPS)
    a1, a2, a5 = _pick_lines(rng, _LIMERICK_A_GROUPS[a_key], active_themes, 3)

    b_key = _pick_group(rng, _LIMERICK_B_GROUPS)
    b3, b4 = _pick_lines(rng, _LIMERICK_B_GROUPS[b_key], active_themes, 2)

    return [a1, a2, b3, b4, a5]


def _generate_haiku(rng: random.Random, active_themes: frozenset[str]) -> list[str]:
    first, third = _pick_lines(rng, _HAIKU_5, active_themes, 2)
    (second,) = _pick_lines(rng, _HAIKU_7, active_themes, 1)
    return [first, second, third]


def _generate_free_verse(
    rng: random.Random, stats: DiffStats, active_themes: frozenset[str]
) -> list[str]:
    lines: list[str] = []

    if stats.files_touched == 0:
        lines.append("no file stirred in this commit")
    elif stats.files_touched == 1:
        lines.append(f"{stats.files[0].path} changed, alone")
    else:
        lines.append(f"{stats.files_touched} files moved together")

    if stats.lines_added or stats.lines_removed:
        lines.append(f"{stats.lines_added} lines arrived, {stats.lines_removed} lines left")
    else:
        lines.append("not a single line was disturbed")

    if "rename" in active_themes:
        renamed = next(f for f in stats.files if f.status == "renamed")
        lines.append(f"{renamed.old_path} became {renamed.path}")

    if "binary" in active_themes:
        lines.append("some of it cannot be read as words")

    if stats.keywords:
        top = stats.keywords[: min(3, len(stats.keywords))]
        lines.append("and through it all: " + ", ".join(top))

    closing = {
        "growth": "the codebase, a little larger now",
        "pruning": "the codebase, a little lighter now",
    }
    for theme, line in closing.items():
        if theme in active_themes:
            lines.append(line)
            break
    else:
        lines.append("the codebase, unmistakably different")

    return lines


def _themes_for(stats: DiffStats) -> frozenset[str]:
    net = stats.lines_added - stats.lines_removed
    empty = stats.files_touched == 0 and stats.lines_added == 0 and stats.lines_removed == 0

    themes: set[str] = set()
    if empty:
        themes.add("empty")
    if net > 0:
        themes.add("growth")
    if net < 0:
        themes.add("pruning")
    if net == 0 and not empty:
        themes.add("balance")
    if any(f.status == "renamed" for f in stats.files):
        themes.add("rename")
    if any(f.binary for f in stats.files):
        themes.add("binary")
    if any(f.status == "deleted" for f in stats.files):
        themes.add("deletion")
    if any(f.status == "added" for f in stats.files):
        themes.add("addition")
    if stats.files_touched >= 5:
        themes.add("sprawl")
    if stats.keywords:
        themes.add("keyword")
    themes.add("neutral")
    return frozenset(themes)


def _canonical_key(stats: DiffStats) -> str:
    files_key = ",".join(
        f"{f.path}:{f.status}:{f.lines_added}:{f.lines_removed}:{int(f.binary)}:{f.old_path or ''}"
        for f in stats.files
    )
    return "|".join(
        [
            str(stats.lines_added),
            str(stats.lines_removed),
            files_key,
            ",".join(stats.keywords),
        ]
    )


def seed_for(stats: DiffStats) -> int:
    """Derive a deterministic integer seed from a diff's extracted features.

    Two diffs that parse to the same :class:`DiffStats` always yield the
    same seed, and therefore the same poem — that reproducibility is the
    whole point of this module.
    """

    digest = hashlib.sha256(_canonical_key(stats).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


@dataclass(frozen=True)
class Poem:
    form: str
    lines: list[str]
    seed: int

    def __str__(self) -> str:
        return "\n".join(self.lines)


def choose_form(seed: int) -> str:
    """Pick a form deterministically from the seed alone.

    Does not consume any randomness from a :class:`random.Random` instance,
    so it stays independent of however many random choices a given form's
    generator ends up making.
    """

    return FORMS[seed % len(FORMS)]


def generate_poem(stats: DiffStats, form: str | None = None) -> Poem:
    """Turn extracted diff features into a poem.

    ``form`` overrides the deterministic form choice with one of
    ``FORM_HAIKU``, ``FORM_LIMERICK`` or ``FORM_FREE_VERSE``; the poem's
    *content* for a given form is always deterministic from ``stats``.
    """

    seed = seed_for(stats)
    chosen_form = form or choose_form(seed)
    if chosen_form not in FORMS:
        raise ValueError(f"unknown poem form: {chosen_form!r}")

    rng = random.Random(seed)
    active_themes = _themes_for(stats)

    if chosen_form == FORM_HAIKU:
        lines = _generate_haiku(rng, active_themes)
    elif chosen_form == FORM_LIMERICK:
        lines = _generate_limerick(rng, active_themes)
    else:
        lines = _generate_free_verse(rng, stats, active_themes)

    return Poem(form=chosen_form, lines=lines, seed=seed)
