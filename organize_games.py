"""
Recursively scan a folder of game files, identify each game via the IGDB
API, and copy the files into destination subfolders named after the game's
primary genre.

Setup:
    1. Create a Twitch developer application: https://dev.twitch.tv/console/apps
       (Category: "Application Integration"). This gives you a Client ID and
       Client Secret - IGDB authenticates through Twitch.
    2. Provide those via --client-id/--client-secret, or the
       IGDB_CLIENT_ID / IGDB_CLIENT_SECRET environment variables.

Example:
    python organize_games.py --source "D:\\Games\\*.adf" --dest "D:\\Organized"
    python organize_games.py --source "D:\\ROMs\\*.zip" --dest "D:\\Organized" --dry-run
    python organize_games.py --source "D:\\Games\\*.adf" --dest "D:\\Organized" --dry-run --unknowns-only

Optional manual overrides:
    If the automatic filename parsing guesses the wrong title for a
    particular file, pass --overrides pointing at a JSON file mapping either
    the original filename OR the auto-parsed title (case-insensitive) to the
    exact title that should be searched on IGDB, e.g.:

        {
            "Flimbo.adf": "Flimbo's Quest",
            "some weird parsed title": "Actual Game Name"
        }

    To assign a genre without relying on IGDB, create genre_overrides.json
    (or pass --genre-overrides) mapping filename or parsed title to a folder
    name, e.g.:

        {
            "hack.adf": "Role-playing (RPG)",
            "empty disk for saves.adf": "Utility"
        }
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

import requests

from filename_parser import clean_title, reload_amiga_acronyms, search_title_variants
from igdb_client import AMIGA_PLATFORM_ID, IGDBClient

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


def platform_ids_for_glob(pattern):
    if pattern.lower().endswith(".adf"):
        return [AMIGA_PLATFORM_ID]
    return None


def resolve_platform_ids(pattern, platform_arg):
    if platform_arg is None:
        return platform_ids_for_glob(pattern)
    if platform_arg.lower() in ("none", "off", ""):
        return None
    if platform_arg.lower() == "amiga":
        return [AMIGA_PLATFORM_ID]
    try:
        return [int(platform_arg)]
    except ValueError:
        sys.exit(f"Error: unknown --platform value: {platform_arg!r} (use amiga, none, or a numeric IGDB platform ID)")


def load_overrides(path):
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k.strip().lower(): v for k, v in raw.items()}


def default_genre_overrides_path():
    return Path(__file__).resolve().parent / "genre_overrides.json"


def load_genre_overrides(path=None):
    override_path = Path(path) if path else default_genre_overrides_path()
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


def resolve_igdb_credentials(cli_client_id=None, cli_client_secret=None):
    """
    Resolve IGDB/Twitch credentials from CLI args, environment variables,
    igdb_credentials.json, or a .env file.
    """
    load_local_env_files()

    client_id = (cli_client_id or os.environ.get("IGDB_CLIENT_ID") or "").strip()
    client_secret = (cli_client_secret or os.environ.get("IGDB_CLIENT_SECRET") or "").strip()

    if client_id and client_secret:
        return client_id, client_secret

    creds_path = Path(__file__).resolve().parent / "igdb_credentials.json"
    if creds_path.is_file():
        try:
            with creds_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            client_id = client_id or str(data.get("client_id", "")).strip()
            client_secret = client_secret or str(data.get("client_secret", "")).strip()
        except (json.JSONDecodeError, OSError, TypeError, AttributeError):
            pass

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
        "Set them in the SAME terminal session you use to run Python, then retry:\n"
        '  $env:IGDB_CLIENT_ID="your_client_id"\n'
        '  $env:IGDB_CLIENT_SECRET="your_client_secret"\n\n'
        "Or create one of these files (recommended on Windows):\n"
        f"  {script_dir / '.env'}\n"
        f"  {script_dir / 'igdb_credentials.json'}\n\n"
        ".env example:\n"
        "  IGDB_CLIENT_ID=your_client_id\n"
        "  IGDB_CLIENT_SECRET=your_client_secret\n\n"
        "igdb_credentials.json example:\n"
        '  {"client_id": "your_client_id", "client_secret": "your_client_secret"}\n\n'
        "If you set User/System environment variables in Windows, restart Cursor "
        "so new terminals can see them."
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


def build_search_titles(file_path, parsed_title, overrides):
    override = overrides.get(file_path.name.lower()) or overrides.get(parsed_title.lower())
    if override:
        return [override]

    variants = search_title_variants(parsed_title)
    preferred = []
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
        "--client-id",
        default=None,
        help="IGDB/Twitch Client ID (or set IGDB_CLIENT_ID env var / .env / igdb_credentials.json)",
    )
    parser.add_argument(
        "--client-secret",
        default=None,
        help="IGDB/Twitch Client Secret (or set IGDB_CLIENT_SECRET env var / .env / igdb_credentials.json)",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="IGDB platform filter: amiga, none, or a numeric platform ID "
        "(default: amiga when source glob is *.adf)",
    )
    parser.add_argument(
        "--min-match-score",
        type=float,
        default=0.5,
        help="Minimum title similarity score (0-1) required to accept an IGDB match (default: 0.5)",
    )
    parser.add_argument(
        "--overrides",
        default=None,
        help="Optional JSON file mapping filename or parsed title -> exact search title",
    )
    parser.add_argument(
        "--genre-overrides",
        default=None,
        help="JSON file mapping filename or parsed title -> genre folder name "
        "(default: genre_overrides.json beside this script, if present)",
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
    parser.add_argument(
        "--log-file",
        default="organize_log.csv",
        help="CSV file to write a record of every processed file (default: organize_log.csv)",
    )
    parser.add_argument(
        "--cache-file",
        default="igdb_genre_cache.json",
        help="JSON file used to cache IGDB lookups across runs (default: igdb_genre_cache.json)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.unknowns_only:
        args.dry_run = True

    reload_amiga_acronyms()

    source_dir, glob_pattern = parse_source_pattern(args.source)
    dest_dir = Path(args.dest).expanduser().resolve()

    client_id, client_secret = resolve_igdb_credentials(args.client_id, args.client_secret)
    if not client_id or not client_secret:
        sys.exit(format_missing_credentials_error(client_id, client_secret))

    overrides = load_overrides(args.overrides)
    genre_overrides = load_genre_overrides(args.genre_overrides)
    if genre_overrides:
        print(f"Loaded {len(genre_overrides)} manual genre override(s).\n")
    platform_ids = resolve_platform_ids(glob_pattern, args.platform)

    try:
        client = IGDBClient(
            client_id,
            client_secret,
            cache_file=args.cache_file,
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
        search_titles = build_search_titles(file_path, parsed_title, overrides)

        result = client.lookup_best_match(search_titles, min_score=args.min_match_score)
        search_title = result.get("search_title") or search_titles[0]

        genre_override = lookup_genre_override(file_path, parsed_title, genre_overrides)
        if genre_override:
            genre = genre_override
            status = "override"
            matched_count += 1
        else:
            is_match = (
                bool(result.get("matched_name"))
                and result.get("match_score", 0.0) >= args.min_match_score
                and bool(result.get("genres"))
            )

            if is_match:
                genre = result["genres"][0] if result["genres"] else UNKNOWN_GENRE
                status = "matched"
                matched_count += 1
            else:
                genre = UNKNOWN_GENRE
                status = "unmatched"
                unmatched_count += 1

        is_match = status in ("matched", "override")

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
        with open(args.log_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(log_rows[0].keys()))
            writer.writeheader()
            writer.writerows(log_rows)
    elif args.unknowns_only:
        with open(args.log_file, "w", newline="", encoding="utf-8") as f:
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
        print(f"Log written to {args.log_file} (unmatched rows only).")
    else:
        print(f"Log written to {args.log_file}")
    if args.dry_run:
        print("Dry run: no files were copied.")


if __name__ == "__main__":
    main()
