import datetime
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen


DATE_KEYS = ("date", "day", "jour", "dateTexte")
MEAL_KEYS = ("menu", "meal", "repas", "title", "name", "description")
AUDIO_KEYS = ("audio_url", "audio", "mp3", "url_audio", "son")


class MenuError(Exception):
    pass


def fetch_menu_json(url: str) -> Any:
    if not url:
        raise MenuError("No JSON URL configured.")
    with urlopen(url, timeout=10) as response:  # nosec B310
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def meal_for_date(data: Any, day: Optional[datetime.date] = None) -> Dict[str, str]:
    if day is None:
        day = datetime.date.today()
    item = _find_item(data, day)
    if item is None:
        raise MenuError(f"No meal found for {day.isoformat()}.")
    return _normalize_item(item)


def tts_audio_urls(text: str, lang: str = "fr") -> List[str]:
    urls = []
    for part in _split_tts_text(text):
        query = urlencode(
            {
                "ie": "UTF-8",
                "client": "tw-ob",
                "tl": lang,
                "q": part,
            }
        )
        urls.append(f"https://translate.google.com/translate_tts?{query}")
    return urls


def _find_item(data: Any, day: datetime.date) -> Any:
    day_keys = {
        day.isoformat(),
        day.strftime("%Y/%m/%d"),
        day.strftime("%d/%m/%Y"),
    }
    weekday_keys = {
        day.strftime("%A").lower(),
        str(day.weekday()),
        str(day.isoweekday()),
    }

    if isinstance(data, dict):
        for key in day_keys:
            if key in data:
                return data[key]
        for key in weekday_keys:
            if key in data:
                return data[key]
        for collection_key in ("menus", "meals", "repas", "days", "jours"):
            if collection_key in data:
                found = _find_item(data[collection_key], day)
                if found is not None:
                    return found
        if _item_matches_date(data, day):
            return data
    elif isinstance(data, list):
        for item in data:
            if _item_matches_date(item, day):
                return item
    return None


def _item_matches_date(item: Any, day: datetime.date) -> bool:
    if not isinstance(item, dict):
        return False
    for key in DATE_KEYS:
        if key in item and _parse_date(str(item[key])) == day:
            return True
    return False


def _parse_date(value: str) -> Optional[datetime.date]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    return None


def _normalize_item(item: Any) -> Dict[str, str]:
    if isinstance(item, str):
        return {"text": item, "audio_url": ""}
    if isinstance(item, list):
        return {"text": ", ".join(str(part) for part in item), "audio_url": ""}
    if not isinstance(item, dict):
        return {"text": str(item), "audio_url": ""}

    day_menu = _normalize_day_menu(item)
    if day_menu:
        return day_menu

    text = _first_string(item, MEAL_KEYS)
    audio_url = _first_string(item, AUDIO_KEYS)
    if not text:
        text = _join_parts(item)
    return {"text": text, "audio_url": audio_url}


def _normalize_day_menu(item: Dict[str, Any]) -> Optional[Dict[str, str]]:
    midi = str(item.get("midi") or "").strip()
    soir = str(item.get("soir") or "").strip()
    if not midi and not soir:
        return None

    labels = item.get("labels")
    if not isinstance(labels, dict):
        labels = {}
    midi_label = labels.get("midi", "Midi")
    soir_label = labels.get("soir", "Soir")

    parts = []
    date_longue = str(item.get("dateLongue") or "").strip()
    if date_longue:
        parts.append(date_longue)
    if midi and not item.get("midiIntrouvable", False):
        parts.append(f"{midi_label}: {_clean_multiline(midi)}")
    if soir and not item.get("soirIntrouvable", False):
        parts.append(f"{soir_label}: {_clean_multiline(soir)}")
    if not parts:
        return None
    return {
        "text": ". ".join(parts),
        "audio_url": _first_string(item, AUDIO_KEYS),
    }


def _clean_multiline(value: str) -> str:
    return ", ".join(part.strip() for part in value.splitlines() if part.strip())


def _split_tts_text(text: str, limit: int = 180) -> List[str]:
    words = text.split()
    parts = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def _first_string(item: Dict[str, Any], keys: tuple) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str):
            return value
    return ""


def _join_parts(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    for value in item.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(part) for part in value)
    return ", ".join(parts)
