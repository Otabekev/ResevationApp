import json
import os

_translations: dict[str, dict] = {}

_dir = os.path.join(os.path.dirname(__file__), "locales")
for lang in ("uz", "ru", "en"):
    with open(os.path.join(_dir, f"{lang}.json"), encoding="utf-8") as f:
        _translations[lang] = json.load(f)


def t(key: str, lang: str = "uz", **kwargs) -> str:
    """Translate a key for the given language, with optional format kwargs."""
    text = _translations.get(lang, _translations["uz"]).get(key)
    if text is None:
        text = _translations["uz"].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text
