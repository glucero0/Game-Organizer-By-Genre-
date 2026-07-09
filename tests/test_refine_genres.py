import unittest
from pathlib import Path
from unittest.mock import patch

from refine_genres import build_file_entry, load_organize_log, scan_organized_files


class RefineGenresHelperTests(unittest.TestCase):
    def test_scan_organized_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            platform = root / "Platform"
            platform.mkdir()
            (platform / "game.adf").write_bytes(b"x")
            results = list(scan_organized_files(root))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "Platform")
        self.assertEqual(results[0][1].name, "game.adf")

    def test_build_file_entry_uses_log(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "hack.adf"
            file_path.write_bytes(b"x")
            log = {
                "hack.adf": {
                    "parsed_title": "Hack",
                    "matched_igdb_name": "Hack",
                    "genre": "Role-playing (RPG)",
                }
            }
            entry = build_file_entry(file_path, "Role-playing (RPG)", log)
        self.assertEqual(entry["parsed_title"], "Hack")
        self.assertEqual(entry["igdb_name"], "Hack")

    def test_load_organize_log_missing(self):
        self.assertEqual(load_organize_log("/nonexistent/organize_log.csv"), {})


if __name__ == "__main__":
    unittest.main()
