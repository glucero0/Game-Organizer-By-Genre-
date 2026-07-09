"""
Google Gemini API client for batch genre refinement.
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

_GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
_GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_RETRYABLE_STATUS = {429, 500, 503}
_MODEL_FALLBACKS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
)


class GeminiClient:
    def __init__(
        self,
        api_key,
        cache_file="ai_genre_cache.json",
        model="gemini-2.5-flash",
        requests_per_minute=10,
        max_retries=8,
    ):
        self.api_key = api_key
        self.cache_file = Path(cache_file)
        self.model = model
        self.max_retries = max(1, max_retries)
        self.min_interval = 60.0 / max(requests_per_minute, 1)
        self._last_request_time = 0.0
        self._cache = self._load_cache()
        self._available_models = None
        self._model_verified = False

    def _load_cache(self):
        if not self.cache_file.is_file():
            return {}
        try:
            with self.cache_file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {}

    def save_cache(self):
        with self.cache_file.open("w", encoding="utf-8") as handle:
            json.dump(self._cache, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_time = time.time()

    def get_cached(self, filename):
        return self._cache.get(filename.lower())

    def list_models(self):
        response = requests.get(
            _GEMINI_MODELS_URL,
            params={"key": self.api_key},
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(self._sanitize_error(str(exc))) from exc

        models = []
        for item in response.json().get("models", []):
            name = str(item.get("name", "")).removeprefix("models/")
            methods = item.get("supportedGenerationMethods") or []
            if name and "generateContent" in methods:
                models.append(name)
        return sorted(models)

    def ensure_model(self):
        if self._model_verified:
            return self.model

        available = set(self.list_models())
        self._available_models = sorted(available)

        if self.model in available:
            self._model_verified = True
            return self.model

        for candidate in _MODEL_FALLBACKS:
            if candidate in available:
                print(
                    f"Model {self.model!r} is not available for this API key; "
                    f"using {candidate!r} instead."
                )
                self.model = candidate
                self._model_verified = True
                return self.model

        flash_models = [name for name in self._available_models if "flash" in name.lower()]
        if flash_models:
            self.model = flash_models[0]
            print(f"Using Gemini model {self.model!r}.")
            self._model_verified = True
            return self.model

        sample = ", ".join(self._available_models[:8])
        raise RuntimeError(
            f"No suitable Gemini flash model found for {self.model!r}. "
            f"Run refine_genres.py --list-models to see options. "
            f"Examples: {sample}"
        )

    def refine_genres_batch(
        self,
        current_genre,
        existing_genres,
        file_entries,
        use_cache=True,
    ):
        """
        Ask Gemini to assign shelf genres for a batch of files.

        file_entries: list of dicts with keys filename, parsed_title, igdb_name, igdb_genre
        Returns list of dicts: filename, genre, game_title, reason
        """
        pending = []
        results = []
        for entry in file_entries:
            filename = entry["filename"]
            cached = self.get_cached(filename) if use_cache else None
            if cached and cached.get("genre"):
                results.append(self._result_from_cache(filename, cached))
            else:
                pending.append(entry)

        if not pending:
            return results

        prompt = self._build_prompt(current_genre, existing_genres, pending)
        response_text = self._generate(prompt)
        parsed = self._parse_response(response_text, pending)
        by_name = {item["filename"].lower(): item for item in parsed}

        for entry in pending:
            filename = entry["filename"]
            item = by_name.get(filename.lower())
            if not item:
                item = {
                    "filename": filename,
                    "genre": current_genre,
                    "game_title": entry.get("parsed_title") or "",
                    "reason": "Gemini returned no entry; kept current folder",
                }
            item.setdefault("game_title", entry.get("parsed_title") or "")
            item.setdefault("reason", "")
            self._cache[filename.lower()] = {
                "genre": item["genre"],
                "game_title": item.get("game_title", ""),
                "reason": item.get("reason", ""),
                "previous_genre": current_genre,
                "model": self.model,
            }
            results.append(item)

        self.save_cache()
        return results

    @staticmethod
    def _result_from_cache(filename, cached):
        return {
            "filename": filename,
            "genre": cached.get("genre", ""),
            "game_title": cached.get("game_title", ""),
            "reason": cached.get("reason", "cached"),
        }

    @staticmethod
    def _build_prompt(current_genre, existing_genres, file_entries):
        genre_list = ", ".join(sorted(existing_genres))
        lines = [
            "You are a retro game collector organizing disk images onto genre shelves.",
            "Each file is currently in a folder that may be wrong.",
            "",
            f'Current folder being reviewed: "{current_genre}"',
            f"Existing genre folders in the library: {genre_list}",
            "",
            "For EACH file below, choose the best shelf genre.",
            "- Prefer an existing genre folder when it fits.",
            "- You MAY suggest a new concise genre name when needed (e.g. Dungeon Crawlers, Rogue-Likes).",
            "- Multi-disk games share one genre.",
            "- Utility/noise disks (empty save disk, fix tools) -> Utility.",
            "",
            "Files:",
        ]
        for entry in file_entries:
            parts = [f'- {entry["filename"]}']
            if entry.get("parsed_title"):
                parts.append(f'parsed="{entry["parsed_title"]}"')
            if entry.get("igdb_name"):
                parts.append(f'igdb="{entry["igdb_name"]}"')
            if entry.get("igdb_genre"):
                parts.append(f'igdb_genre="{entry["igdb_genre"]}"')
            lines.append(" | ".join(parts))

        lines.extend(
            [
                "",
                "Return ONLY a JSON array, no markdown, with one object per file:",
                '[{"filename":"exact.bin","genre":"Shelf Genre","game_title":"Canonical Name","reason":"brief"}]',
            ]
        )
        return "\n".join(lines)

    def _generate(self, prompt):
        self.ensure_model()
        last_response = None
        for attempt in range(self.max_retries):
            self._throttle()
            url = _GEMINI_API_URL.format(model=self.model)
            response = requests.post(
                url,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=120,
            )
            last_response = response

            if response.status_code in _RETRYABLE_STATUS:
                wait = self._retry_wait_seconds(response, attempt)
                print(
                    f"Gemini rate limit (HTTP {response.status_code}); "
                    f"waiting {wait:.0f}s before retry {attempt + 1}/{self.max_retries}...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue

            if response.status_code == 404:
                self._model_verified = False
                previous = self.model
                self.ensure_model()
                if self.model != previous:
                    print(
                        f"Retrying with model {self.model!r} after HTTP 404.",
                        file=sys.stderr,
                    )
                    continue
                raise RuntimeError(
                    f"Gemini model {self.model!r} was not found. "
                    "Run refine_genres.py --list-models and pass --model <name>."
                )

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(self._sanitize_error(str(exc))) from exc

            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc

        status = last_response.status_code if last_response is not None else "unknown"
        raise RuntimeError(
            "Gemini rate limit exceeded "
            f"(last HTTP {status}) after {self.max_retries} retries. "
            "Wait a minute and re-run the same command; completed batches are cached in "
            f"{self.cache_file.name}. Try a lower --rpm (e.g. 5) or smaller --batch-size."
        )

    @staticmethod
    def _retry_wait_seconds(response, attempt):
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
        return min(120.0, 10.0 * (2**attempt))

    def _sanitize_error(self, message):
        if not self.api_key:
            return message
        return message.replace(self.api_key, "***")

    @staticmethod
    def _parse_response(response_text, file_entries):
        text = response_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", text)
            if not match:
                raise
            payload = json.loads(match.group(0))

        if isinstance(payload, dict) and "files" in payload:
            payload = payload["files"]
        if not isinstance(payload, list):
            raise ValueError("Gemini response was not a JSON array")

        expected = {entry["filename"].lower() for entry in file_entries}
        parsed = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename", "")).strip()
            genre = str(item.get("genre", "")).strip()
            if not filename or not genre:
                continue
            if filename.lower() not in expected:
                continue
            parsed.append(
                {
                    "filename": filename,
                    "genre": genre,
                    "game_title": str(item.get("game_title", "")).strip(),
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
        return parsed
