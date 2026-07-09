# GameOrganizer

Organize retro game files into genre folders using [IGDB](https://www.igdb.com/) metadata.

Point the tool at a folder of messy scene-release or TOSEC-style filenames, and it will parse each name, look the game up on IGDB, and **copy** files into subfolders named after the game's primary genre. Unmatched files go into `Unknown`.

Built for large real-world collections (hundreds of Amiga ADFs with disk suffixes, glued lowercase names, and European re-releases), with layered heuristics and JSON files you can extend without touching code.

## Features

- **Recursive glob scan** — e.g. `E:\Games\**\*.adf`
- **Filename cleanup** — strips TOSEC/scene tags, disk suffixes (`-d1`, `Disk1`, `Ultima5a`), hardware tags, and more
- **Heuristic title parsing** — splits glued names (`doubledragon2`), expands abbreviations (`abreed` → Alien Breed), roman numeral variants (`Populous II`)
- **IGDB lookup** — OAuth via Twitch, on-disk cache, rate limiting, fuzzy match scoring
- **Amiga-aware** — `*.adf` sources automatically filter IGDB to the Commodore Amiga platform (with fallback when IGDB omits the platform tag)
- **Configurable mappings** — acronyms, IGDB title aliases, search overrides, and manual genre overrides
- **Dry run** — preview results without copying; `--unknowns-only` shows just the files still landing in `Unknown`
- **CSV log** — every file, parsed title, IGDB match, score, genre, and destination path

## Requirements

- Python 3.10+
- A free [Twitch developer application](https://dev.twitch.tv/console/apps) (category: **Application Integration**) for IGDB API access

```bash
pip install -r requirements.txt
```

## Quick start

1. Clone the repo and install dependencies.
2. Set up IGDB credentials (see below).
3. Run a dry run:

```powershell
python organize_games.py --source "D:\Games\*.adf" --dest "D:\Organized" --dry-run
```

4. When satisfied, run without `--dry-run` to copy files.

```powershell
python organize_games.py --source "D:\Games\*.adf" --dest "D:\Organized"
```

**Important:** `--source` must include a glob in the filename part (e.g. `*.adf`). There is no default extension.

## IGDB credentials

IGDB authenticates through Twitch. You need a **Client ID** and **Client Secret**.

### Option A: `.env` file (recommended)

```bash
cp .env.example .env
```

Edit `.env`:

```
IGDB_CLIENT_ID=your_client_id
IGDB_CLIENT_SECRET=your_client_secret
```

### Option B: Environment variables

Set these in the **same terminal session** you use to run the script.

PowerShell:

```powershell
$env:IGDB_CLIENT_ID="your_client_id"
$env:IGDB_CLIENT_SECRET="your_client_secret"
```

bash:

```bash
export IGDB_CLIENT_ID=your_client_id
export IGDB_CLIENT_SECRET=your_client_secret
```

If you set system-wide environment variables on Windows, restart your terminal or IDE so new sessions pick them up.

### Option C: `igdb_credentials.json`

```bash
cp igdb_credentials.json.example igdb_credentials.json
```

```json
{
  "client_id": "your_client_id",
  "client_secret": "your_client_secret"
}
```

Credential files are gitignored. Never commit secrets.

## Usage examples

### Organize Amiga ADFs

```powershell
python organize_games.py `
  --source "E:\Amiga_Stuff\Amiga ADF Files A-Z\*.adf" `
  --dest "E:\Amiga_Stuff\Amiga ADF by Genre"
```

### Dry run — show everything

```powershell
python organize_games.py --source "D:\Games\*.adf" --dest "D:\Organized" --dry-run
```

### Dry run — unknowns only

Useful when tuning mappings: prints only unmatched files and a deduplicated list of parsed titles at the end.

```powershell
python organize_games.py --source "D:\Games\*.adf" --dest "D:\Organized" --unknowns-only
```

### Other file types

Platform filter defaults to Amiga only for `*.adf`. For other extensions, IGDB searches all platforms unless you set `--platform`:

```powershell
python organize_games.py --source "D:\ROMs\*.zip" --dest "D:\Organized" --platform none
```

## Command-line options

| Option | Description |
|--------|-------------|
| `--source` | **Required.** Directory + glob, searched recursively (e.g. `D:\Games\*.adf`) |
| `--dest` | **Required.** Output directory; genre subfolders are created inside it |
| `--dry-run` | Print what would happen; do not copy files |
| `--unknowns-only` | Implies `--dry-run`; only print unmatched files + unique-title summary |
| `--client-id` | Twitch/IGDB Client ID (or use env / `.env` / `igdb_credentials.json`) |
| `--client-secret` | Twitch/IGDB Client Secret |
| `--platform` | `amiga`, `none`, or a numeric IGDB platform ID (default: `amiga` for `*.adf`) |
| `--min-match-score` | Minimum title similarity 0–1 to accept a match (default: `0.5`) |
| `--overrides` | JSON file: filename or parsed title → exact IGDB search title |
| `--genre-overrides` | JSON file: filename or parsed title → genre folder name |
| `--log-file` | CSV output path (default: `organize_log.csv`) |
| `--cache-file` | IGDB lookup cache path (default: `igdb_genre_cache.json`) |

## How it works

For each file matching the glob:

1. **Parse** the filename stem into a clean title (`filename_parser.py`)
2. **Build search candidates** — parsed title, glued-name expansions, sequel/base-game variants, acronyms, and IGDB aliases
3. **Look up** the best IGDB match with genres (`igdb_client.py`)
4. **Resolve genre** — IGDB primary genre, or a manual override, or `Unknown`
5. **Copy** the file to `{dest}/{genre}/{filename}` (originals are never moved or deleted)

Sequel numbers and disk labels are stripped where possible. Expansion disks and DLC often inherit genre from the base game (e.g. *Test Drive II - California Challenge* → *Test Drive II*).

## Configuration files

All JSON config files must be **valid JSON**. Every entry needs a comma except the last. If `amiga_acronyms.json` is malformed, the tool prints a warning and falls back to built-in acronyms only.

Copy the `.example` files, edit your copies, and keep secrets/overrides out of git (see `.gitignore`).

### `amiga_acronyms.json` — scene filename → full title

For short scene-release names. Keys are matched after removing disk/sequel suffixes.

```json
{
  "eotb": "Eye of the Beholder",
  "synd": "Syndicate",
  "f1manag": "F1 Manager",
  "chasehq": "Chase H.Q."
}
```

`EOTB2-d1.ADF` → searches *Eye of the Beholder II*. `F1manag1.adf` → *F1 Manager*.

Reloaded automatically on each run. See `amiga_acronyms.json.example`.

### `igdb_title_aliases.json` — local title → IGDB canonical name

When IGDB uses a different name than your files (European re-releases, punctuation, etc.):

```json
{
  "4d sports driving": "Stunts",
  "f-15 eagle strike": "F-15 Strike Eagle II",
  "dragon force": "D.R.A.G.O.N. Force",
  "chase hq": "Chase H.Q."
}
```

Use this for **full parsed titles**, not short acronyms. Aliases are tried first in the IGDB search list.

### `genre_overrides.json` — manual genre assignment

When IGDB has no entry, wrong genre, or you want a custom folder name:

```json
{
  "hack.adf": "Role-playing (RPG)",
  "empty disk for saves.adf": "Utility",
  "dungeonquest": "Role-playing (RPG)"
}
```

Keys match **filename**, **filename stem**, or **parsed title** (case-insensitive). Manual genres override IGDB. Loaded automatically from `genre_overrides.json` beside the script if present.

See `genre_overrides.json.example`.

### `--overrides` — force IGDB search title

Optional JSON file passed on the command line. Maps filename or parsed title to the exact string to search on IGDB (replaces all automatic variants for that file):

```json
{
  "weird_scene_name.adf": "Actual Game Name",
  "flimbo": "Flimbo's Quest"
}
```

## Tuning workflow

Getting unknowns down is iterative:

1. Run with `--unknowns-only` to see what's left.
2. For each unknown, decide:
   - **Parser gap?** — glued name, disk suffix, abbreviation (may need a code change or acronym)
   - **IGDB name mismatch?** — add to `igdb_title_aliases.json`
   - **Short scene name?** — add to `amiga_acronyms.json`
   - **Not in IGDB / wrong genre?** — add to `genre_overrides.json`
3. Delete `igdb_genre_cache.json` after parser or alias changes (cached lookups won't pick up new search titles otherwise).
4. Re-run `--unknowns-only` and repeat.

Genre-only changes do **not** require clearing the cache.

## Caching

| File | Purpose |
|------|---------|
| `igdb_genre_cache.json` | Caches IGDB search results between runs |
| `.igdb_token_cache.json` | Caches Twitch OAuth token |
| `organize_log.csv` | Per-run results log |

Delete `igdb_genre_cache.json` when you change parsing logic, acronyms, or IGDB aliases.

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

### Project layout

```
GameOrganizer/
├── organize_games.py       # CLI entry point
├── filename_parser.py      # Filename → title heuristics
├── igdb_client.py          # IGDB API client, cache, fuzzy match
├── amiga_acronyms.json     # User-editable scene acronyms (optional)
├── igdb_title_aliases.json # User-editable IGDB name mappings
├── genre_overrides.json    # User-editable manual genres (optional)
├── requirements.txt
└── tests/
```

## Limitations

- Uses IGDB's **primary genre** only (first genre in the API response).
- Files are **copied**, not moved; duplicates get `(2)`, `(3)`, etc. suffixes if the destination name already exists.
- IGDB coverage for obscure Amiga titles is incomplete; some games exist under different names or lack platform tags.
- Very short or generic filenames (`hack.adf`, `fix.adf`) may need manual overrides.
- Match quality depends on filename parsing; scene releases vary widely in naming conventions.

## Acknowledgements

Game metadata from [IGDB](https://www.igdb.com/) (Twitch).
