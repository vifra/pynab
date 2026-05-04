"""
Serialize & unserialize RFID application data.
"""

VALID_ACTIONS = ("mute", "up", "down", "reset")
FORM_ACTIONS = VALID_ACTIONS + ("set",)
DEFAULT_ACTION = "reset"
SET_ACTION_PREFIX = "set:"
MIN_SPEAKER_BASE = 0
MAX_SPEAKER_BASE = 255


def normalize_speaker_base(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = MAX_SPEAKER_BASE
    return max(MIN_SPEAKER_BASE, min(MAX_SPEAKER_BASE, number))


def serialize(action, value=None):
    if action not in FORM_ACTIONS:
        action = DEFAULT_ACTION
    if action == "set":
        return f"{SET_ACTION_PREFIX}{normalize_speaker_base(value)}".encode(
            "utf8"
        )
    return action.encode("utf8")


def unserialize(data):
    if isinstance(data, bytes):
        action = data.decode("utf8")
    else:
        action = data
    if is_set_action(action):
        return f"{SET_ACTION_PREFIX}{set_action_value(action)}"
    if action not in VALID_ACTIONS:
        return DEFAULT_ACTION
    return action


def is_set_action(action):
    if not isinstance(action, str) or not action.startswith(SET_ACTION_PREFIX):
        return False
    value = action[len(SET_ACTION_PREFIX) :]
    return value.isdigit()


def set_action_value(action):
    if not is_set_action(action):
        return MAX_SPEAKER_BASE
    return normalize_speaker_base(action[len(SET_ACTION_PREFIX) :])
