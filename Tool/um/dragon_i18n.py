"""Small translation layer for the GUI.

`tr('English text')` returns the text in the chosen language. English is the source language: the text itself is
the key, so a missing translation simply shows the English text. Templates use positional `{0}` / named `{name}`
fields so a translation may reorder them: `tr('Added: {0}', label)`.
"""
from __future__ import annotations

LANGUAGES = {'en': 'English', 'ja': '日本語'}
# Texts the GUI translates through a variable (so a scan of tr('...') literals cannot see them).
DYNAMIC_KEYS = ('tops', 'face', 'hair', 'other',
                'undressed model', 'swimwear', 'dead state', 'different age', 'test model', 'special pose',
                'Automatic (follow Windows)', 'English', 'Follow Windows', 'Light', 'Dark',
                'Unpacking Blender', 'Checking that Blender starts', 'Blender is already installed',
                'Downloading Blender {0}', 'Blender {0} is ready')
_current = 'en'


def system_language() -> str:
    """'ja' when the Windows display language is Japanese, otherwise 'en'."""
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return 'ja' if (lang_id & 0x3FF) == 0x11 else 'en'
    except Exception:  # noqa: BLE001 - not Windows or no ctypes: fall back to the locale
        try:
            import locale
            code = (locale.getdefaultlocale()[0] or '').lower()
            return 'ja' if code.startswith('ja') else 'en'
        except Exception:  # noqa: BLE001
            return 'en'


def resolve(setting: str) -> str:
    """'auto' follows the system; 'en'/'ja' are used as they are; anything else is English."""
    if setting == 'auto':
        return system_language()
    return setting if setting in LANGUAGES else 'en'


def set_language(setting: str) -> str:
    global _current
    _current = resolve(setting)
    return _current


def get_language() -> str:
    return _current


def translations(code: str) -> dict:
    if code == 'ja':
        from um.dragon_i18n_ja import JA
        return JA
    return {}


def tr(text: str, *args, **kwargs) -> str:
    """Translate `text` and fill `{0}` / `{name}` fields with the given values."""
    out = translations(_current).get(text, text)
    if not (args or kwargs):
        return out
    try:
        return out.format(*args, **kwargs)
    except (IndexError, KeyError, ValueError):
        try:
            return text.format(*args, **kwargs)
        except (IndexError, KeyError, ValueError):
            return out
