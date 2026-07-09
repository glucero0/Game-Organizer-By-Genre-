"""
Minimal IGDB API client: handles Twitch OAuth2 client-credentials auth,
rate limiting, on-disk response caching, and picking the best fuzzy match
for a searched title.
"""

import difflib
import json
import os
import re
import time
import threading

import requests

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_API_BASE = "https://api.igdb.com/v4"

# IGDB platform ID for Commodore Amiga.
AMIGA_PLATFORM_ID = 16

# Minimum fuzzy title similarity (0-1) required to accept an IGDB match in pass 1.
MIN_MATCH_SCORE = 0.5


class IGDBClient:
    def __init__(
        self,
        client_id,
        client_secret,
        cache_file="igdb_genre_cache.json",
        token_cache_file=".igdb_token_cache.json",
        requests_per_second=4,
        platform_ids=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.cache_file = cache_file
        self.token_cache_file = token_cache_file
        self.min_interval = 1.0 / requests_per_second
        self.platform_ids = platform_ids

        self._last_request_time = 0.0
        self._lock = threading.Lock()
        self._access_token = None
        self._cache = self._load_json(self.cache_file)

        self._ensure_token()

    # -- persistence -------------------------------------------------

    @staticmethod
    def _load_json(path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, sort_keys=True)

    # -- auth ----------------------------------------------------------

    def _ensure_token(self):
        cached = self._load_json(self.token_cache_file)
        now = time.time()
        if cached.get("access_token") and cached.get("expires_at", 0) > now + 60:
            self._access_token = cached["access_token"]
            return
        self._fetch_new_token()

    def _fetch_new_token(self):
        resp = requests.post(
            _TOKEN_URL,
            params={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        expires_at = time.time() + float(data.get("expires_in", 0))
        with open(self.token_cache_file, "w", encoding="utf-8") as f:
            json.dump({"access_token": self._access_token, "expires_at": expires_at}, f)

    # -- networking ------------------------------------------------------

    def _throttle(self):
        with self._lock:
            elapsed = time.time() - self._last_request_time
            wait = self.min_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_time = time.time()

    def _post(self, endpoint, body, retries=3):
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self._access_token}",
        }
        url = f"{_API_BASE}/{endpoint}"

        last_exc = None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=15)
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code == 401:
                self._fetch_new_token()
                headers["Authorization"] = f"Bearer {self._access_token}"
                continue

            if resp.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue

            resp.raise_for_status()
            return resp.json()

        if last_exc:
            raise last_exc
        raise RuntimeError(f"IGDB request to {endpoint!r} failed after {retries} retries")

    def _build_search_body(self, title, platform_ids=None):
        safe_title = title.replace('"', "'")
        body = f'search "{safe_title}"; fields name,genres.name;'
        platform_ids = self.platform_ids if platform_ids is None else platform_ids
        if platform_ids:
            ids = ",".join(str(platform_id) for platform_id in platform_ids)
            body += f" where platforms = ({ids});"
        body += " limit 10;"
        return body

    @staticmethod
    def _is_acceptable_match(result, min_score):
        return (
            bool(result.get("matched_name"))
            and result.get("match_score", 0.0) >= min_score
            and bool(result.get("genres"))
        )

    # -- public API --------------------------------------------------

    def lookup_game(self, title):
        """
        Search IGDB for `title`, returning:
            {"matched_name": str|None, "genres": [str, ...],
             "match_score": float, "search_title": str, "error": str|None}
        Results are cached on disk keyed by the lowercased query title.
        """
        return self._lookup_single(title, cache_key=title.strip().lower())

    def lookup_best_match(self, titles, min_score=MIN_MATCH_SCORE):
        """
        Try several title variants (best-first) and return the strongest match.
        Cached under the first title in the list.
        """
        titles = [t.strip() for t in titles if t and t.strip()]
        if not titles:
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": "",
                "error": "empty title",
            }

        cache_key = titles[0].lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._lookup_best_match_for_platforms(titles, min_score, self.platform_ids)
        if self.platform_ids and not self._is_acceptable_match(result, min_score):
            unfiltered = self._lookup_best_match_for_platforms(titles, min_score, None)
            if self._is_acceptable_match(unfiltered, min_score):
                self._cache[cache_key] = unfiltered
                self._save_cache()
                return unfiltered

        self._cache[cache_key] = result
        self._save_cache()
        return result

    def _lookup_best_match_for_platforms(self, titles, min_score, platform_ids):
        best_result = {
            "matched_name": None,
            "genres": [],
            "match_score": 0.0,
            "search_title": titles[0],
            "error": None,
        }

        best_without_genres = None

        for title in titles:
            result = self._lookup_single(
                title,
                cache_key=None,
                min_score=0,
                platform_ids=platform_ids,
            )
            result["search_title"] = title
            score = result.get("match_score", 0.0)
            has_genres = bool(result.get("genres"))

            if result.get("matched_name") and score >= min_score:
                if has_genres:
                    return result
                if (
                    best_without_genres is None
                    or score > best_without_genres.get("match_score", 0.0)
                ):
                    best_without_genres = result

            if score > best_result.get("match_score", 0.0):
                best_result = result

        if best_without_genres:
            for title in titles:
                fallback = self._lookup_single(
                    title,
                    cache_key=None,
                    min_score=0,
                    platform_ids=platform_ids,
                )
                if fallback.get("genres") and fallback.get("match_score", 0.0) >= min_score:
                    inherited = dict(best_without_genres)
                    inherited["genres"] = fallback["genres"]
                    return inherited

        return best_result

    def _lookup_single(self, title, cache_key=None, min_score=MIN_MATCH_SCORE, platform_ids=None):
        key = cache_key or title.strip().lower()
        if not key:
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": title,
                "error": "empty title",
            }

        if cache_key is None and key in self._cache:
            return self._cache[key]

        body = self._build_search_body(title, platform_ids=platform_ids)

        try:
            results = self._post("games", body)
        except requests.RequestException as exc:
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": title,
                "error": str(exc),
            }
        except RuntimeError as exc:
            return {
                "matched_name": None,
                "genres": [],
                "match_score": 0.0,
                "search_title": title,
                "error": str(exc),
            }

        best, score = self._pick_best_match(title, results)
        if best is None or score < min_score:
            result = {
                "matched_name": best.get("name") if best else None,
                "genres": [],
                "match_score": round(score, 3),
                "search_title": title,
                "error": None,
            }
        else:
            genre_names = [g["name"] for g in best.get("genres", []) if "name" in g]
            result = {
                "matched_name": best.get("name"),
                "genres": genre_names,
                "match_score": round(score, 3),
                "search_title": title,
                "error": None,
            }

        if cache_key is not None:
            self._cache[key] = result
            self._save_cache()

        return result

    @staticmethod
    def _pick_best_match(query, results):
        if not results:
            return None, 0.0

        query_norm = query.strip().lower()
        query_words = [w for w in re.findall(r"\w+", query_norm) if len(w) > 2]
        best_result, best_score = None, -1.0

        for candidate in results:
            name = candidate.get("name", "")
            name_norm = name.lower()

            if query_norm == name_norm:
                score = 1.0
            elif query_norm in name_norm:
                length_ratio = len(query_norm) / max(len(name_norm), 1)
                if length_ratio < 0.55 or (
                    name_norm.endswith(query_norm) and length_ratio < 0.75
                ):
                    score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio() * 0.4
                else:
                    score = max(
                        difflib.SequenceMatcher(None, query_norm, name_norm).ratio(),
                        0.92,
                    )
            else:
                score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
                if len(query_words) >= 2:
                    if all(word in name_norm for word in query_words):
                        score *= 0.65
                    else:
                        score *= 0.35

            if score > best_score:
                best_result, best_score = candidate, score

        return best_result, best_score
