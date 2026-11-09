"""
Texts duetPrintGuard sends itself - the default ntfy / Pushover title and message, and the messages shown on the
printer - in the language the pages were last shown in.  Each page sends its language with its requests (ui/src/api.js),
saved as ALERTS.LANGUAGE (duet_config.set_alert_language).  A title or message set on the Configuration page is sent
as it is.

They come from the "alerts" group of the UI's locale files (ui/src/locales/<code>.json): the build writes each
language's alert texts to static/app/locales/<code>.json.  A text missing from a language is sent in
English, and if there are no locale files at all (e.g. the pages were never built) the English given by the
caller is used.
"""
import json
import os
import re

LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'app', 'locales')
_locales = None


def _load():
    global _locales
    if _locales is None:
        _locales = {}
        try:
            names = sorted(os.listdir(LOCALES_DIR))
        except OSError:
            names = []
        for name in names:
            if name.endswith('.json'):
                try:
                    with open(os.path.join(LOCALES_DIR, name), encoding='utf-8') as f:
                        _locales[name[:-5].lower()] = json.load(f)
                except (OSError, ValueError):
                    pass
    return _locales


def languages():
    """The codes of the languages alerts can be sent in - always includes English."""
    return {'en', *_load()}


def alert_text(key, english, **params):
    """The alert text called key in the alert language, with {name} filled in from params."""
    from duet_config import ALERTS  # Late - duet_config uses languages() to check the setting
    locales = _load()
    language = getattr(ALERTS, 'LANGUAGE', 'en')
    text = None
    for code in (language, 'en'):
        text = (locales.get(code) or {}).get('alerts', {}).get(key)
        if isinstance(text, str):
            break
    if not isinstance(text, str):
        text = english
    return re.sub(r'\{(\w+)\}', lambda m: str(params.get(m.group(1), m.group(0))), text)
