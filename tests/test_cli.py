"""
CLI contract tests: allowed flags, removed flags, defaults, and main() behavior.
"""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import organize_games
import refine_genres
from organize_games import format_missing_credentials_error, parse_args as parse_organize_args
from refine_genres import parse_args as parse_refine_args, resolve_gemini_api_key


def _organize_argv(*extra):
    return ["organize_games.py", "--source", "D:/Games/*.adf", "--dest", "D:/Organized", *extra]


def _refine_argv(dest, *extra):
    return ["refine_genres.py", "--dest", str(dest), *extra]


class ArgparseHelperTests(unittest.TestCase):
    def assert_argv_rejected(self, parse_args, argv):
        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                parse_args()
        self.assertEqual(ctx.exception.code, 2)


class OrganizeGamesCliTests(ArgparseHelperTests):
    def test_minimal_required_args(self):
        with patch.object(sys, "argv", _organize_argv()):
            args = parse_organize_args()
        self.assertEqual(args.source, "D:/Games/*.adf")
        self.assertEqual(args.dest, "D:/Organized")

    def test_defaults(self):
        with patch.object(sys, "argv", _organize_argv()):
            args = parse_organize_args()
        self.assertFalse(args.dry_run)
        self.assertFalse(args.unknowns_only)
        self.assertIsNone(args.platform)

    def test_all_optional_flags_accepted(self):
        argv = _organize_argv(
            "--platform",
            "none",
            "--dry-run",
            "--unknowns-only",
        )
        with patch.object(sys, "argv", argv):
            args = parse_organize_args()
        self.assertEqual(args.platform, "none")
        self.assertTrue(args.dry_run)
        self.assertTrue(args.unknowns_only)

    def test_rejects_removed_curated_library(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--curated-library", "curated.json"),
        )

    def test_rejects_removed_log_file(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--log-file", "custom.csv"),
        )

    def test_rejects_removed_cache_file(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--cache-file", "cache.json"),
        )

    def test_rejects_removed_overrides(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--overrides", "titles.json"),
        )

    def test_rejects_removed_genre_overrides(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--genre-overrides", "genres.json"),
        )

    def test_rejects_removed_min_match_score(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--min-match-score", "0.7"),
        )

    def test_rejects_removed_client_id(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--client-id", "secret"),
        )

    def test_rejects_removed_client_secret(self):
        self.assert_argv_rejected(
            parse_organize_args,
            _organize_argv("--client-secret", "secret"),
        )

    def test_missing_source_exits(self):
        self.assert_argv_rejected(
            parse_organize_args,
            ["organize_games.py", "--dest", "D:/Organized"],
        )

    def test_missing_dest_exits(self):
        self.assert_argv_rejected(
            parse_organize_args,
            ["organize_games.py", "--source", "D:/Games/*.adf"],
        )


class RefineGenresCliTests(ArgparseHelperTests):
    def test_minimal_required_args(self):
        with patch.object(sys, "argv", _refine_argv("D:/Organized")):
            args = parse_refine_args()
        self.assertEqual(args.dest, "D:/Organized")

    def test_defaults(self):
        with patch.object(sys, "argv", _refine_argv("D:/Organized")):
            args = parse_refine_args()
        self.assertFalse(args.dry_run)
        self.assertFalse(args.refresh)
        self.assertFalse(args.list_models)
        self.assertFalse(args.update_curated)
        self.assertEqual(args.model, "gemini-2.5-flash")
        self.assertEqual(args.batch_size, 25)
        self.assertEqual(args.rpm, 10)

    def test_all_optional_flags_accepted(self):
        argv = _refine_argv(
            "D:/Organized",
            "--dry-run",
            "--refresh",
            "--model",
            "gemini-1.5-flash",
            "--batch-size",
            "10",
            "--rpm",
            "5",
            "--update-curated",
        )
        with patch.object(sys, "argv", argv):
            args = parse_refine_args()
        self.assertTrue(args.dry_run)
        self.assertTrue(args.refresh)
        self.assertEqual(args.model, "gemini-1.5-flash")
        self.assertEqual(args.batch_size, 10)
        self.assertEqual(args.rpm, 5)
        self.assertTrue(args.update_curated)

    def test_rejects_removed_organize_log(self):
        self.assert_argv_rejected(
            parse_refine_args,
            _refine_argv("D:/Organized", "--organize-log", "custom.csv"),
        )

    def test_rejects_removed_log_file(self):
        self.assert_argv_rejected(
            parse_refine_args,
            _refine_argv("D:/Organized", "--log-file", "custom.csv"),
        )

    def test_rejects_removed_cache_file(self):
        self.assert_argv_rejected(
            parse_refine_args,
            _refine_argv("D:/Organized", "--cache-file", "cache.json"),
        )

    def test_rejects_removed_apply(self):
        self.assert_argv_rejected(
            parse_refine_args,
            _refine_argv("D:/Organized", "--apply"),
        )

    def test_rejects_removed_api_key(self):
        self.assert_argv_rejected(
            parse_refine_args,
            _refine_argv("D:/Organized", "--api-key", "secret"),
        )

    def test_missing_dest_exits(self):
        self.assert_argv_rejected(parse_refine_args, ["refine_genres.py"])


class CredentialCliTests(unittest.TestCase):
    def test_missing_igdb_credentials_error_mentions_dotenv_only(self):
        message = format_missing_credentials_error("", "")
        self.assertIn(".env", message)
        self.assertNotIn("igdb_credentials", message)

    def test_main_exits_when_igdb_credentials_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            dest = Path(tmp) / "dest"
            source.mkdir()
            dest.mkdir()
            (source / "game.adf").write_bytes(b"x")
            argv = [
                "organize_games.py",
                "--source",
                str(source / "*.adf"),
                "--dest",
                str(dest),
                "--dry-run",
            ]
            with patch("organize_games.load_local_env_files"), patch.dict(
                os.environ, {}, clear=True
            ):
                with patch.object(sys, "argv", argv):
                    with self.assertRaises(SystemExit) as ctx:
                        organize_games.main()
        self.assertIn("IGDB credentials missing", str(ctx.exception))

    def test_resolve_gemini_api_key_from_gemini_env(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=True):
            with patch("refine_genres.load_local_env_files"):
                self.assertEqual(resolve_gemini_api_key(), "gemini-key")

    def test_resolve_gemini_api_key_from_google_env(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "google-key"}, clear=True):
            with patch("refine_genres.load_local_env_files"):
                self.assertEqual(resolve_gemini_api_key(), "google-key")

    def test_main_exits_when_gemini_api_key_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            genre = root / "Shooter"
            genre.mkdir()
            (genre / "game.adf").write_bytes(b"x")
            with patch("refine_genres.load_local_env_files"), patch(
                "refine_genres.resolve_gemini_api_key",
                return_value="",
            ):
                with patch.object(sys, "argv", _refine_argv(root)):
                    with self.assertRaises(SystemExit) as ctx:
                        refine_genres.main()
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


class OrganizeGamesMainBehaviorTests(unittest.TestCase):
    def test_unknowns_only_implies_dry_run_in_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source"
            dest = tmp_path / "dest"
            source.mkdir()
            dest.mkdir()
            (source / "game.adf").write_bytes(b"x")

            mock_client = MagicMock()
            mock_client.lookup_best_match.return_value = {
                "matched_name": "",
                "match_score": 0.0,
                "genre": "Unknown",
                "error": "",
            }

            argv = [
                "organize_games.py",
                "--source",
                str(source / "*.adf"),
                "--dest",
                str(dest),
                "--unknowns-only",
            ]
            with patch("organize_games.load_local_env_files"), patch.dict(
                os.environ,
                {"IGDB_CLIENT_ID": "id", "IGDB_CLIENT_SECRET": "secret"},
                clear=True,
            ), patch("organize_games.IGDBClient", return_value=mock_client), patch.object(
                sys, "argv", argv
            ):
                organize_games.main()

            self.assertFalse(list(dest.rglob("*.adf")))
            mock_client.lookup_best_match.assert_called()


class RefineGenresMainBehaviorTests(unittest.TestCase):
    def _run_main(self, root, *, dry_run):
        shooter = root / "Shooter"
        shooter.mkdir()
        file_path = shooter / "hack.adf"
        file_path.write_bytes(b"x")
        log_path = root / "organize_log.csv"
        with log_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
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
            writer.writerow(
                {
                    "source_path": str(file_path),
                    "parsed_title": "hack",
                    "search_title": "hack",
                    "matched_igdb_name": "Hack",
                    "match_score": "1.0",
                    "genre": "Shooter",
                    "status": "matched",
                    "dest_path": str(file_path),
                    "error": "",
                }
            )

        mock_client = MagicMock()
        mock_client.ensure_model.return_value = "gemini-2.5-flash"
        mock_client.refine_genres_batch.return_value = [
            {
                "filename": "hack.adf",
                "genre": "Rogue-Likes",
                "game_title": "Hack",
                "reason": "roguelike",
            }
        ]

        argv = _refine_argv(root)
        if dry_run:
            argv.append("--dry-run")

        with patch("refine_genres.GeminiClient", return_value=mock_client), patch(
            "refine_genres.resolve_gemini_api_key",
            return_value="test-key",
        ), patch.object(sys, "argv", argv):
            original_cwd = Path.cwd()
            try:
                os.chdir(root)
                refine_genres.main()
            finally:
                os.chdir(original_cwd)

        return file_path, root / "Rogue-Likes" / "hack.adf"

    def test_dry_run_does_not_move_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, expected_dest = self._run_main(root, dry_run=True)
            self.assertTrue(original.is_file())
            self.assertFalse(expected_dest.exists())

    def test_without_dry_run_moves_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, expected_dest = self._run_main(root, dry_run=False)
            self.assertFalse(original.exists())
            self.assertTrue(expected_dest.is_file())


if __name__ == "__main__":
    unittest.main()
