"""
Import a manually sorted genre folder into curated_library.json.

After you have organized (and corrected) files under genre subfolders, run:

    python import_curated.py --from "E:\\Amiga_Stuff\\Amiga ADF by Genre"
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from curated import default_curated_library_path
from filename_parser import clean_title
from organize_games import ORGANIZE_LOG_CSV


def parse_args():
    parser = argparse.ArgumentParser(description="Build curated_library.json from sorted folders.")
    parser.add_argument(
        "--from",
        dest="source_dir",
        required=True,
        help="Sorted destination root (genre subfolders)",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing output file instead of replacing",
    )
    return parser.parse_args()


def load_log_index(log_path):
    path = Path(log_path)
    if not path.is_file():
        return {}
    index = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            filename = Path(row["source_path"]).name.lower()
            index[filename] = row
    return index


def import_sorted_folder(source_dir, log_index=None):
    root = Path(source_dir)
    if not root.is_dir():
        sys.exit(f"Error: not a directory: {root}")

    entries = {}
    for genre_dir in sorted(root.iterdir()):
        if not genre_dir.is_dir():
            continue
        genre = genre_dir.name
        for file_path in sorted(genre_dir.glob("*")):
            if not file_path.is_file():
                continue
            parsed = clean_title(file_path.stem)
            entry = {
                "genre": genre,
                "parsed_title": parsed,
            }
            log_row = (log_index or {}).get(file_path.name.lower())
            if log_row:
                search = (log_row.get("search_title") or "").strip()
                matched = (log_row.get("matched_igdb_name") or "").strip()
                titles = []
                if search:
                    titles.append(search)
                if matched and matched.lower() != search.lower():
                    titles.append(matched)
                if titles:
                    entry["search_titles"] = titles
            entries[file_path.name.lower()] = entry
            entries[file_path.stem.lower()] = entry
    return entries


def main():
    args = parse_args()
    output_path = default_curated_library_path()
    existing = {}
    if args.merge and output_path.is_file():
        try:
            with output_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            existing = data.get("entries", data)
        except (json.JSONDecodeError, OSError):
            existing = {}

    log_index = load_log_index(ORGANIZE_LOG_CSV)
    imported = import_sorted_folder(args.source_dir, log_index)
    merged = {**existing, **imported}

    payload = {
        "_comment": "Human-reviewed shelf assignments. Regenerate with import_curated.py.",
        "entries": dict(sorted(merged.items(), key=lambda item: item[0])),
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    unique_files = len({k for k in merged if "." in k})
    print(f"Wrote {unique_files} file entries to {output_path}")


if __name__ == "__main__":
    main()
