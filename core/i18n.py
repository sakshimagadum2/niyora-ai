"""Small JSON-backed translation helper for the Streamlit interface."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_STRINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "strings.json"


@lru_cache(maxsize=1)
def _load_strings() -> dict[str, Any]:
    with _STRINGS_PATH.open(encoding="utf-8") as strings_file:
        strings = json.load(strings_file)
    if not isinstance(strings, dict):
        raise ValueError("UI strings must be a JSON object")
    return strings


def t(key: str, lang: str = "en") -> str:
    """Return a translation, falling back to English and then the key itself."""
    strings = _load_strings()
    english = strings.get("en", {})
    language = strings.get(lang, {})
    if not isinstance(english, dict) or not isinstance(language, dict):
        raise ValueError("each language dictionary must be a JSON object")
    english_value = english.get(key, key)
    return language.get(key, english_value)
