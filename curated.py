"""
Curated Amiga library: filename/title -> shelf genre and IGDB search hints.

The curated library captures human-reviewed decisions so future runs need less
manual correction. Populate it with import_curated.py from a sorted folder.
"""

import json
import re
from pathlib import Path

# Applied when no per-file curated entry exists. Longest matching rule wins.
_SHELF_GENRE_RULES = (
    (
        (
            "dungeon master",
            "eye of the beholder",
            "bard's tale",
            "bard's tale ii",
            "eotb",
        ),
        "Dungeon Crawlers",
    ),
    (("gauntlet",), "Hack and Slash"),
    (("dungeon quest",), "Text Adventure"),
    (("hack.adf", "hack"), "Rogue-Likes"),
    (
        (
            "covert action",
            "hostages",
            "paperboy",
        ),
        "Action",
    ),
    (("cannon fodder",), "Real Time Strategy (RTS)"),
    (("barbarian",), "Platform"),
    (("another world", "out of this world"), "Platform"),
    (("amberstar", "ambermoon", "amber"), "Role-playing (RPG)"),
)


def default_curated_library_path():
    return Path(__file__).resolve().parent / "curated_library.json"


def load_curated_library(path=None):
    library_path = Path(path) if path else default_curated_library_path()
    if not library_path.is_file():
        return {}
    try:
        with library_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    entries = data.get("entries", data)
    normalized = {}
    for key, value in entries.items():
        if not isinstance(value, dict):
            continue
        normalized[key.strip().lower()] = value
    return normalized


def lookup_curated_entry(file_path, parsed_title, library):
    if not library:
        return None
    path = Path(getattr(file_path, "name", file_path))
    keys = (
        path.name.lower(),
        path.stem.lower(),
        parsed_title.lower(),
        re.sub(r"[\s_-]+", "", parsed_title.lower()),
    )
    for key in keys:
        entry = library.get(key)
        if entry:
            return entry
    return None


def curated_search_titles(entry):
    if not entry:
        return []
    titles = []
    for key in ("search_titles", "search_title", "igdb_title"):
        value = entry.get(key)
        if not value:
            continue
        if isinstance(value, list):
            titles.extend(str(item).strip() for item in value if str(item).strip())
        else:
            titles.append(str(value).strip())
    deduped = []
    for title in titles:
        if not any(existing.lower() == title.lower() for existing in deduped):
            deduped.append(title)
    return deduped


def curated_genre(entry):
    if not entry:
        return None
    genre = entry.get("genre") or entry.get("shelf_genre")
    return str(genre).strip() if genre else None


def apply_shelf_genre_rules(parsed_title, matched_name, igdb_genre):
    """Map IGDB metadata to collector-friendly shelf names."""
    haystacks = [
        (parsed_title or "").lower(),
        (matched_name or "").lower(),
    ]
    best_genre = None
    best_len = -1
    for needles, shelf_genre in _SHELF_GENRE_RULES:
        for needle in needles:
            for haystack in haystacks:
                if needle in haystack and len(needle) > best_len:
                    best_genre = shelf_genre
                    best_len = len(needle)
    return best_genre or igdb_genre


def resolve_shelf_genre(
    file_path,
    parsed_title,
    matched_name,
    igdb_genre,
    library,
    genre_override=None,
    curated_entry=None,
):
    if genre_override:
        return genre_override, "override"
    entry = curated_entry or lookup_curated_entry(file_path, parsed_title, library)
    curated = curated_genre(entry)
    if curated:
        return curated, "curated"
    if igdb_genre:
        return apply_shelf_genre_rules(parsed_title, matched_name, igdb_genre), "matched"
    return None, None
