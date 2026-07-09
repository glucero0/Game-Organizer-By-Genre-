"""
Recursively scan a folder of game files, identify each game via the IGDB
API, and copy the files into destination subfolders named after the game's
primary genre.

Setup:
    1. Create a Twitch developer application: https://dev.twitch.tv/console/apps
       (Category: "Application Integration"). This gives you a Client ID and
       Client Secret - IGDB authenticates through Twitch.
    2. Copy .env.example to .env and set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.

Example:
    python organize_games.py --source "D:\\Games\\*.adf" --dest "D:\\Organized"
    python organize_games.py --source "D:\\ROMs\\*.zip" --dest "D:\\Organized" --dry-run
    python organize_games.py --source "D:\\Games\\*.adf" --dest "D:\\Organized" --dry-run --unknowns-only

Optional JSON files beside this script (loaded automatically if present):
    platform_defaults.json   — extension -> IGDB platform when --platform is omitted
    igdb_title_aliases.json  — map parsed titles to IGDB search names
    acronyms.json            — expand short scene filenames to full titles
    genre_overrides.json     — map filenames/titles to genre folders
    curated_library.json     — reviewed per-file shelf assignments
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

import requests

from curated import (
    curated_search_titles,
    load_curated_library,
    lookup_curated_entry,
    resolve_shelf_genre,
)
from filename_parser import clean_title, reload_acronyms, search_title_variants
from igdb_client import IGDBClient, MIN_MATCH_SCORE

ORGANIZE_LOG_CSV = "organize_log.csv"
from platform_defaults import load_platform_defaults, resolve_platform_ids

UNKNOWN_GENRE = "Unknown"
_INVALID_FS_CHARS = '<>:"/\\|?*'
_GLOB_CHARS = frozenset("*?[")


def has_glob_pattern(name):
    return any(ch in name for ch in _GLOB_CHARS)


def parse_source_pattern(source_arg):
    """
    Parse --source like D:\\Games\\*.adf into (base_directory, glob_pattern).
    The filename part must contain a glob; there is no default extension.
    """
    source_path = Path(source_arg).expanduser()
    pattern = source_path.name
    if not has_glob_pattern(pattern):
        sys.exit(
            "Error: --source must include a glob pattern in the filename, "
            'e.g. D:\\Games\\*.adf'
        )

    base_dir = source_path.parent.resolve()
    if not base_dir.is_dir():
        sys.exit(f"Error: source directory does not exist: {base_dir}")

    return base_dir, pattern


def sanitize_folder_name(name):
    cleaned = "".join(c for c in name if c not in _INVALID_FS_CHARS).strip(" .")
    return cleaned or UNKNOWN_GENRE


def iter_matching_files(base_dir, pattern):
    for path in base_dir.rglob(pattern):
        if path.is_file():
            yield path


def unique_destination(dest_path):
    if not dest_path.exists():
        return dest_path
    stem, suffix, parent = dest_path.stem, dest_path.suffix, dest_path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def default_genre_overrides_path():
    return Path(__file__).resolve().parent / "genre_overrides.json"


def load_genre_overrides():
    override_path = default_genre_overrides_path()
    if not override_path.is_file():
        return {}
    try:
        with open(override_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        sys.exit(
            f"Error: could not parse {override_path} ({exc}).\n"
            "Check for missing closing quotes, trailing commas, or unescaped characters. "
            "Compare against genre_overrides.json.example."
        )
    except OSError as exc:
        sys.exit(f"Error: could not read {override_path} ({exc}).")
    return {k.strip().lower(): str(v).strip() for k, v in raw.items() if str(v).strip()}


def lookup_genre_override(file_path, parsed_title, genre_overrides):
    """Return a manual genre for filename, stem, or parsed title if configured."""
    if not genre_overrides:
        return None
    path = Path(getattr(file_path, "name", file_path))
    for key in (path.name.lower(), path.stem.lower(), parsed_title.lower()):
        genre = genre_overrides.get(key)
        if genre:
            return genre
    return None


def _load_dotenv_file(path):
    """Load KEY=VALUE lines into os.environ without overwriting existing values."""
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_local_env_files():
    """Load .env from the script directory and current working directory."""
    script_dir = Path(__file__).resolve().parent
    _load_dotenv_file(script_dir / ".env")
    _load_dotenv_file(Path.cwd() / ".env")


def resolve_igdb_credentials():
    """Resolve IGDB/Twitch credentials from .env (or environment variables)."""
    load_local_env_files()

    client_id = (os.environ.get("IGDB_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("IGDB_CLIENT_SECRET") or "").strip()
    return client_id, client_secret


def format_missing_credentials_error(client_id, client_secret):
    script_dir = Path(__file__).resolve().parent
    missing = []
    if not client_id:
        missing.append("IGDB_CLIENT_ID")
    if not client_secret:
        missing.append("IGDB_CLIENT_SECRET")

    return (
        "Error: IGDB credentials missing: "
        + ", ".join(missing)
        + ".\n\n"
        "Create a .env file beside organize_games.py (recommended):\n"
        f"  {script_dir / '.env'}\n\n"
        "Example:\n"
        "  IGDB_CLIENT_ID=your_client_id\n"
        "  IGDB_CLIENT_SECRET=your_client_secret\n\n"
        "Copy from .env.example and fill in your Twitch developer credentials."
    )


def load_igdb_title_aliases(path=None):
    """
    Map parsed/local titles to the name IGDB actually uses.
    European Mindscape re-releases are a common case (e.g. 4D Sports Driving -> Stunts).
    """
    aliases = {
        "4d sports driving": "Stunts",
        "4d driving": "Stunts",
        "dragon force": "D.R.A.G.O.N. Force",
        "falcon - the f-16 fighter simulation": "Falcon",
        "f18interceptor": "F/A-18 Interceptor",
        "f-18 interceptor": "F/A-18 Interceptor",
        "test drive ii - the duel": "The Duel: Test Drive II",
        "tetris pro": "Tetris",
        "zakmckraken": "Zak McKracken and the Alien Mindbenders",
        "zak mckracken": "Zak McKracken and the Alien Mindbenders",
        "sensible soccer - internedit": "Sensible Soccer",
        "sensible soccer - intern edit": "Sensible Soccer",
        "silent service - the submarine simulation": "Silent Service",
        "f-15 eagle strike": "F-15 Strike Eagle II",
        "chase hq": "Chase H.Q.",
        "eye of the beholder 2": "Eye of the Beholder II",
    }
    alias_path = Path(path) if path else Path(__file__).resolve().parent / "igdb_title_aliases.json"
    if not alias_path.is_file():
        return aliases
    try:
        with alias_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        for key, value in data.items():
            aliases[key.strip().lower()] = value.strip()
    except (json.JSONDecodeError, OSError, AttributeError):
        pass
    return aliases


_IGDB_TITLE_ALIASES = load_igdb_title_aliases()


def build_search_titles(file_path, parsed_title, curated_entry=None):
    variants = search_title_variants(parsed_title)
    preferred = curated_search_titles(curated_entry)
    for key in (parsed_title.lower(), Path(file_path.name).stem.lower()):
        alias = _IGDB_TITLE_ALIASES.get(key)
        if alias and not any(existing.lower() == alias.lower() for existing in preferred):
            preferred.append(alias)

    if not preferred:
        return variants

    combined = []
    for title in preferred + variants:
        if not any(existing.lower() == title.lower() for existing in combined):
            combined.append(title)
    return combined


def parse_args():
    parser = argparse.ArgumentParser(
        description="Organize game files into genre subfolders using IGDB metadata.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--source",
        required=True,
        help='Source path with glob pattern, e.g. D:\\Games\\*.adf (searched recursively)',
    )
    parser.add_argument("--dest", required=True, help="Destination folder for organized output")
    parser.add_argument(
        "--platform",
        default=None,
        help="IGDB platform filter: alias (amiga, snes, nes, …), none, or a numeric IGDB platform ID "
        "(default: from platform_defaults.json by source extension, if mapped)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print/log what would happen; do not copy any files",
    )
    parser.add_argument(
        "--unknowns-only",
        action="store_true",
        help="With --dry-run, only print unmatched files and a unique-title summary "
        "(implies --dry-run)",
    )
    return parser.parse_args()


def main():
    load_local_env_files()
    args = parse_args()
    if args.unknowns_only:
        args.dry_run = True

    reload_acronyms()

    source_dir, glob_pattern = parse_source_pattern(args.source)
    dest_dir = Path(args.dest).expanduser().resolve()

    client_id, client_secret = resolve_igdb_credentials()
    if not client_id or not client_secret:
        sys.exit(format_missing_credentials_error(client_id, client_secret))

    genre_overrides = load_genre_overrides()
    curated_library = load_curated_library()
    platform_defaults = load_platform_defaults()
    platform_ids = resolve_platform_ids(glob_pattern, args.platform, platform_defaults)
    if genre_overrides:
        print(f"Loaded {len(genre_overrides)} manual genre override(s).")
    if curated_library:
        unique_curated = len({k for k in curated_library if "." in k})
        print(f"Loaded {unique_curated} curated library entries.")
    if genre_overrides or curated_library:
        print()

    try:
        client = IGDBClient(
            client_id,
            client_secret,
            platform_ids=platform_ids,
        )
    except requests.RequestException as exc:
        sys.exit(f"Error: failed to authenticate with IGDB/Twitch. Check your client ID/secret.\n{exc}")

    if platform_ids:
        print(f"IGDB platform filter: {platform_ids}\n")

    files = sorted(iter_matching_files(source_dir, glob_pattern))
    if not files:
        print(f"No files matching {glob_pattern!r} found under {source_dir}")
        return

    print(f"Found {len(files)} file(s) under {source_dir} matching {glob_pattern!r}")
    if args.unknowns_only:
        print("Showing unmatched files only.\n")
    else:
        print()

    rows = []
    matched_count = 0
    unmatched_count = 0

    for i, file_path in enumerate(files, start=1):
        parsed_title = clean_title(file_path.stem)
        curated_entry = lookup_curated_entry(file_path, parsed_title, curated_library)
        search_titles = build_search_titles(file_path, parsed_title, curated_entry)

        result = client.lookup_best_match(search_titles, min_score=MIN_MATCH_SCORE)
        search_title = result.get("search_title") or search_titles[0]

        is_igdb_match = (
            bool(result.get("matched_name"))
            and result.get("match_score", 0.0) >= MIN_MATCH_SCORE
            and bool(result.get("genres"))
        )
        igdb_genre = result["genres"][0] if is_igdb_match and result.get("genres") else None
        genre_override = lookup_genre_override(file_path, parsed_title, genre_overrides)
        genre, status = resolve_shelf_genre(
            file_path,
            parsed_title,
            result.get("matched_name"),
            igdb_genre,
            curated_library,
            genre_override=genre_override,
            curated_entry=curated_entry,
        )

        if genre:
            matched_count += 1
        else:
            genre = UNKNOWN_GENRE
            status = "unmatched"
            unmatched_count += 1

        is_match = status in ("matched", "override", "curated")

        genre_folder = sanitize_folder_name(genre)
        dest_folder = dest_dir / genre_folder
        dest_path = unique_destination(dest_folder / file_path.name)

        if not args.dry_run:
            dest_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_path)

        rows.append(
            {
                "source_path": str(file_path),
                "parsed_title": parsed_title,
                "search_title": search_title,
                "matched_igdb_name": result.get("matched_name") or "",
                "match_score": f"{result.get('match_score', 0.0):.3f}",
                "genre": genre,
                "status": status,
                "dest_path": str(dest_path),
                "error": result.get("error") or "",
            }
        )

        if args.unknowns_only and is_match:
            continue

        print(
            f"[{i}/{len(files)}] {file_path.name} -> search='{search_title}' "
            f"match='{result.get('matched_name')}' genre='{genre}' ({status})"
        )

    log_rows = rows
    if args.unknowns_only:
        log_rows = [row for row in rows if row["status"] == "unmatched"]

    if log_rows:
        with open(ORGANIZE_LOG_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
            writer.writeheader()
            writer.writerows(log_rows)
    elif args.unknowns_only:
        with open(ORGANIZE_LOG_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "source_path",
                    "parsed_title",
                    "search_title",
                    "matched_igdb_name",
                    "match_score",
                    "genre",
                    "status",
                    "dest_path",
                    "error",
                ],
            )
            writer.writeheader()

    print(f"\nDone. {matched_count} matched, {unmatched_count} unmatched.")
    if args.unknowns_only:
        unique_titles = sorted(
            {row["parsed_title"] for row in rows if row["status"] == "unmatched"},
            key=str.lower,
        )
        print(
            f"Unknown summary: {unmatched_count} file(s), "
            f"{len(unique_titles)} unique parsed title(s)."
        )
        for title in unique_titles:
            print(f"  {title}")
        print(f"Log written to {ORGANIZE_LOG_CSV} (unmatched rows only).")
    else:
        print(f"Log written to {ORGANIZE_LOG_CSV}")
    if args.dry_run:
        print("Dry run: no files were copied.")


if __name__ == "__main__":
    main()
