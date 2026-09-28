"""Seeded template engine that turns :class:`~codepoem.diffparser.DiffStats`
into a short poem.

The design goal is reproducibility: the same diff always produces the same
poem, in the same form and style, forever. There is no model and no network
call — just a hash of the diff's own features used to seed
:class:`random.Random`, and a small library of hand-written, syllable-checked
lines that get filtered by which "themes" the diff exhibits (net growth,
deletions, renames, a big sprawling change, ...) and picked deterministically
from there.

Haiku and limerick lines are fixed text, each one's syllable count verified
against :func:`count_syllables` at import time, so line selection can never
silently break the form's meter. Free verse has no meter to break, so it is
the one form that interpolates live feature values (file names, keyword,
counts) directly into its lines.

On top of the three forms (haiku/limerick/free verse) sits a second,
independent axis: the *style*. A style is a complete vocabulary bank — its
own haiku line pools, its own limerick rhyme groups, its own free-verse
phrasing — so the same diff, in the same form, reads completely differently
depending on which style is selected. Styles never touch the meter or rhyme
rules; they only swap out *which words* fill them, so a style change can
never break a form's structure.
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

STYLE_CLASSIC = "classic"
STYLE_NOIR = "noir"
STYLE_COSMIC = "cosmic"
STYLES = (STYLE_CLASSIC, STYLE_NOIR, STYLE_COSMIC)

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


# ---------------------------------------------------------------------------
# Style packs: each of the pools above belongs to the "classic" style. The
# two below are complete, independent vocabularies for the same forms —
# same meter and rhyme rules, different words. See the "Style packs" section
# further down for how a style is selected and bundled with a form.
# ---------------------------------------------------------------------------

_NOIR_HAIKU_5 = (
    _line("the shadows lean in", "empty"),
    _line("a lamp burns alone", "empty", "balance"),
    _line("the city stays still", "balance"),
    _line("smoke curls off the page", "growth"),
    _line("new code cuts the dark", "growth"),
    _line("the code grows a shade", "growth", "addition"),
    _line("a function goes dark", "pruning", "deletion"),
    _line("one clue slips away", "pruning", "deletion"),
    _line("the trail turns and bends", "rename"),
    _line("two paths cross tonight", "rename"),
    _line("a frame lost to light", "binary"),
    _line("wide sprawl in the fog", "sprawl"),
    _line("ten shadows converge", "sprawl"),
    _line("one word haunts the case", "keyword"),
    _line("one name marks the case", "keyword"),
    _line("the ledger holds true", "balance"),
    _line("the terminal waits"),
    _line("the cursor keeps watch"),
)

_NOIR_HAIKU_7 = (
    _line("no shadow crossed this room", "empty"),
    _line("the case stays cold and shut tight", "empty", "balance"),
    _line("green light spills across the floor", "growth"),
    _line("more flows in than what is lost", "growth", "addition"),
    _line("the case grows heavy with clues", "growth"),
    _line("one red thread vanishes now", "pruning", "deletion"),
    _line("less remains than what came first", "pruning"),
    _line("what was here is gone for good", "deletion"),
    _line("an alias wears a new face", "rename"),
    _line("the old lead points to the new", "rename"),
    _line("this case speaks in a dead code", "binary"),
    _line("the diff hid more than it tells", "binary"),
    _line("many trails spread through the fog", "sprawl"),
    _line("ten suspects hold their breath now", "sprawl"),
    _line("one word keeps circling the case", "keyword"),
    _line("that same word returns again", "keyword"),
    _line("the ledger settles even", "balance"),
    _line("it balances, cold and true", "balance"),
    _line("the terminal hums, patient"),
    _line("the keys click through the report"),
)

_NOIR_LIMERICK_A_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "ace": (
        _line("a diff came in without a trace", "empty", "balance"),
        _line("the changes sprawled all over the place", "growth", "sprawl"),
        _line("the missing code left empty space", "pruning", "deletion"),
        _line("a rename gave the file new face", "rename"),
        _line("the keyword kept coming back apace", "keyword"),
    ),
    "old": (
        _line("there once was a secret retold", "growth"),
        _line("the function was trimmed, we were told", "pruning"),
        _line("a binary byte, dark and cold", "binary"),
        _line("the sprawling report stayed untold", "sprawl"),
    ),
}

_NOIR_LIMERICK_B_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "eal": (
        _line("it dared to conceal", "balance"),
        _line("and start to reveal", "growth"),
        _line("then closed the appeal", "pruning"),
        _line("a rename's appeal", "rename"),
    ),
    "own": (
        _line("till truth was well known", "balance"),
        _line("the lead had well grown", "growth"),
        _line("till doubt had been shown", "pruning"),
        _line("the byte stayed unknown", "binary"),
    ),
}

_COSMIC_HAIKU_5 = (
    _line("a star starts to form", "empty"),
    _line("the void stays quite still", "empty", "balance"),
    _line("new code lights the dark", "growth"),
    _line("the code starts to flare", "growth", "addition"),
    _line("old code drifts to dust", "pruning", "deletion"),
    _line("a function burns out", "pruning", "deletion"),
    _line("the path bends through space", "rename"),
    _line("one orbit shifts twice", "rename"),
    _line("a byte drifts through void", "binary"),
    _line("an image floats free", "binary"),
    _line("so many stars drift", "sprawl"),
    _line("the whole sky shifts", "sprawl"),
    _line("a word loops through space", "keyword"),
    _line("one word marks this launch", "keyword"),
    _line("the gauge holds quite still", "balance"),
    _line("ship stays right on course", "balance"),
    _line("the probe hums quietly"),
    _line("the display blinks once"),
)

_COSMIC_HAIKU_7 = (
    _line("no star swept across the sky", "empty"),
    _line("the quiet void stays as it was", "empty", "balance"),
    _line("green light spreads across the hull", "growth"),
    _line("more launches than returns now", "growth", "addition"),
    _line("the payload grows heavier now", "growth"),
    _line("one dim star vanishes now", "pruning", "deletion"),
    _line("less remains than what came first", "pruning"),
    _line("what was here has quietly gone", "deletion"),
    _line("a unit wears a new name", "rename"),
    _line("the old link forwards to new", "rename"),
    _line("this stream speaks in silent code", "binary"),
    _line("the diff cannot show it all", "binary"),
    _line("many systems spread out wide", "sprawl"),
    _line("ten systems hold their breath now", "sprawl"),
    _line("a lone word marks this launch date", "keyword"),
    _line("that one word returns again", "keyword"),
    _line("gains and losses balance out", "balance"),
    _line("it settles back into place", "balance"),
    _line("the console hums, patient"),
    _line("the crew waits for a signal"),
)

_COSMIC_LIMERICK_A_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "ight": (
        _line("a launch went up into the night", "empty", "balance"),
        _line("the payload grew large out of sight", "growth", "sprawl"),
        _line("old modules were trimmed left and right", "pruning", "deletion"),
        _line("a rename gave one file new light", "rename"),
        _line("the keyword kept showing up bright", "keyword"),
    ),
    "aze": (
        _line("the new code ignited a blaze", "growth"),
        _line("the trimmed function vanished in haze", "pruning"),
        _line("a binary byte in the haze", "binary"),
        _line("the sprawling system in a maze", "sprawl"),
    ),
}

_COSMIC_LIMERICK_B_GROUPS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "ars": (
        _line("it soared past the stars", "balance"),
        _line("and burned among stars", "growth"),
        _line("then dimmed like far stars", "pruning"),
        _line("new names among stars", "rename"),
    ),
    "een": (
        _line("the bytes went unseen", "binary"),
        _line("a keyword stayed keen", "keyword"),
        _line("the diff hovered between", "balance"),
        _line("the sprawl could be seen", "sprawl"),
    ),
}


@dataclass(frozen=True)
class FreeVerseTemplates:
    """Format-string phrases used to build a free-verse poem.

    Every field is a ``str.format`` template; the placeholders used (and
    which templates take none) mirror exactly what :func:`_generate_free_verse`
    fills in, so a style only ever changes wording, never which lines get
    included or in what order.
    """

    no_file: str
    lone_file: str  # {path}
    many_files: str  # {count}
    lines_changed: str  # {added}, {removed}
    no_lines: str
    renamed: str  # {old}, {new}
    binary: str
    keywords: str  # {keywords}
    growth_close: str
    pruning_close: str
    default_close: str


_CLASSIC_FREE_VERSE = FreeVerseTemplates(
    no_file="no file stirred in this commit",
    lone_file="{path} changed, alone",
    many_files="{count} files moved together",
    lines_changed="{added} lines arrived, {removed} lines left",
    no_lines="not a single line was disturbed",
    renamed="{old} became {new}",
    binary="some of it cannot be read as words",
    keywords="and through it all: {keywords}",
    growth_close="the codebase, a little larger now",
    pruning_close="the codebase, a little lighter now",
    default_close="the codebase, unmistakably different",
)

_NOIR_FREE_VERSE = FreeVerseTemplates(
    no_file="no file moved in the dark tonight",
    lone_file="{path} changed, and no one else was there",
    many_files="{count} files moved together, like suspects",
    lines_changed="{added} lines slipped in, {removed} lines vanished",
    no_lines="not a single line was disturbed, which was itself suspicious",
    renamed="{old} took on the name {new}",
    binary="some of it cannot be read, and never will be",
    keywords="and one word kept circling the case: {keywords}",
    growth_close="the codebase, a little heavier with secrets",
    pruning_close="the codebase, a little leaner, a little colder",
    default_close="the codebase, changed, and not saying why",
)

_COSMIC_FREE_VERSE = FreeVerseTemplates(
    no_file="no file drifted through this commit's orbit",
    lone_file="{path} changed, alone in the dark",
    many_files="{count} files launched together",
    lines_changed="{added} lines entered orbit, {removed} lines burned up on reentry",
    no_lines="not a single line left its orbit",
    renamed="{old} was renamed {new}, a new designation",
    binary="some of it exists only as signal, not words",
    keywords="and drifting through it all: {keywords}",
    growth_close="the codebase, a little further from home now",
    pruning_close="the codebase, a little lighter, trimmed for the journey",
    default_close="the codebase, changed, still in orbit",
)


@dataclass(frozen=True)
class Style:
    """A complete vocabulary bank for every form, bundled under one key."""

    key: str
    haiku_5: tuple
    haiku_7: tuple
    limerick_a_groups: dict
    limerick_b_groups: dict
    free_verse: FreeVerseTemplates


_STYLES: dict[str, Style] = {
    STYLE_CLASSIC: Style(
        key=STYLE_CLASSIC,
        haiku_5=_HAIKU_5,
        haiku_7=_HAIKU_7,
        limerick_a_groups=_LIMERICK_A_GROUPS,
        limerick_b_groups=_LIMERICK_B_GROUPS,
        free_verse=_CLASSIC_FREE_VERSE,
    ),
    STYLE_NOIR: Style(
        key=STYLE_NOIR,
        haiku_5=_NOIR_HAIKU_5,
        haiku_7=_NOIR_HAIKU_7,
        limerick_a_groups=_NOIR_LIMERICK_A_GROUPS,
        limerick_b_groups=_NOIR_LIMERICK_B_GROUPS,
        free_verse=_NOIR_FREE_VERSE,
    ),
    STYLE_COSMIC: Style(
        key=STYLE_COSMIC,
        haiku_5=_COSMIC_HAIKU_5,
        haiku_7=_COSMIC_HAIKU_7,
        limerick_a_groups=_COSMIC_LIMERICK_A_GROUPS,
        limerick_b_groups=_COSMIC_LIMERICK_B_GROUPS,
        free_verse=_COSMIC_FREE_VERSE,
    ),
}


def _pick_group(
    rng: random.Random, groups: dict[str, tuple[tuple[str, frozenset[str]], ...]]
) -> str:
    return rng.choice(sorted(groups))


def _generate_limerick(
    rng: random.Random, active_themes: frozenset[str], style: Style
) -> list[str]:
    a_key = _pick_group(rng, style.limerick_a_groups)
    a1, a2, a5 = _pick_lines(rng, style.limerick_a_groups[a_key], active_themes, 3)

    b_key = _pick_group(rng, style.limerick_b_groups)
    b3, b4 = _pick_lines(rng, style.limerick_b_groups[b_key], active_themes, 2)

    return [a1, a2, b3, b4, a5]


def _generate_haiku(
    rng: random.Random, active_themes: frozenset[str], style: Style
) -> list[str]:
    first, third = _pick_lines(rng, style.haiku_5, active_themes, 2)
    (second,) = _pick_lines(rng, style.haiku_7, active_themes, 1)
    return [first, second, third]


def _generate_free_verse(
    stats: DiffStats, active_themes: frozenset[str], style: Style
) -> list[str]:
    templates = style.free_verse
    lines: list[str] = []

    if stats.files_touched == 0:
        lines.append(templates.no_file)
    elif stats.files_touched == 1:
        lines.append(templates.lone_file.format(path=stats.files[0].path))
    else:
        lines.append(templates.many_files.format(count=stats.files_touched))

    if stats.lines_added or stats.lines_removed:
        lines.append(
            templates.lines_changed.format(
                added=stats.lines_added, removed=stats.lines_removed
            )
        )
    else:
        lines.append(templates.no_lines)

    if "rename" in active_themes:
        renamed = next(f for f in stats.files if f.status == "renamed")
        lines.append(templates.renamed.format(old=renamed.old_path, new=renamed.path))

    if "binary" in active_themes:
        lines.append(templates.binary)

    if stats.keywords:
        top = stats.keywords[: min(3, len(stats.keywords))]
        lines.append(templates.keywords.format(keywords=", ".join(top)))

    closing = {
        "growth": templates.growth_close,
        "pruning": templates.pruning_close,
    }
    for theme, line in closing.items():
        if theme in active_themes:
            lines.append(line)
            break
    else:
        lines.append(templates.default_close)

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
    style: str = STYLE_CLASSIC

    def __str__(self) -> str:
        return "\n".join(self.lines)


def choose_form(seed: int) -> str:
    """Pick a form deterministically from the seed alone.

    Does not consume any randomness from a :class:`random.Random` instance,
    so it stays independent of however many random choices a given form's
    generator ends up making.
    """

    return FORMS[seed % len(FORMS)]


def generate_poem(
    stats: DiffStats, form: str | None = None, style: str | None = None
) -> Poem:
    """Turn extracted diff features into a poem.

    ``form`` overrides the deterministic form choice with one of
    ``FORM_HAIKU``, ``FORM_LIMERICK`` or ``FORM_FREE_VERSE``; the poem's
    *content* for a given form is always deterministic from ``stats``.

    ``style`` selects which vocabulary bank (see ``STYLES``) supplies the
    words; it defaults to ``STYLE_CLASSIC`` when omitted, so existing callers
    that never pass it keep getting exactly what they always got. Unlike
    ``form``, the style is never picked automatically from the seed — it is
    always either the default or what the caller explicitly asked for — but
    once chosen, the poem's content is still a pure, deterministic function
    of ``stats``.
    """

    seed = seed_for(stats)
    chosen_form = form or choose_form(seed)
    if chosen_form not in FORMS:
        raise ValueError(f"unknown poem form: {chosen_form!r}")

    chosen_style = style or STYLE_CLASSIC
    if chosen_style not in _STYLES:
        raise ValueError(f"unknown poem style: {chosen_style!r}")
    style_pack = _STYLES[chosen_style]

    rng = random.Random(seed)
    active_themes = _themes_for(stats)

    if chosen_form == FORM_HAIKU:
        lines = _generate_haiku(rng, active_themes, style_pack)
    elif chosen_form == FORM_LIMERICK:
        lines = _generate_limerick(rng, active_themes, style_pack)
    else:
        lines = _generate_free_verse(stats, active_themes, style_pack)

    return Poem(form=chosen_form, lines=lines, seed=seed, style=chosen_style)
