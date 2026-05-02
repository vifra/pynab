"""
Serialize & unserialize RFID application data.
"""
import json

DATA_IN_LOCAL_DB = "DATA_IN_LOCAL_DB"
MAX_TEXT_LENGTH = 1000

from .tts import (
    DEFAULT_PROVIDER,
    DEFAULT_STYLE,
    DEFAULT_VOICE,
    normalize_provider,
    normalize_style,
    normalize_voice_for_provider,
)


def serialize(text):
    return normalize_text(text).encode("utf8")


def unserialize(data):
    if isinstance(data, bytes):
        text = data.decode("utf8")
    else:
        text = data
    return normalize_text(text)


def normalize_text(text):
    text = str(text or "").strip()
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH].strip()
    return text


def serialize_payload(
    text,
    voice=DEFAULT_VOICE,
    style=DEFAULT_STYLE,
    provider=DEFAULT_PROVIDER,
):
    payload = normalize_payload(
        {
            "text": text,
            "voice": voice,
            "style": style,
            "provider": provider,
        }
    )
    return json.dumps(payload, ensure_ascii=False)


def unserialize_payload(value):
    if isinstance(value, dict):
        return normalize_payload(value)
    if isinstance(value, bytes):
        value = value.decode("utf8")
    value = str(value or "").strip()
    if not value:
        return normalize_payload({})
    try:
        data = json.loads(value)
    except Exception:
        data = {"text": value}
    return normalize_payload(data)


def normalize_payload(data):
    if not isinstance(data, dict):
        data = {}
    provider = normalize_provider(data.get("provider", DEFAULT_PROVIDER))
    return {
        "text": normalize_text(data.get("text", "")),
        "provider": provider,
        "voice": normalize_voice_for_provider(
            data.get("voice", DEFAULT_VOICE), provider
        ),
        "style": normalize_style(
            data.get("style", data.get("speed", DEFAULT_STYLE))
        ),
    }


async def read_data_ui(uid):
    from . import models

    config = await models.Config.load_async()
    uid_data_base = _json_data_base(config.json_data_base)
    return unserialize_payload(uid_data_base.get(uid, ""))


async def write_data_ui(
    uid,
    text,
    voice=DEFAULT_VOICE,
    style=DEFAULT_STYLE,
    provider=DEFAULT_PROVIDER,
):
    from . import models

    config = await models.Config.load_async()
    uid_data_base = _json_data_base(config.json_data_base)
    uid_data_base[uid] = serialize_payload(text, voice, style, provider)
    config.json_data_base = json.dumps(uid_data_base)
    await config.save_async()


def read_data_ui_for_views(uid):
    from .models import Config

    config = Config.load()
    uid_data_base = _json_data_base(config.json_data_base)
    return unserialize_payload(uid_data_base.get(uid, ""))


def write_data_ui_for_views(
    uid,
    text,
    voice=DEFAULT_VOICE,
    style=DEFAULT_STYLE,
    provider=DEFAULT_PROVIDER,
):
    from .models import Config

    config = Config.load()
    uid_data_base = _json_data_base(config.json_data_base)
    uid_data_base[uid] = serialize_payload(text, voice, style, provider)
    config.json_data_base = json.dumps(uid_data_base)
    config.save()


def _json_data_base(value):
    try:
        data = json.loads(value)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        return {}
    return data
