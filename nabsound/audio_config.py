import shutil
import subprocess
from pathlib import Path


CONFIG_PATH = Path("/var/lib/tagtagtag-sound/mixer.conf")
DEFAULT_CONFIG_PATH = Path("/opt/wm8960/mixer.conf.default")
BACKUP_PATH = Path("/var/lib/tagtagtag-sound/mixer.conf.pynab-backup")

SPEAKER_BASE_DEFAULT = 255
SPEAKER_BASE_STEP = 15

CONFIG_FIELDS = {
    "tagtag-speaker-low": {"type": "int", "min": 0, "max": 127},
    "tagtag-speaker-high": {"type": "int", "min": 0, "max": 127},
    "speaker-base": {"type": "int", "min": 0, "max": 255},
    "headphone-low": {"type": "int", "min": 0, "max": 255},
    "headphone-high": {"type": "int", "min": 0, "max": 255},
    "lineout-mode": {"type": "choice", "choices": ["lineout", "headphone"]},
}


def load_config():
    config = default_config()
    path = CONFIG_PATH if CONFIG_PATH.exists() else DEFAULT_CONFIG_PATH
    try:
        for line in path.read_text().splitlines():
            clean = line.strip()
            if not clean or clean.startswith(";") or "=" not in clean:
                continue
            key, value = clean.split("=", 1)
            if key in CONFIG_FIELDS:
                config[key] = value
    except OSError as err:
        config["_error"] = str(err)
    return config


def default_config():
    return {
        "tagtag-speaker-low": "110",
        "tagtag-speaker-high": "120",
        "speaker-base": str(SPEAKER_BASE_DEFAULT),
        "headphone-low": "227",
        "headphone-high": "249",
        "lineout-mode": "lineout",
    }


def normalize_int(value, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def ensure_config_file():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        source = DEFAULT_CONFIG_PATH if DEFAULT_CONFIG_PATH.exists() else None
        if source:
            shutil.copyfile(str(source), str(CONFIG_PATH))
        else:
            CONFIG_PATH.write_text("")


def backup_config():
    if CONFIG_PATH.exists() and not BACKUP_PATH.exists():
        shutil.copyfile(str(CONFIG_PATH), str(BACKUP_PATH))


def save_config_values(config):
    ensure_config_file()
    backup_config()
    lines = []
    handled = set()
    for line in CONFIG_PATH.read_text().splitlines():
        clean = line.strip()
        if "=" in clean and not clean.startswith(";"):
            key = clean.split("=", 1)[0]
            if key in CONFIG_FIELDS:
                lines.append(f"{key}={config[key]}")
                handled.add(key)
                continue
        lines.append(line)
    for key in CONFIG_FIELDS:
        if key not in handled:
            lines.append(f"{key}={config[key]}")
    CONFIG_PATH.write_text("\n".join(lines) + "\n")


def save_config(post):
    config = load_config()
    for key, field in CONFIG_FIELDS.items():
        value = post.get(key, config.get(key, ""))
        if field["type"] == "int":
            value = normalize_int(value, field["min"], field["max"])
        elif value not in field["choices"]:
            value = config.get(key, field["choices"][0])
        config[key] = str(value)

    save_config_values(config)
    reload_status = reload_mixer()
    if reload_status and reload_status["ok"]:
        return {"ok": True, "message": "Configuration audio enregistree."}
    return reload_status


def set_speaker_base(value):
    value = normalize_int(value, 0, 255)
    config = load_config()
    config["speaker-base"] = str(value)
    save_config_values(config)
    return reload_mixer()


def change_speaker_base(delta):
    config = load_config()
    current = normalize_int(config.get("speaker-base"), 0, 255)
    return set_speaker_base(current + delta)


def mute_speaker():
    return set_speaker_base(0)


def volume_up():
    return change_speaker_base(SPEAKER_BASE_STEP)


def volume_down():
    return change_speaker_base(-SPEAKER_BASE_STEP)


def reset_speaker_volume():
    return set_speaker_base(SPEAKER_BASE_DEFAULT)


def restore_default_config():
    if not DEFAULT_CONFIG_PATH.exists():
        return {"ok": False, "message": "Configuration par defaut introuvable."}
    ensure_config_file()
    backup_config()
    shutil.copyfile(str(DEFAULT_CONFIG_PATH), str(CONFIG_PATH))
    return reload_mixer()


def reload_mixer():
    status = run_command(["pkill", "-USR1", "-f", "tagtagtag-mixerd"])
    if status["ok"]:
        status["message"] = "Mixeur audio recharge."
    return status


def reset_alsa():
    commands = [
        ["systemctl", "stop", "nabd.socket"],
        ["systemctl", "stop", "nabd.service"],
        ["alsactl", "init", "0"],
        ["systemctl", "start", "nabd.socket"],
        ["systemctl", "start", "nabd.service"],
    ]
    for command in commands:
        status = run_command(command)
        if not status["ok"]:
            return status
    return {"ok": True, "message": "ALSA a ete reinitialise."}


def run_command(command):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return {"ok": False, "message": str(err), "output": ""}
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    if result.returncode != 0:
        return {
            "ok": False,
            "message": f"{' '.join(command)} a echoue.",
            "output": output,
        }
    return {"ok": True, "message": "", "output": output}
