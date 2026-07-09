import json
import unittest
from unittest.mock import MagicMock, patch

from gemini_client import GeminiClient


class GeminiClientTests(unittest.TestCase):
    def test_parse_response_array(self):
        text = json.dumps(
            [
                {
                    "filename": "hack.adf",
                    "genre": "Rogue-Likes",
                    "game_title": "Hack",
                    "reason": "roguelike",
                }
            ]
        )
        entries = [{"filename": "hack.adf"}]
        parsed = GeminiClient._parse_response(text, entries)
        self.assertEqual(parsed[0]["genre"], "Rogue-Likes")

    def test_build_prompt_includes_context(self):
        prompt = GeminiClient._build_prompt(
            "Simulator",
            ["Platform", "Simulator"],
            [
                {
                    "filename": "paperboy.adf",
                    "parsed_title": "paperboy",
                    "igdb_name": "Paperboy",
                    "igdb_genre": "Simulator",
                }
            ],
        )
        self.assertIn("paperboy.adf", prompt)
        self.assertIn("Current folder being reviewed", prompt)

    def test_refine_uses_cache_without_api_call(self):
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = "test"
        client.cache_file = client.model = ""
        client.min_interval = 0
        client._last_request_time = 0
        client._cache = {
            "hack.adf": {
                "genre": "Rogue-Likes",
                "game_title": "Hack",
                "reason": "cached",
            }
        }
        with patch.object(client, "_generate") as generate:
            results = client.refine_genres_batch(
                "Role-playing (RPG)",
                ["Role-playing (RPG)"],
                [{"filename": "hack.adf", "parsed_title": "hack"}],
                use_cache=True,
            )
        generate.assert_not_called()
        self.assertEqual(results[0]["genre"], "Rogue-Likes")

    def test_refine_falls_back_when_file_missing_from_response(self):
        client = GeminiClient.__new__(GeminiClient)
        client.api_key = "test"
        client.cache_file = MagicMock()
        client.model = "gemini-2.5-flash"
        client.min_interval = 0
        client._last_request_time = 0
        client._cache = {}
        client.save_cache = MagicMock()

        with patch.object(client, "_generate", return_value="[]"):
            results = client.refine_genres_batch(
                "Unknown",
                ["Unknown"],
                [{"filename": "mystery.adf", "parsed_title": "mystery"}],
                use_cache=False,
            )
        self.assertEqual(results[0]["genre"], "Unknown")
        self.assertIn("kept current folder", results[0]["reason"])

    def test_generate_retries_on_rate_limit(self):
        client = GeminiClient("test-key", requests_per_minute=1000, max_retries=3)
        client.min_interval = 0
        client._model_verified = True

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.raise_for_status = MagicMock()
        ok_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}]
        }

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}

        with patch("gemini_client.requests.post", side_effect=[rate_limited, ok_response]) as post:
            with patch("gemini_client.time.sleep") as sleep:
                text = client._generate("prompt")
        self.assertEqual(text, "[]")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_generate_raises_after_exhausted_retries(self):
        client = GeminiClient("secret-key", requests_per_minute=1000, max_retries=2)
        client.min_interval = 0
        client._model_verified = True

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {}

        with patch("gemini_client.requests.post", return_value=rate_limited):
            with patch("gemini_client.time.sleep"):
                with self.assertRaisesRegex(RuntimeError, "rate limit exceeded"):
                    client._generate("prompt")


    def test_ensure_model_falls_back_when_requested_missing(self):
        client = GeminiClient("test-key", model="gemini-2.0-flash")
        with patch.object(
            client,
            "list_models",
            return_value=["gemini-2.5-flash", "gemini-1.5-flash"],
        ):
            resolved = client.ensure_model()
        self.assertEqual(resolved, "gemini-2.5-flash")


if __name__ == "__main__":
    unittest.main()
