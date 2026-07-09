import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from organize_games import (
    build_search_titles,
    format_missing_credentials_error,
    has_glob_pattern,
    load_genre_overrides,
    lookup_genre_override,
    parse_source_pattern,
    resolve_igdb_credentials,
    _load_dotenv_file,
)
from platform_defaults import AMIGA_PLATFORM_ID, platform_ids_for_glob, resolve_platform_ids


class SourceGlobTests(unittest.TestCase):
    def test_has_glob_pattern(self):
        self.assertTrue(has_glob_pattern("*.adf"))
        self.assertFalse(has_glob_pattern("games.adf"))

    def test_parse_source_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, pattern = parse_source_pattern(str(Path(tmp) / "*.adf"))
            self.assertEqual(pattern, "*.adf")
            self.assertEqual(base, Path(tmp).resolve())

    def test_adf_glob_uses_amiga_platform(self):
        self.assertEqual(platform_ids_for_glob("*.adf"), [AMIGA_PLATFORM_ID])

    def test_non_adf_glob_has_no_default_platform(self):
        self.assertIsNone(platform_ids_for_glob("*.zip"))

    def test_resolve_platform_override(self):
        defaults = {"aliases": {"amiga": AMIGA_PLATFORM_ID}, "extensions": {".adf": "amiga"}}
        self.assertIsNone(resolve_platform_ids("*.adf", "none", defaults))
        self.assertEqual(resolve_platform_ids("*.zip", "amiga", defaults), [AMIGA_PLATFORM_ID])


class CredentialTests(unittest.TestCase):
    def test_resolve_from_env(self):
        env = {
            "IGDB_CLIENT_ID": "id123",
            "IGDB_CLIENT_SECRET": "secret456",
        }
        with patch.dict(os.environ, env, clear=True):
            client_id, client_secret = resolve_igdb_credentials()
        self.assertEqual(client_id, "id123")
        self.assertEqual(client_secret, "secret456")

    def test_resolve_from_dotenv(self):
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            dotenv.write_text(
                "IGDB_CLIENT_ID=from_dotenv\nIGDB_CLIENT_SECRET=from_secret\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                _load_dotenv_file(dotenv)
                client_id, client_secret = resolve_igdb_credentials()
        self.assertEqual(client_id, "from_dotenv")
        self.assertEqual(client_secret, "from_secret")

    def test_missing_credentials_error_lists_fields(self):
        message = format_missing_credentials_error("", "secret")
        self.assertIn("IGDB_CLIENT_ID", message)
        self.assertNotIn("IGDB_CLIENT_SECRET", message.split("missing:")[1].split(".")[0])
        self.assertIn(".env", message)
        self.assertNotIn("igdb_credentials", message)


class BuildSearchTitlesTests(unittest.TestCase):
    def test_returns_variants(self):
        titles = build_search_titles(_FakePath("alteredbeast - d1.adf"), "alteredbeast")
        self.assertIn("Altered Beast", titles)

    def test_igdb_alias_for_rebranded_title(self):
        titles = build_search_titles(
            _FakePath("4D Sports Driving (1990)(Mindscape)[cr CSL](Disk 1 of 2).adf"),
            "4D Sports Driving",
        )
        self.assertEqual(titles[0], "Stunts")

    def test_igdb_alias_for_dragon_force(self):
        titles = build_search_titles(
            _FakePath("Dragon Force v1.02 (1989-12-08)(Interstel Corporation).adf"),
            "Dragon Force",
        )
        self.assertEqual(titles[0], "D.R.A.G.O.N. Force")

    def test_curated_search_titles_prepended(self):
        entry = {"search_titles": ["The Great Giana Sisters"]}
        titles = build_search_titles(_FakePath("gianasisters.adf"), "gianasisters", entry)
        self.assertEqual(titles[0], "The Great Giana Sisters")


class GenreOverrideTests(unittest.TestCase):
    def test_lookup_by_filename(self):
        overrides = {"hack.adf": "Role-playing (RPG)"}
        genre = lookup_genre_override(_FakePath("hack.adf"), "hack", overrides)
        self.assertEqual(genre, "Role-playing (RPG)")

    def test_lookup_by_parsed_title(self):
        overrides = {"dungeon quest": "Adventure"}
        genre = lookup_genre_override(_FakePath("dungeonquest1.adf"), "Dungeon Quest", overrides)
        self.assertEqual(genre, "Adventure")

    def test_load_missing_file_returns_empty(self):
        with patch(
            "organize_games.default_genre_overrides_path",
            return_value=Path("/nonexistent/genre_overrides.json"),
        ):
            self.assertEqual(load_genre_overrides(), {})

    def test_load_genre_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "genre_overrides.json"
            path.write_text(
                json.dumps({"Hack.adf": "Role-playing (RPG)"}),
                encoding="utf-8",
            )
            with patch("organize_games.default_genre_overrides_path", return_value=path):
                overrides = load_genre_overrides()
        self.assertEqual(overrides["hack.adf"], "Role-playing (RPG)")

    def test_invalid_genre_overrides_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "genre_overrides.json"
            path.write_text('{"broken": "Platform,}', encoding="utf-8")
            with patch("organize_games.default_genre_overrides_path", return_value=path):
                with self.assertRaises(SystemExit):
                    load_genre_overrides()


class _FakePath:
    def __init__(self, name):
        self.name = name
        self.stem = Path(name).stem


if __name__ == "__main__":
    unittest.main()
