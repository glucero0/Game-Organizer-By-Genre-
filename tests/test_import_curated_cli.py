"""CLI contract tests for import_curated.py."""

import sys
import unittest
from unittest.mock import patch

from import_curated import parse_args


def _argv(*extra):
    return ["import_curated.py", "--from", "D:/Sorted", *extra]


class ArgparseHelperTests(unittest.TestCase):
    def assert_argv_rejected(self, argv):
        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                parse_args()
        self.assertEqual(ctx.exception.code, 2)


class ImportCuratedCliTests(ArgparseHelperTests):
    def test_minimal_required_args(self):
        with patch.object(sys, "argv", _argv()):
            args = parse_args()
        self.assertEqual(args.source_dir, "D:/Sorted")

    def test_defaults(self):
        with patch.object(sys, "argv", _argv()):
            args = parse_args()
        self.assertFalse(args.merge)

    def test_merge_flag_accepted(self):
        with patch.object(sys, "argv", _argv("--merge")):
            args = parse_args()
        self.assertTrue(args.merge)

    def test_rejects_removed_output(self):
        self.assert_argv_rejected(_argv("--output", "custom.json"))

    def test_rejects_removed_log(self):
        self.assert_argv_rejected(_argv("--log", "organize_log.csv"))

    def test_missing_from_exits(self):
        self.assert_argv_rejected(["import_curated.py"])


if __name__ == "__main__":
    unittest.main()
