import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from filename_parser import _acronyms_path, _load_acronyms, clean_title, reload_acronyms


def stem(filename):
    return filename.rsplit(".", 1)[0]


class AcronymReloadTests(unittest.TestCase):
    def test_reload_loads_custom_acronym(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acronyms.json"
            path.write_text(json.dumps({"eotb": "Eye of the Beholder"}), encoding="utf-8")
            with patch("filename_parser._acronyms_path", return_value=path):
                reload_acronyms()
            self.assertEqual(clean_title(stem("EOTB2-d1.ADF")), "Eye of the Beholder 2")

    def test_invalid_json_prints_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "acronyms.json"
            path.write_text('{"broken": "value" "missing": "comma"}', encoding="utf-8")
            with patch("filename_parser._acronyms_path", return_value=path):
                with patch("sys.stderr") as stderr:
                    _load_acronyms()
            self.assertTrue(any("could not load" in str(call) for call in stderr.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
