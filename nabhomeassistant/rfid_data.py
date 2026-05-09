import json


DEFAULT_ACTION = {
    "action_type": "read_state",
    "service_path": "",
    "entity_id": "",
    "service_data": "",
    "speech_regex": "",
    "speech_replacement": "",
}


def _decode_database(raw_database):
    try:
        database = json.loads(raw_database or "{}")
    except Exception:
        database = {}
    if not isinstance(database, dict):
        database = {}
    return database


def _normalize_action(action):
    normalized = DEFAULT_ACTION.copy()
    if isinstance(action, dict):
        normalized.update(
            {
                "action_type": action.get("action_type", "read_state")
                or "read_state",
                "service_path": action.get("service_path", "") or "",
                "entity_id": action.get("entity_id", "") or "",
                "service_data": action.get("service_data", "") or "",
                "speech_regex": action.get("speech_regex", "") or "",
                "speech_replacement": action.get("speech_replacement", "")
                or "",
            }
        )
    if normalized["action_type"] not in ("read_state", "call_service"):
        normalized["action_type"] = "read_state"
    return normalized


async def read_data_ui(uid):
    from . import models

    config = await models.Config.load_async()
    database = _decode_database(config.json_data_base)
    return _normalize_action(database.get(uid))


async def write_data_ui(uid, action):
    from . import models

    config = await models.Config.load_async()
    database = _decode_database(config.json_data_base)
    database[uid] = _normalize_action(action)
    config.json_data_base = json.dumps(database)
    await config.save_async()


def read_data_ui_for_views(uid):
    from .models import Config

    config = Config.load()
    database = _decode_database(config.json_data_base)
    return _normalize_action(database.get(uid))


def write_data_ui_for_views(uid, action):
    from .models import Config

    config = Config.load()
    database = _decode_database(config.json_data_base)
    database[uid] = _normalize_action(action)
    config.json_data_base = json.dumps(database)
    config.save()
