"""
Load extension -> IGDB platform defaults from platform_defaults.json.
"""

import json
import sys
from pathlib import Path

# Kept for tests and backward-compatible imports.
AMIGA_PLATFORM_ID = 16


def default_platform_defaults_path():
    return Path(__file__).resolve().parent / "platform_defaults.json"


def load_platform_defaults(path=None):
    defaults_path = Path(path) if path else default_platform_defaults_path()
    if not defaults_path.is_file():
        return {"aliases": {}, "extensions": {}}
    try:
        with defaults_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        sys.exit(f"Error: could not load {defaults_path} ({exc}).")

    aliases = data.get("aliases", {})
    extensions = data.get("extensions", {})
    if not isinstance(aliases, dict) or not isinstance(extensions, dict):
        sys.exit(f"Error: {defaults_path} must contain 'aliases' and 'extensions' objects.")
    return {
        "aliases": {str(key).lower(): value for key, value in aliases.items()},
        "extensions": {str(key).lower(): value for key, value in extensions.items()},
    }


def extension_from_glob(pattern):
    suffix = pattern.lower().split("*")[-1]
    if not suffix:
        return None
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix


def resolve_platform_value(value, defaults):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.lstrip("-").isdigit():
            return int(stripped)
        alias = defaults.get("aliases", {}).get(stripped.lower())
        if alias is not None:
            return resolve_platform_value(alias, defaults)
        sys.exit(
            f"Error: unknown platform alias {stripped!r} in platform_defaults.json. "
            "Use a numeric IGDB platform ID or a defined alias."
        )
    sys.exit(f"Error: invalid platform value in platform_defaults.json: {value!r}")


def platform_ids_for_glob(pattern, defaults=None):
    defaults = defaults or load_platform_defaults()
    extension = extension_from_glob(pattern)
    if not extension:
        return None
    mapped = defaults.get("extensions", {}).get(extension)
    if mapped is None:
        return None
    platform_id = resolve_platform_value(mapped, defaults)
    return [platform_id] if platform_id is not None else None


def resolve_platform_ids(pattern, platform_arg, defaults=None):
    defaults = defaults or load_platform_defaults()
    if platform_arg is not None:
        if platform_arg.lower() in ("none", "off", ""):
            return None
        platform_id = resolve_platform_value(platform_arg, defaults)
        return [platform_id] if platform_id is not None else None
    return platform_ids_for_glob(pattern, defaults)
