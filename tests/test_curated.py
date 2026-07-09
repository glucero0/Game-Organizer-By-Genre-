import unittest

from curated import (
    apply_shelf_genre_rules,
    curated_search_titles,
    lookup_curated_entry,
    resolve_shelf_genre,
)


class _FakePath:
    def __init__(self, name):
        self.name = name
        self.stem = name.rsplit(".", 1)[0]


class CuratedTests(unittest.TestCase):
    def test_lookup_by_filename(self):
        library = {
            "gianasisters.adf": {"genre": "Platform", "search_titles": ["The Great Giana Sisters"]},
        }
        entry = lookup_curated_entry(_FakePath("gianasisters.adf"), "gianasisters", library)
        self.assertEqual(entry["genre"], "Platform")

    def test_curated_search_titles(self):
        entry = {"search_titles": ["Another World", "Out of This World"]}
        self.assertEqual(curated_search_titles(entry), ["Another World", "Out of This World"])

    def test_shelf_rules_dungeon_crawler(self):
        genre = apply_shelf_genre_rules("dungeonmaster", "Dungeon Master", "Role-playing (RPG)")
        self.assertEqual(genre, "Dungeon Crawlers")

    def test_resolve_prefers_curated_over_igdb(self):
        library = {"hack.adf": {"genre": "Rogue-Likes"}}
        genre, status = resolve_shelf_genre(
            _FakePath("hack.adf"),
            "hack",
            "Hack",
            "Role-playing (RPG)",
            library,
        )
        self.assertEqual(genre, "Rogue-Likes")
        self.assertEqual(status, "curated")

    def test_resolve_applies_shelf_rules_when_no_curated(self):
        genre, status = resolve_shelf_genre(
            _FakePath("gauntlet.adf"),
            "gauntlet",
            "Gauntlet II",
            "Hack and slash/Beat 'em up",
            {},
        )
        self.assertEqual(genre, "Hack and Slash")
        self.assertEqual(status, "matched")


if __name__ == "__main__":
    unittest.main()
