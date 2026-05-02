import shutil
import subprocess
from pathlib import Path

from django.shortcuts import render
from django.views.generic import TemplateView


CONFIG_PATH = Path("/var/lib/tagtagtag-sound/mixer.conf")
DEFAULT_CONFIG_PATH = Path("/opt/wm8960/mixer.conf.default")
BACKUP_PATH = Path("/var/lib/tagtagtag-sound/mixer.conf.pynab-backup")

CONFIG_FIELDS = {
    "tagtag-speaker-low": {"type": "int", "min": 0, "max": 127},
    "tagtag-speaker-high": {"type": "int", "min": 0, "max": 127},
    "speaker-base": {"type": "int", "min": 0, "max": 255},
    "headphone-low": {"type": "int", "min": 0, "max": 255},
    "headphone-high": {"type": "int", "min": 0, "max": 255},
    "lineout-mode": {"type": "choice", "choices": ["lineout", "headphone"]},
}

ALSA_CONTROLS = [
    ("Headphones Jack", ["amixer", "cget", "numid=1"]),
    ("Volume Button", ["amixer", "cget", "numid=44"]),
    ("PCM -6dB", ["amixer", "cget", "numid=18"]),
    ("Playback", ["amixer", "cget", "numid=11"]),
    ("Headphone", ["amixer", "cget", "numid=12"]),
    ("Speaker", ["amixer", "cget", "numid=14"]),
]


class SoundSettingsView(TemplateView):
    template_name = "nabsound/settings.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.context())

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "save")
        status = None
        if action == "save":
            status = save_config(request.POST)
        elif action == "reload":
            status = reload_mixer()
        elif action == "restore-default":
            status = restore_default_config()
        elif action == "reset-alsa":
            status = reset_alsa()
        elif action == "store-alsa":
            status = run_command(["alsactl", "store"])
        return render(request, self.template_name, self.context(status))

    def context(self, status=None):
        config = load_config()
        return {
            "config_path": str(CONFIG_PATH),
            "backup_path": str(BACKUP_PATH),
            "config": config,
            "config_error": config.get("_error", ""),
            "form": config_form(config),
            "alsa_controls": alsa_status(),
            "status": status,
        }


def config_form(config):
    return {
        "tagtag_speaker_low": config.get("tagtag-speaker-low", ""),
        "tagtag_speaker_high": config.get("tagtag-speaker-high", ""),
        "speaker_base": config.get("speaker-base", ""),
        "headphone_low": config.get("headphone-low", ""),
        "headphone_high": config.get("headphone-high", ""),
        "lineout_mode": config.get("lineout-mode", "lineout"),
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
        "speaker-base": "255",
        "headphone-low": "227",
        "headphone-high": "249",
        "lineout-mode": "lineout",
    }


def save_config(post):
    config = load_config()
    for key, field in CONFIG_FIELDS.items():
        value = post.get(key, config.get(key, ""))
        if field["type"] == "int":
            value = normalize_int(value, field["min"], field["max"])
        elif value not in field["choices"]:
            value = config.get(key, field["choices"][0])
        config[key] = str(value)

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
    reload_status = reload_mixer()
    if reload_status and reload_status["ok"]:
        return {"ok": True, "message": "Configuration audio enregistree."}
    return reload_status


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


def alsa_status():
    controls = []
    for label, command in ALSA_CONTROLS:
        status = run_command(command)
        controls.append(
            {
                "label": label,
                "ok": status["ok"],
                "value": extract_values(status["output"]),
                "output": status["output"],
            }
        )
    return controls


def extract_values(output):
    for line in output.splitlines():
        clean = line.strip()
        if clean.startswith(": values="):
            return clean.replace(": values=", "")
    return ""


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
