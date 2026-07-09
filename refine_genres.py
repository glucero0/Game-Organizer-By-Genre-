"""
Pass 2: refine genre folders with Gemini after organize_games.py.

Walk an organized destination tree, ask Gemini to review shelf placement in
batches (grouped by current genre folder), then create new genre folders and
move files as needed.

Examples:
    python refine_genres.py --dest "E:\\Organized" --dry-run
    python refine_genres.py --dest "E:\\Organized"
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

from filename_parser import clean_title
from gemini_client import GeminiClient
from import_curated import import_sorted_folder
from organize_games import (
    ORGANIZE_LOG_CSV,
    load_local_env_files,
    sanitize_folder_name,
    unique_destination,
)

REFINE_LOG_CSV = "refine_log.csv"


def resolve_gemini_api_key():
    load_local_env_files()
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Refine organized game folders using Gemini (pass 2).",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Organized destination root (genre subfolders from pass 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print/log proposed moves; do not move any files",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore ai_genre_cache.json and re-query Gemini",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Gemini model id (default: gemini-2.5-flash; auto-fallback if unavailable)",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List Gemini models available to your API key and exit",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Files per Gemini request within a genre folder (default: 25)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=10,
        help="Max Gemini requests per minute (default: 10; lower if you hit 429)",
    )
    parser.add_argument(
        "--update-curated",
        action="store_true",
        help="After moving files, regenerate curated_library.json from the destination tree",
    )
    return parser.parse_args()


def load_organize_log(log_path):
    path = Path(log_path)
    if not path.is_file():
        return {}
    index = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            filename = Path(row.get("source_path", "")).name
            if filename:
                index[filename.lower()] = row
    return index


def scan_organized_files(dest_root):
    """Yield (current_genre, file_path) for files directly under genre folders."""
    root = Path(dest_root).resolve()
    if not root.is_dir():
        sys.exit(f"Error: destination does not exist: {root}")

    for genre_dir in sorted(root.iterdir()):
        if not genre_dir.is_dir():
            continue
        current_genre = genre_dir.name
        for file_path in sorted(genre_dir.iterdir()):
            if file_path.is_file():
                yield current_genre, file_path


def build_file_entry(file_path, current_genre, organize_log):
    filename = file_path.name
    log_row = organize_log.get(filename.lower(), {})
    parsed = log_row.get("parsed_title") or clean_title(file_path.stem)
    return {
        "filename": filename,
        "parsed_title": parsed,
        "igdb_name": (log_row.get("matched_igdb_name") or "").strip(),
        "igdb_genre": (log_row.get("genre") or current_genre).strip(),
        "current_genre": current_genre,
        "file_path": file_path,
    }


def chunk(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def collect_genre_folders(dest_root):
    root = Path(dest_root)
    return sorted(child.name for child in root.iterdir() if child.is_dir())


def main():
    load_local_env_files()
    args = parse_args()
    api_key = resolve_gemini_api_key()
    if not api_key:
        sys.exit(
            "Error: Gemini API key required. Add GEMINI_API_KEY to .env "
            "(see .env.example).\n"
            "Get a key at https://aistudio.google.com/apikey"
        )

    dest_root = Path(args.dest).expanduser().resolve()
    organize_log = load_organize_log(ORGANIZE_LOG_CSV)
    if organize_log:
        print(f"Loaded organize log context for {len(organize_log)} file(s).")
    else:
        print(f"No {ORGANIZE_LOG_CSV} found; using filename parsing only for context.")
    print()

    grouped = {}
    for current_genre, file_path in scan_organized_files(dest_root):
        grouped.setdefault(current_genre, []).append(
            build_file_entry(file_path, current_genre, organize_log)
        )

    if not grouped:
        sys.exit(f"No files found under genre folders in {dest_root}")

    total_files = sum(len(items) for items in grouped.values())
    print(f"Found {total_files} file(s) across {len(grouped)} genre folder(s) in {dest_root}")
    if args.dry_run:
        print("Dry run: no files will be moved.\n")

    client = GeminiClient(
        api_key,
        model=args.model,
        requests_per_minute=args.rpm,
    )

    if args.list_models:
        for name in client.list_models():
            print(name)
        return

    resolved_model = client.ensure_model()
    if resolved_model != args.model:
        print(f"Using Gemini model: {resolved_model}")
    print()

    existing_genres = collect_genre_folders(dest_root)
    rows = []
    move_count = 0
    stay_count = 0

    for current_genre in sorted(grouped):
        entries = grouped[current_genre]
        print(f"Reviewing {len(entries)} file(s) in {current_genre!r}...")
        for batch in chunk(entries, args.batch_size):
            batch_payload = [
                {
                    "filename": entry["filename"],
                    "parsed_title": entry["parsed_title"],
                    "igdb_name": entry["igdb_name"],
                    "igdb_genre": entry["igdb_genre"],
                }
                for entry in batch
            ]
            refined = client.refine_genres_batch(
                current_genre,
                existing_genres,
                batch_payload,
                use_cache=not args.refresh,
            )
            refined_by_name = {item["filename"].lower(): item for item in refined}

            for entry in batch:
                suggestion = refined_by_name.get(entry["filename"].lower(), {})
                new_genre = sanitize_folder_name(suggestion.get("genre") or current_genre)
                if new_genre not in existing_genres:
                    existing_genres.append(new_genre)
                    existing_genres.sort()

                file_path = entry["file_path"]
                dest_folder = dest_root / new_genre
                dest_path = unique_destination(dest_folder / file_path.name)
                changed = new_genre != current_genre

                if changed:
                    move_count += 1
                    action = "move"
                else:
                    stay_count += 1
                    action = "keep"

                rows.append(
                    {
                        "filename": file_path.name,
                        "current_genre": current_genre,
                        "new_genre": new_genre,
                        "game_title": suggestion.get("game_title", ""),
                        "reason": suggestion.get("reason", ""),
                        "action": action,
                        "dest_path": str(dest_path),
                    }
                )

                if changed:
                    reason = suggestion.get("reason")
                    suffix = f" ({reason})" if reason else ""
                    print(f"  {file_path.name}: {current_genre} -> {new_genre}{suffix}")

                if not args.dry_run and changed:
                    dest_folder.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file_path), str(dest_path))
                    entry["file_path"] = dest_path

    with open(REFINE_LOG_CSV, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "filename",
                "current_genre",
                "new_genre",
                "game_title",
                "reason",
                "action",
                "dest_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"\nDone. {stay_count} unchanged, {move_count} to move. Log: {REFINE_LOG_CSV}"
    )
    if args.dry_run:
        print("Dry run: no files were moved.")
    if not args.dry_run and args.update_curated:
        output = Path(__file__).resolve().parent / "curated_library.json"
        payload = {
            "_comment": "Generated after Gemini refine pass.",
            "entries": import_sorted_folder(dest_root, organize_log),
        }
        with output.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Updated curated library: {output}")


if __name__ == "__main__":
    main()
