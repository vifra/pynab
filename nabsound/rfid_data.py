"""
Serialize & unserialize RFID application data.
"""

VALID_ACTIONS = ("mute", "up", "down", "reset")
DEFAULT_ACTION = "reset"


def serialize(action):
    if action not in VALID_ACTIONS:
        action = DEFAULT_ACTION
    return action.encode("utf8")


def unserialize(data):
    if isinstance(data, bytes):
        action = data.decode("utf8")
    else:
        action = data
    if action not in VALID_ACTIONS:
        return DEFAULT_ACTION
    return action
