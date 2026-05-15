import datetime
import json

from django.http import JsonResponse, QueryDict
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from meteofrance_api.client import MeteoFranceClient, Place

from . import rfid_data
from .models import Config, ScheduledMessage
from .nabweatherd import NabWeatherd
from nabweb.led_palette import (
    choreography_color_palettes,
    choreography_color_values,
)


WEATHER_ANIMATION_FIELDS = [
    ("sunny", _("Sunshine")),
    ("cloudy", _("Cloudy")),
    ("foggy", _("Fog")),
    ("rainy", _("Rain")),
    ("rain_alert", _("Rain alert")),
    ("snowy", _("Snow")),
    ("stormy", _("Thunderstorm")),
]

LED_CHOICES = [
    {"value": "nose", "label": _("Nose")},
    {"value": "left", "label": _("Left")},
    {"value": "center", "label": _("Center")},
    {"value": "right", "label": _("Right")},
]

PATTERN_CHOICES = [
    {"value": "blink", "label": _("Blink")},
    {"value": "breath", "label": _("Breathe")},
    {"value": "static", "label": _("Fixed")},
]


class SettingsView(TemplateView):
    template_name = "nabweatherd/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        context["weather_animation_fields"] = self.weather_animation_fields(
            context["config"]
        )
        context["led_color_palettes"] = choreography_color_palettes()
        context["led_usage_summary"] = self.led_usage_summary(
            context["config"]
        )
        context["scheduled_messages"] = ScheduledMessage.objects.all()
        celsius_available = True
        farenheit_available = True
        user_language = self.request.LANGUAGE_CODE
        if user_language == "fr-fr":
            # Sounds not available for temperatures higher than 50
            farenheit_available = False
        context["celsius_available"] = celsius_available
        context["farenheit_available"] = farenheit_available
        return context

    def led_usage_summary(self, config):
        usage = [
            {"key": "nose", "label": _("Nose LED"), "items": []},
            {"key": "left", "label": _("Left LED"), "items": []},
            {"key": "center", "label": _("Center LED"), "items": []},
            {"key": "right", "label": _("Right LED"), "items": []},
            {
                "key": "bottom",
                "label": _("Bottom LED"),
                "items": [
                    {
                        "label": _("Network status"),
                        "detail": _("Native pulse color"),
                    }
                ],
            },
        ]
        usage_by_key = {entry["key"]: entry for entry in usage}
        configured = config.weather_animations or {}

        weather_enabled = config.weather_animation_type in (
            "weather_only",
            "weather_and_rain",
        )
        rain_enabled = config.weather_animation_type in (
            "rain_only",
            "weather_and_rain",
        )
        if weather_enabled:
            for key, label in WEATHER_ANIMATION_FIELDS:
                if key == "rain_alert":
                    continue
                self.add_animation_usage(
                    usage_by_key, configured, key, _("Weather"), label
                )
        if rain_enabled:
            self.add_animation_usage(
                usage_by_key,
                configured,
                "rain_alert",
                _("Weather"),
                _("Rain alert"),
            )

        try:
            from nabairqualityd.models import Config as AirQualityConfig

            airquality_config = AirQualityConfig.load()
            if airquality_config.visual_airquality != "nothing":
                for led in ("left", "center", "right"):
                    usage_by_key[led]["items"].append(
                        {
                            "label": _("Air quality"),
                            "detail": _("Default animation, three LEDs"),
                        }
                    )
        except Exception:
            pass

        for entry in usage:
            entry["has_multiple"] = len(entry["items"]) > 1
            if not entry["items"]:
                entry["items"].append(
                    {"label": _("Free"), "detail": _("No configured use")}
                )
        return usage

    def add_animation_usage(
        self, usage_by_key, configured, key, service_label, animation_label
    ):
        if key in configured:
            simple = self.animation_to_simple_form(configured[key])
            usage_by_key[simple["led"]]["items"].append(
                {
                    "label": f"{service_label} - {animation_label}",
                    "detail": _("Custom animation"),
                }
            )
            return
        for led in ("left", "center", "right"):
            usage_by_key[led]["items"].append(
                {
                    "label": f"{service_label} - {animation_label}",
                    "detail": _("Default animation, three LEDs"),
                }
            )

    def get(self, request, *args, **kwargs):
        json_item = {}
        json_places = []
        context = self.get_context_data(**kwargs)
        if "q" in request.GET:
            search_location = request.GET["q"]
            client = MeteoFranceClient()
            list_places = client.search_places(search_location)
            for one_place in list_places:
                # correct bad json returned my MeteoFrance + admin is not
                # always there
                if "name" in one_place.raw_data:
                    one_place.raw_data["name"] = one_place.raw_data[
                        "name"
                    ].replace("'", " ")
                if "admin" in one_place.raw_data:
                    one_place.raw_data["admin"] = one_place.raw_data[
                        "admin"
                    ].replace("'", " ")
                json_item["value"] = str(one_place.raw_data)
                json_item["text"] = one_place.__str__()
                json_places.append(json_item)
                json_item = {}
            return JsonResponse(json_places, status=200, safe=False)
        return render(request, SettingsView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        config = Config.load()
        if "location" in request.POST:
            location = request.POST["location"]
            if location != "":
                location = location.replace("None", "''")
                location = location.replace("'", '"')

                location_json = json.loads(location)
                location_place = Place(location_json)
                config.location = location_json
                config.location_user_friendly = location_place.__str__()

        if "unit" in request.POST:
            unit = request.POST["unit"]
            config.unit = int(unit)

        if "weather_animation_type" in request.POST:
            weather_animation_type = request.POST["weather_animation_type"]
            config.weather_animation_type = weather_animation_type

        if "weather_frequency" in request.POST:
            weather_frequency = request.POST["weather_frequency"]
            config.weather_frequency = weather_frequency

        animation_error = self.save_weather_animations(config, request.POST)

        config.save()
        NabWeatherd.signal_daemon()
        context = self.get_context_data(**kwargs)
        context["animation_error"] = animation_error
        return render(request, SettingsView.template_name, context=context)

    def weather_animation_fields(self, config):
        defaults = NabWeatherd.default_animation_objects()
        configured = config.weather_animations or {}
        palette_values = choreography_color_values()
        fields = []
        for key, label in WEATHER_ANIMATION_FIELDS:
            animation = configured.get(key, defaults[key])
            simple = self.animation_to_simple_form(animation)
            fields.append(
                {
                    "key": key,
                    "label": label,
                    "custom": key in configured,
                    "led": simple["led"],
                    "color": simple["color"],
                    "color_in_palette": simple["color"] in palette_values,
                    "tempo": simple["tempo"],
                    "pattern": simple["pattern"],
                    "led_choices": LED_CHOICES,
                    "pattern_choices": PATTERN_CHOICES,
                }
            )
        return fields

    def save_weather_animations(self, config, post):
        defaults = NabWeatherd.default_animation_objects()
        configured = {}
        errors = []
        for key, label in WEATHER_ANIMATION_FIELDS:
            mode = post.get(f"animation_mode_{key}", "default")
            if mode != "custom":
                continue
            animation = self.build_simple_animation(
                post.get(f"animation_led_{key}", "center"),
                post.get(f"animation_color_{key}", "#0000ff"),
                post.get(f"animation_tempo_{key}", "25"),
                post.get(f"animation_pattern_{key}", "blink"),
            )
            if animation is None:
                errors.append(str(label))
                continue
            if animation != defaults[key]:
                configured[key] = animation
        if errors:
            return ", ".join(errors)
        config.weather_animations = configured
        return None

    def animation_to_simple_form(self, animation):
        colors = animation.get("colors") or []
        led = "center"
        color = "#0000ff"
        active_frames = []
        for frame in colors:
            for candidate in ("nose", "left", "center", "right", "bottom"):
                value = frame.get(candidate)
                if value and value != "000000":
                    led = candidate
                    color = "#" + value[-6:]
                    active_frames.append(value[-6:])
                    break
        pattern = "blink"
        if colors and len(colors) == 1:
            pattern = "static"
        elif len(set(active_frames)) > 2:
            pattern = "breath"
        return {
            "led": led,
            "color": color,
            "tempo": int(animation.get("tempo", 25)),
            "pattern": pattern,
        }

    def build_simple_animation(self, led, color, tempo, pattern):
        if led not in ("nose", "left", "center", "right"):
            return None
        try:
            tempo = max(1, min(500, int(tempo)))
        except ValueError:
            return None
        color = self.normalize_color(color)
        off = self.single_led_frame(led, "000000")
        if pattern == "static":
            colors = [self.single_led_frame(led, color)]
        elif pattern == "breath":
            colors = [
                self.single_led_frame(led, self.scale_color(color, level))
                for level in (0, 20, 40, 60, 80, 100, 80, 60, 40, 20)
            ]
        else:
            colors = [self.single_led_frame(led, color), off]
        return {"tempo": tempo, "colors": colors}

    def single_led_frame(self, led, color):
        return {
            "nose": color if led == "nose" else "000000",
            "left": color if led == "left" else "000000",
            "center": color if led == "center" else "000000",
            "right": color if led == "right" else "000000",
            "bottom": color if led == "bottom" else "000000",
        }

    def normalize_color(self, color):
        color = (color or "").strip().lstrip("#")
        if len(color) != 6:
            return "000000"
        try:
            int(color, 16)
        except ValueError:
            return "000000"
        return color.lower()

    def scale_color(self, color, percent):
        factor = percent / 100
        r = int(int(color[0:2], 16) * factor)
        g = int(int(color[2:4], 16) * factor)
        b = int(int(color[4:6], 16) * factor)
        return f"{r:02x}{g:02x}{b:02x}"

    def put(self, request, *args, **kwargs):
        put_dict = QueryDict(request.body, encoding=request._encoding)
        config = Config.load()
        config.next_performance_date = datetime.datetime.now(
            datetime.timezone.utc
        )
        config.next_performance_type = put_dict["type"]
        config.save()
        NabWeatherd.signal_daemon()
        return JsonResponse({"status": "ok"})


class RFIDDataView(TemplateView):
    template_name = "nabweatherd/rfid-data.html"

    def get(self, request, *args, **kwargs):
        """
        Unserialize RFID application data
        """
        type = "today"
        data = request.GET.get("data", None)
        if data:
            type = rfid_data.unserialize(data.encode("utf8"))
        context = self.get_context_data(**kwargs)
        context["type"] = type
        return render(request, RFIDDataView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        """
        Serialize RFID application data
        """
        type = "today"
        if "type" in request.POST:
            type = request.POST["type"]
        data = rfid_data.serialize(type)
        data = data.decode("utf8")
        return JsonResponse({"data": data})
