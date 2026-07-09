import unittest
from unittest.mock import patch

from igdb_client import IGDBClient


class PickBestMatchTests(unittest.TestCase):
    def test_exact_match(self):
        results = [{"name": "Barbarian", "genres": [{"name": "Fighting"}]}]
        best, score = IGDBClient._pick_best_match("Barbarian", results)
        self.assertEqual(best["name"], "Barbarian")
        self.assertEqual(score, 1.0)

    def test_rejects_scattered_words_in_long_title(self):
        results = [
            {"name": "I Keep Dying in Another World", "genres": [{"name": "Adventure"}]},
            {"name": "Another World", "genres": [{"name": "Platform"}]},
        ]
        best, score = IGDBClient._pick_best_match("Another world", results)
        self.assertEqual(best["name"], "Another World")
        self.assertGreater(score, 0.5)

    def test_prefers_substring_match(self):
        results = [
            {"name": "A-10 Tank Killer", "genres": [{"name": "Simulator"}]},
            {"name": "A-10 Tank Killer + Extra Missions", "genres": []},
        ]
        best, score = IGDBClient._pick_best_match("A-10 Tank Killer", results)
        self.assertEqual(best["name"], "A-10 Tank Killer")
        self.assertGreaterEqual(score, 0.92)

    def test_empty_results(self):
        best, score = IGDBClient._pick_best_match("Agony", [])
        self.assertIsNone(best)
        self.assertEqual(score, 0.0)


class LookupBestMatchTests(unittest.TestCase):
    def test_inherits_genres_from_base_game_variant(self):
        client = IGDBClient.__new__(IGDBClient)
        client._cache = {}
        client.platform_ids = None

        def fake_lookup(title, cache_key=None, min_score=0.5, platform_ids=None):
            if title == "A-10 Tank Killer - Extra Missions":
                return {
                    "matched_name": "A-10 Tank Killer + Extra Missions",
                    "genres": [],
                    "match_score": 0.97,
                    "search_title": title,
                    "error": None,
                }
            if title == "A-10 Tank Killer":
                return {
                    "matched_name": "A-10 Tank Killer",
                    "genres": ["Simulator"],
                    "match_score": 1.0,
                    "search_title": title,
                    "error": None,
                }
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": title,
                "error": None,
            }

        with patch.object(client, "_lookup_single", side_effect=fake_lookup), patch.object(
            client, "_save_cache"
        ):
            result = client.lookup_best_match(
                ["A-10 Tank Killer - Extra Missions", "A-10 Tank Killer"],
                min_score=0.5,
            )

        self.assertEqual(result["genres"], ["Simulator"])
        self.assertEqual(result["matched_name"], "A-10 Tank Killer")

    def test_falls_back_without_platform_filter(self):
        client = IGDBClient.__new__(IGDBClient)
        client._cache = {}
        client.platform_ids = [16]

        def fake_lookup(title, cache_key=None, min_score=0.5, platform_ids=None):
            if platform_ids and title == "Dungeon Quest":
                return {
                    "matched_name": None,
                    "genres": [],
                    "match_score": 0.0,
                    "search_title": title,
                    "error": None,
                }
            if not platform_ids and title == "Dungeon Quest":
                return {
                    "matched_name": "Dungeon Quest",
                    "genres": ["Role-playing (RPG)"],
                    "match_score": 1.0,
                    "search_title": title,
                    "error": None,
                }
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": title,
                "error": None,
            }

        with patch.object(client, "_lookup_single", side_effect=fake_lookup), patch.object(
            client, "_save_cache"
        ):
            result = client.lookup_best_match(["Dungeon Quest"], min_score=0.5)

        self.assertEqual(result["matched_name"], "Dungeon Quest")
        self.assertEqual(result["genres"], ["Role-playing (RPG)"])


if __name__ == "__main__":
    unittest.main()
