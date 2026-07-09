"""
Heuristics for turning a messy game filename into clean, searchable game titles.

Handles scene-release names, No-Intro/TOSEC ROM tags, and common retro
disk-image naming (disk suffixes, hardware tags, glued lowercase names).
"""

import json
import re
import sys
from pathlib import Path

# Note: "World" is deliberately excluded - it's handled in "(World)" via brackets.
_REGION_TOKENS = (
    r"USA|Europe|EUR|Japan|JPN|Asia|Australia|Korea|China|"
    r"Taiwan|Brazil|France|Germany|GER|Italy|Spain|SPA|"
    r"Netherlands|Sweden|SWE|Russia|RUS|Scandinavia|Unl|Unk"
)

_PLATFORM_TOKENS = (
    r"Amiga|Atari ?2600|Atari ?5200|Atari ?7800|Atari ?ST|Atari|DOS|MS-?DOS|PC|"
    r"NES|SNES|Genesis|Mega ?Drive|GBA|GBC|GB|N64|PS1|PSX|PS2|PS3|PS4|PS5|PSP|"
    r"Xbox ?360|Xbox ?One|Xbox|Commodore ?64|C64|MSX|ZX ?Spectrum|Spectrum|"
    r"Dreamcast|Saturn|3DO|TurboGrafx(?:-?16)?|Neo ?Geo|Arcade|Wii ?U|Wii|Switch|"
    r"OCS|AGA|ECS"
)

_SCENE_GROUPS = (
    r"CODEX|PLAZA|SKIDROW|RELOADED|HOODLUM|CPY|FLT|TENOKE|RUNE|FAIRLIGHT|PROPHET|"
    r"DARKSiDERS|DARKSIDERS|RAZOR1911|RAZOR|DEViANCE|DEVIANCE|VITALITY|POSTMORTEM|"
    r"FASiSO|EMPRESS|FitGirl|DODI|KaOs|GOG|ElAmigos|Xatab|ANOMALY|SiMPLEX|3DM|"
    r"P2P|RG ?Mechanics"
)

_EDITION_QUALIFIERS = (
    r"Game of the Year Edition|GOTY Edition|GOTY|Complete Edition|Definitive Edition|"
    r"Ultimate Edition|Deluxe Edition|Gold Edition|Enhanced Edition|Anniversary Edition|"
    r"Special Edition|Collector'?s Edition|Remastered|HD Remaster|Director'?s Cut|"
    r"Extended Cut|Redux|Xmas Edition|Christmas Edition"
)

# Avoid matching plain "- d1" disk suffixes; TOSEC "(Disk 1 of 2)" is removed via brackets.
_IMAGE_DESCRIPTORS = (
    r"boxart|box[\s_-]?art|cover|front|back|spine|"
    r"cart(?:ridge)?|label|screenshot[s]?|logo|wheel|banner|fanart|"
    r"clearlogo|marquee|title[\s_-]?screen|gameplay|thumb(?:nail)?|art|map|runes"
)

_TAG_KEYWORDS = (
    r"REPACK|PROPER|RETAIL|READNFO|INTERNAL|UNCUT|MULTi\d*|CRACKED?|CRACK[- ]?ONLY|"
    r"UPDATE ?\d*|BUILD ?\d+|v\d+(?:\.\d+)*|Rev ?[A-Za-z0-9]+|Setup|Installer|Unlocked|"
    r"data disk"
)

# Amiga ADF / TOSEC disk-volume suffixes stripped after tag cleanup.
_DISK_SUFFIX_PATTERNS = (
    re.compile(r"\s*-\s*d\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"-d\d+\s*$", re.IGNORECASE),
    re.compile(r"-\d+\s*$"),
    re.compile(r"_\d+\s*$"),
    re.compile(r"\s+\d\s*$"),
    re.compile(r"\s+save\s*$", re.IGNORECASE),
    re.compile(r"(?<=\d)[\s_-]+challenge\s*$", re.IGNORECASE),
    re.compile(r"(?<=\d)\s+challenge\s*$", re.IGNORECASE),
    re.compile(r"[\s_-]*disk\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"(?<=\d)[aAbB]$"),
)

# Scene acronyms: short filename -> full IGDB-searchable title.
_ACRONYMS = {}
_ACRONYM_DEFAULTS = {
    "icftd": "It Came from the Desert",
    "synd": "Syndicate",
    "stooges": "The Three Stooges",
    "sinbad": "Sinbad and the Throne of the Falcon",
}
_ACRONYM_FILE_NAMES = ("acronyms.json", "amiga_acronyms.json")


def _acronyms_path():
    base = Path(__file__).resolve().parent
    for name in _ACRONYM_FILE_NAMES:
        path = base / name
        if path.is_file():
            return path
    return base / _ACRONYM_FILE_NAMES[0]


def _load_acronyms():
    _ACRONYMS.clear()
    _ACRONYMS.update(_ACRONYM_DEFAULTS)
    path = _acronyms_path()
    if not path.is_file():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        for key, value in data.items():
            _ACRONYMS[key.strip().lower()] = value.strip()
        if path.name == "amiga_acronyms.json":
            print(
                f"Note: loaded legacy {path.name}; rename to acronyms.json when convenient.",
                file=sys.stderr,
            )
    except json.JSONDecodeError as exc:
        print(
            f"Warning: could not load {path.name} ({exc}); using built-in acronyms only.",
            file=sys.stderr,
        )
    except (OSError, AttributeError) as exc:
        print(f"Warning: could not load {path.name} ({exc}).", file=sys.stderr)


def reload_acronyms():
    """Reload acronyms.json (call after editing the file)."""
    _load_acronyms()


reload_amiga_acronyms = reload_acronyms


_load_acronyms()

# Filename-specific fixes (applied before glue-word expansion).
_ABBREVIATION_FIXES = {
    "attak": "attack",
    "aquventura": "aqua venture",
    "bardstale": "bard's tale",
    "abreed": "alien breed",
    "lethalxs": "lethal xcess",
    "kickoff": "kick off",
    "kingofchicago": "king of chicago",
    "newzealandstory": "new zealand story",
    "headoverheels": "head over heels",
    "maniacmansion": "maniac mansion",
    "magicpockets": "magic pockets",
    "marblemadness": "marble madness",
    "themepa": "theme park",
    "tetrispro": "tetris pro",
    "tvsportbasketball": "tv sports basketball",
    "dungeonquest": "dungeon quest",
    "timesoflore": "times of lore",
    "zakmckraken": "zak mckracken",
    "f18interceptor": "f-18 interceptor",
    "shadowofthebeast": "shadow of the beast",
    "shadowofthebeast2": "shadow of the beast 2",
    "shadowofthebeast3": "shadow of the beast 3",
}

_BRACKET_PATTERN = re.compile(r"[\[\(\{][^\[\]\(\)\{\}]*[\]\)\}]")
_LEFTOVER_BRACKET_CHARS = re.compile(r"[\[\]\(\)\{\}]")
_LEADING_NUMBER_PATTERN = re.compile(r"^\s*\d{1,3}[\s.\-_]+")
_TRAILING_ARTICLE_PATTERN = re.compile(r"^(.*),\s*(The|A|An)\s*$", re.IGNORECASE)
_MULTISPACE_PATTERN = re.compile(r"\s{2,}")
_TRAILING_SEPARATORS_PATTERN = re.compile(r"^[\s\-_.,]+|[\s\-_.,]+$")
_CAMEL_SPLIT_PATTERN = re.compile(r"([a-z])([A-Z])")
_ACRONYM_SPLIT_PATTERN = re.compile(r"([A-Z]+)([A-Z][a-z])")
_SEQUEL_NUMBER_PATTERN = re.compile(r"([^\d\s])(\d+)$")
_DIGIT_LETTER_SPLIT_PATTERN = re.compile(r"^(\d+)([A-Za-z])")
_WORD_HYPHEN_PATTERN = re.compile(r"(?<=[A-Za-z])-(?=[A-Za-z])")
_SCENE_ACRONYM_PATTERN = re.compile(r"^([A-Za-z]{3,10})(\d{1,2})$")

# Common English words glued into lowercase Amiga filenames (longest first).
_GLUE_WORDS = sorted(
    [
        "commando", "squadron", "palace", "nights", "dragon", "beast", "beyond",
        "blood", "money", "moves", "tiger", "bubble", "bobble", "barbarian",
        "altered", "another", "arabian", "archon", "arkanoid", "attack", "breed",
        "cannon", "fodder", "fever", "world", "after", "night", "lord", "lords",
        "star", "tale", "black", "bionic", "birds", "prey", "beach", "volley",
        "army", "war", "double", "dungeon", "master", "quest",
        "populous", "gauntlet", "lotus", "manic", "mansion", "marble", "madness",
        "magic", "pocket", "pockets", "head", "heel", "heels", "over", "zealand",
        "story", "rising", "sun", "desert", "king", "chicago",
        "kick", "off", "lethal", "project", "prince", "persia", "zak", "mckracken",
        "shadow", "tetris", "theme", "park", "sport", "sports", "basket", "ball",
        "basketball", "ultima", "vikings", "viking", "lost", "california", "drive",
        "test", "syndicate", "sinbad", "throne", "falcon", "three", "stooges", "pro",
        "silent", "service", "submarine", "simulation", "interceptor", "lore", "times",
    ],
    key=len,
    reverse=True,
)

_ROMAN_NUMERALS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

# Expansion/data-disk suffixes: search the base game title too (for genre inheritance).
_BASE_GAME_SUFFIX_PATTERNS = (
    re.compile(r"\s*[-+]\s*extra missions\s*$", re.IGNORECASE),
    re.compile(r"\s*[-+]\s*expansion(?:\s+pack)?\s*$", re.IGNORECASE),
    re.compile(r"\s*[-+]\s*data disk\s*$", re.IGNORECASE),
    re.compile(r"\s*-\s*california challenge\s*$", re.IGNORECASE),
    re.compile(r"\s*-\s*advanced mission disk\s*$", re.IGNORECASE),
    re.compile(r"\s*-\s*the submarine simulation\s*$", re.IGNORECASE),
    re.compile(r"\s*-\s*intern\s*edit\s*$", re.IGNORECASE),
)


def _insert_glued_word(spaced, word):
    pattern = re.compile(r"(?:^|(?<=[a-z]))" + re.escape(word) + r"(?=[a-z]|$)", re.IGNORECASE)
    return pattern.sub(f" {word} ", spaced)


def _expand_scene_acronym(text):
    """Expand scene acronyms like ICFTD21 -> It Came from the Desert."""
    compact = re.sub(r"[\s_-]+", "", text)
    match = _SCENE_ACRONYM_PATTERN.match(compact)
    if match:
        acronym, _digits = match.groups()
        expanded = _ACRONYMS.get(acronym.lower())
        if expanded:
            return expanded

    expanded = _ACRONYMS.get(compact.lower())
    if expanded:
        return expanded
    return text


def _strip_keyword_group(text, keywords_pattern):
    pattern = re.compile(r"(?<!\w)(?:" + keywords_pattern + r")(?!\w)", re.IGNORECASE)
    return pattern.sub(" ", text)


def _normalize_word_hyphens(text):
    """marble-madness -> marble madness (but preserve A-10)."""
    return _WORD_HYPHEN_PATTERN.sub(" ", text)


def _strip_disk_suffixes(text):
    result = text
    changed = True
    while changed:
        changed = False
        for pattern in _DISK_SUFFIX_PATTERNS:
            updated = pattern.sub("", result).strip()
            if updated != result:
                result = updated
                changed = True
    return result


def _title_case_words(text):
    return " ".join(word.capitalize() if word.islower() else word for word in text.split())


def _split_sequel_number(text):
    return _SEQUEL_NUMBER_PATTERN.sub(r"\1 \2", text)


def _split_camel_case(text):
    text = _CAMEL_SPLIT_PATTERN.sub(r"\1 \2", text)
    text = _ACRONYM_SPLIT_PATTERN.sub(r"\1 \2", text)
    return text


def _split_leading_number(text):
    return _DIGIT_LETTER_SPLIT_PATTERN.sub(r"\1 \2", text)


def _abbreviation_stems(compact):
    """Strip trailing disk/sequel digits or floppy sides for dictionary lookup."""
    stems = [compact]
    stripped = re.sub(r"(\d+|[ab])$", "", compact, flags=re.IGNORECASE)
    if stripped and stripped != compact:
        stems.append(stripped)
    return stems


def _lookup_abbreviation(text):
    compact = re.sub(r"[\s_-]+", "", text.lower())
    spaced = text.lower().strip()

    for candidate in (compact, spaced):
        if candidate in _ABBREVIATION_FIXES:
            fixed = _ABBREVIATION_FIXES[candidate]
            return _title_case_words(fixed) if " " in fixed else fixed.title()
        if candidate in _ACRONYMS:
            return _ACRONYMS[candidate]

    for stem in _abbreviation_stems(compact):
        if stem in _ABBREVIATION_FIXES:
            fixed = _ABBREVIATION_FIXES[stem]
            result = _title_case_words(fixed) if " " in fixed else fixed.title()
            suffix = compact[len(stem) :]
            if suffix.isdigit() and int(suffix) >= 2:
                return f"{result} {int(suffix)}"
            return result
        if stem in _ACRONYMS:
            result = _ACRONYMS[stem]
            suffix = compact[len(stem) :]
            if suffix.isdigit() and int(suffix) >= 2:
                return f"{result} {int(suffix)}"
            return result

    return None


def _fix_abbreviations(text):
    matched = _lookup_abbreviation(text)
    if matched:
        return matched

    spaced = text.lower().strip()
    for src, dst in sorted(_ABBREVIATION_FIXES.items(), key=lambda item: len(item[0]), reverse=True):
        if src in spaced:
            return _title_case_words(spaced.replace(src, dst))
    return text


def _expand_glued_title(text, allow_spaced=False):
    """
    Split run-together names like doubledragon2 or dungeonmaster into words.
    Handles trailing sequel digits (e.g. doubledragon2 -> Double Dragon 2).
    """
    if not text.isascii():
        return text
    if not allow_spaced and " " in text.strip():
        return text

    compact = re.sub(r"\s+", "", text)
    if compact.lower() in _ABBREVIATION_FIXES:
        return text
    sequel = ""
    sequel_match = re.search(r"(\d+)$", compact)
    if sequel_match:
        sequel = sequel_match.group(1)
        core = compact[: sequel_match.start()]
    else:
        core = compact

    if not core.isalpha() or len(core) < 6:
        return text

    spaced = core.lower()
    for word in _GLUE_WORDS:
        spaced = _insert_glued_word(spaced, word)

    spaced = _MULTISPACE_PATTERN.sub(" ", spaced).strip()
    if spaced == core.lower():
        return text

    result = _title_case_words(spaced)
    if sequel:
        result = f"{result} {sequel}"
    return result


def _split_glued_lowercase(text):
    """Backward-compatible alias for glued-name expansion."""
    return _expand_glued_title(text)


def _roman_sequel_variants(text):
    """barbarian 2 -> barbarian II, etc."""
    match = re.match(r"^(.*?)[\s-]+(\d+)$", text.strip())
    if not match:
        return []

    base, number_text = match.groups()
    try:
        number = int(number_text)
    except ValueError:
        return []

    roman = _ROMAN_NUMERALS.get(number)
    if not roman:
        return []

    titled_base = _title_case_words(base.strip())
    return [f"{titled_base} {roman}", f"{titled_base} {number}"]


def _base_game_variants(text):
    """Strip expansion/data-disk suffixes to search the parent game."""
    variants = []
    for pattern in _BASE_GAME_SUFFIX_PATTERNS:
        stripped = pattern.sub("", text).strip()
        if stripped and stripped.lower() != text.lower():
            variants.append(stripped)
    return variants


def clean_title(filename_stem):
    """Turn a filename (without extension) into a best-guess game title."""
    text = filename_stem.replace("_", " ")

    text = _LEADING_NUMBER_PATTERN.sub("", text)

    without_brackets = _BRACKET_PATTERN.sub(" ", text)
    while _BRACKET_PATTERN.search(without_brackets):
        without_brackets = _BRACKET_PATTERN.sub(" ", without_brackets)
    if without_brackets.strip():
        text = without_brackets

    text = _strip_keyword_group(text, _TAG_KEYWORDS)
    text = text.replace(".", " ")

    text = _strip_keyword_group(text, _SCENE_GROUPS)
    text = _strip_keyword_group(text, _EDITION_QUALIFIERS)
    text = _strip_keyword_group(text, _IMAGE_DESCRIPTORS)
    text = _strip_keyword_group(text, _REGION_TOKENS)
    text = _strip_keyword_group(text, _PLATFORM_TOKENS)

    text = _LEFTOVER_BRACKET_CHARS.sub(" ", text)

    article_match = _TRAILING_ARTICLE_PATTERN.match(text.strip())
    if article_match:
        body, article = article_match.groups()
        text = f"{article} {body}".strip()

    text = _strip_disk_suffixes(text)
    text = _normalize_word_hyphens(text)
    text = _TRAILING_SEPARATORS_PATTERN.sub("", text)
    text = _MULTISPACE_PATTERN.sub(" ", text).strip()

    fixed = _lookup_abbreviation(text)
    if fixed:
        text = fixed
    else:
        sequelled = _split_sequel_number(text)
        if sequelled != text:
            text = _title_case_words(sequelled)

    return text


def search_title_variants(parsed_title):
    """
    Build ordered IGDB search candidates from a parsed title.
    Earlier variants are preferred; duplicates are omitted.
    """
    variants = []

    def add(value):
        value = _MULTISPACE_PATTERN.sub(" ", value).strip()
        if not value:
            return
        titled = _title_case_words(value)
        for index, existing in enumerate(variants):
            if existing.lower() == value.lower():
                if value == titled and existing.islower() and not value.islower():
                    variants[index] = value
                return
        variants.append(value)

    add(parsed_title)
    add(_title_case_words(parsed_title))
    add(_expand_scene_acronym(parsed_title))
    add(_split_camel_case(parsed_title))
    add(_split_leading_number(parsed_title))
    add(_fix_abbreviations(parsed_title))
    add(_fix_abbreviations(_split_leading_number(parsed_title)))
    sequel_split = _split_sequel_number(parsed_title)
    add(sequel_split)
    add(_title_case_words(sequel_split))
    add(_fix_abbreviations(sequel_split))
    sequel_base = re.sub(r"[\s_-]*\d+$", "", sequel_split).strip()
    if sequel_base.lower() != sequel_split.lower():
        add(_fix_abbreviations(sequel_base))
    add(_expand_glued_title(parsed_title))
    if sequel_split.count(" ") == 1 and len(re.sub(r"\s+", "", sequel_split)) < 18:
        add(_expand_glued_title(sequel_split, allow_spaced=True))

    for base_variant in _base_game_variants(parsed_title):
        add(base_variant)

    expanded_sequel = (
        _expand_glued_title(sequel_split, allow_spaced=True)
        if sequel_split.count(" ") == 1 and len(re.sub(r"\s+", "", sequel_split)) < 18
        else sequel_split
    )
    if expanded_sequel.lower() != sequel_split.lower():
        add(expanded_sequel)
    roman_source = (
        expanded_sequel
        if expanded_sequel.lower() != sequel_split.lower()
        else _title_case_words(sequel_split)
    )
    for roman_variant in _roman_sequel_variants(roman_source):
        add(roman_variant)

    return variants


if __name__ == "__main__":
    samples = [
        "4D Sports Driving (1990)(Mindscape)[cr CSL](Disk 1 of 2).adf",
        "agony(ocs) - d1.adf",
        "alteredbeast - d1.adf",
        "Another world_1.adf",
        "afterthewar.adf",
        "ABreed-d1.adf",
        "barbarian2 - d1.adf",
        "688attak.adf",
        "doubledragon2.adf",
        "dungeonmaster.adf",
        "Amiga Tetris (1987)(Spectrum HoloByte)[cr Defjam - RSi].adf",
        "A-10 Tank Killer - Extra Missions (1990)(Sierra)[data disk].adf",
    ]
    for s in samples:
        stem = s.rsplit(".", 1)[0]
        cleaned = clean_title(stem)
        print(f"{s}")
        print(f"  clean: {cleaned!r}")
        print(f"  search: {search_title_variants(cleaned)}")
        print()
