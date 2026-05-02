from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from . import rfid_data
from .audio_config import (
    BACKUP_PATH,
    CONFIG_PATH,
    load_config,
    reload_mixer,
    reset_alsa,
    restore_default_config,
    run_command,
    save_config,
)

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


class RFIDDataView(TemplateView):
    template_name = "nabsound/rfid-data.html"

    def get(self, request, *args, **kwargs):
        data = request.GET.get("data", "")
        action = rfid_data.unserialize(data)
        return render(
            request,
            self.template_name,
            {"sound_action": action},
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get("sound_action", rfid_data.DEFAULT_ACTION)
        data = rfid_data.serialize(action).decode("utf8")
        return JsonResponse({"data": data})


def config_form(config):
    return {
        "tagtag_speaker_low": config.get("tagtag-speaker-low", ""),
        "tagtag_speaker_high": config.get("tagtag-speaker-high", ""),
        "speaker_base": config.get("speaker-base", ""),
        "headphone_low": config.get("headphone-low", ""),
        "headphone_high": config.get("headphone-high", ""),
        "lineout_mode": config.get("lineout-mode", "lineout"),
    }


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
