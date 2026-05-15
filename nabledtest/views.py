import asyncio
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from nabweb.led_palette import choreography_color_palettes
from nabweb.views import NabdConnection


LEDS = [
    ("nose", _("Nose")),
    ("left", _("Left")),
    ("center", _("Center")),
    ("right", _("Right")),
]


class SettingsView(TemplateView):
    template_name = "nabledtest/settings.html"
    INFO_ID = "nabledtest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["leds"] = [
            {"key": key, "label": label, "default": default, "tempo": tempo}
            for key, label, default, tempo in [
                ("nose", _("Nose"), "#ff00ff", 25),
                ("left", _("Left"), "#ff0000", 25),
                ("center", _("Center"), "#00ff1f", 35),
                ("right", _("Right"), "#0003ff", 45),
            ]
        ]
        context["led_color_palettes"] = choreography_color_palettes()
        return context

    def get(self, request, *args, **kwargs):
        return render(
            request,
            SettingsView.template_name,
            context=self.get_context_data(**kwargs),
        )

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "test")
        if action == "clear":
            result = asyncio.run(self.clear_info())
        else:
            result = asyncio.run(self.send_test_animation(request.POST))
        return JsonResponse(result)

    async def send_test_animation(self, post):
        base_tempo = 5
        led_settings = {
            key: {
                "color": self.normalize_color(post.get(f"color_{key}", "")),
                "steps": max(
                    1,
                    self.normalize_tempo(post.get(f"tempo_{key}", "25"))
                    // base_tempo,
                ),
            }
            for key, label in LEDS
        }
        colors = self.build_parallel_blink_frames(led_settings)
        packet = {
            "type": "info",
            "request_id": "nabledtest",
            "info_id": self.INFO_ID,
            "animation": {"tempo": base_tempo, "colors": colors},
        }
        return await NabdConnection.transaction(self._send_packet, packet)

    async def clear_info(self):
        packet = {
            "type": "info",
            "request_id": "nabledtest",
            "info_id": self.INFO_ID,
        }
        return await NabdConnection.transaction(self._send_packet, packet)

    async def _send_packet(self, reader, writer, packet):
        writer.write((json.dumps(packet) + "\r\n").encode("utf8"))
        await writer.drain()
        while True:
            response = await asyncio.wait_for(reader.readline(), 1)
            if not response:
                return {
                    "status": "error",
                    "message": _("No response from Nabd."),
                }
            data = json.loads(response.decode("utf8"))
            if (
                data.get("type") != "response"
                or data.get("request_id") != "nabledtest"
            ):
                continue
            if data.get("status") == "ok":
                return {"status": "ok"}
            raw_response = json.dumps(data, ensure_ascii=False)
            return {
                "status": "error",
                "message": data.get(
                    "message",
                    _("Nabd rejected the animation: %(response)s")
                    % {"response": raw_response},
                ),
            }

    def off_frame(self):
        return {key: "000000" for key, label in LEDS}

    def build_parallel_blink_frames(self, led_settings):
        frames = []
        for frame_index in range(80):
            frame = {}
            for key, settings in led_settings.items():
                phase = frame_index // settings["steps"]
                frame[key] = settings["color"] if phase % 2 == 0 else "000000"
            frames.append(frame)
        return frames

    def normalize_tempo(self, tempo):
        try:
            return max(1, min(500, int(tempo)))
        except ValueError:
            return 25

    def normalize_color(self, color):
        color = (color or "").strip().lstrip("#")
        if len(color) != 6:
            return "000000"
        try:
            int(color, 16)
        except ValueError:
            return "000000"
        return color.lower()
