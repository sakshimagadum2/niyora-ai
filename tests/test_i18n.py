import json
from pathlib import Path

from core.i18n import t


def test_every_english_string_has_a_hindi_translation() -> None:
    strings_path = Path(__file__).resolve().parents[1] / "data" / "strings.json"
    strings = json.loads(strings_path.read_text(encoding="utf-8"))

    assert strings["en"]
    assert set(strings["en"]).issubset(strings["hi"])


def test_unknown_language_or_key_falls_back_to_english() -> None:
    assert t("tab.applicant", "unknown") == t("tab.applicant", "en")
    assert t("missing.translation.key", "hi") == "missing.translation.key"


def test_hindi_translation_is_used_when_available() -> None:
    assert t("tab.applicant", "hi") == "आवेदक"
