import unittest

from platform_defaults import (
    AMIGA_PLATFORM_ID,
    extension_from_glob,
    load_platform_defaults,
    platform_ids_for_glob,
    resolve_platform_ids,
    resolve_platform_value,
)


class PlatformDefaultsTests(unittest.TestCase):
    DEFAULTS = {
        "aliases": {"amiga": 16, "snes": 19},
        "extensions": {".adf": "amiga", ".nes": 18, ".zip": None},
    }

    def test_extension_from_glob(self):
        self.assertEqual(extension_from_glob("*.adf"), ".adf")
        self.assertEqual(extension_from_glob("*.NES"), ".nes")
        self.assertIsNone(extension_from_glob("*"))

    def test_adf_uses_amiga_from_defaults(self):
        self.assertEqual(platform_ids_for_glob("*.adf", self.DEFAULTS), [AMIGA_PLATFORM_ID])

    def test_unmapped_extension_returns_none(self):
        self.assertIsNone(platform_ids_for_glob("*.zip", self.DEFAULTS))

    def test_numeric_extension_mapping(self):
        self.assertEqual(platform_ids_for_glob("*.nes", self.DEFAULTS), [18])

    def test_platform_arg_none_searches_all(self):
        self.assertIsNone(resolve_platform_ids("*.zip", "none", self.DEFAULTS))

    def test_platform_arg_alias(self):
        self.assertEqual(resolve_platform_ids("*.rom", "snes", self.DEFAULTS), [19])

    def test_platform_arg_numeric_string(self):
        self.assertEqual(resolve_platform_ids("*.rom", "18", self.DEFAULTS), [18])

    def test_resolve_platform_value_alias_chain(self):
        self.assertEqual(resolve_platform_value("amiga", self.DEFAULTS), 16)

    def test_shipped_defaults_include_adf(self):
        defaults = load_platform_defaults()
        self.assertEqual(platform_ids_for_glob("*.adf", defaults), [16])


if __name__ == "__main__":
    unittest.main()
