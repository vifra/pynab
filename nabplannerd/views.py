import datetime

from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.generic import View

from .models import ScheduledRule
from .nabplannerd import NabPlannerD
from .scheduler import (
    available_actions,
    available_services,
    is_active_weekday,
    is_in_window,
    minutes_since_midnight,
    parse_times,
    trigger_service,
)
from nabsound import rfid_data as sound_rfid_data
from nabtts import rfid_data as tts_rfid_data
from nabtts.tts import (
    EDGE_VOICE_CHOICES,
    GOOGLE_VOICE_CHOICES,
    PROVIDER_CHOICES,
    STYLE_CHOICES,
    VOICE_CHOICES,
)


WEEKDAYS = [
    (0, "Lundi"),
    (1, "Mardi"),
    (2, "Mercredi"),
    (3, "Jeudi"),
    (4, "Vendredi"),
    (5, "Samedi"),
    (6, "Dimanche"),
]

TIMELINE_START_HOUR = 0
TIMELINE_END_HOUR = 23
TIMELINE_HOURS = 24
MAX_INTERVAL_POINTS = 48


class PlannerView(View):
    template_name = "nabplannerd/index.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.context())

    def post(self, request, *args, **kwargs):
        if not is_valid_rule_form(request.POST):
            return HttpResponseRedirect(reverse("nabplanner.index"))
        rule_id = request.POST.get("rule_id", "")
        if rule_id:
            rule = get_object_or_404(ScheduledRule, pk=int(rule_id))
        else:
            rule = ScheduledRule()
        apply_rule_form(rule, request.POST)
        rule.save()
        notify_rule_service(rule)
        NabPlannerD.signal_daemon()
        return HttpResponseRedirect(reverse("nabplanner.index"))

    def context(self):
        rules = list(ScheduledRule.objects.all())
        decorate_rules(rules)
        sleep_segments = clock_sleep_segments()
        return {
            "rules": rules,
            "services": available_services(),
            "actions": available_actions(),
            "provider_choices": PROVIDER_CHOICES,
            "voice_choices": VOICE_CHOICES,
            "edge_voice_values": [value for value, label in EDGE_VOICE_CHOICES],
            "google_voice_values": [
                value for value, label in GOOGLE_VOICE_CHOICES
            ],
            "style_choices": STYLE_CHOICES,
            "weekdays": WEEKDAYS,
            "timeline_hours": timeline_hours(),
            "timeline": build_timeline(rules, sleep_segments),
        }


def is_valid_rule_form(post):
    service = post.get("service", "")
    mode = post.get("mode", "")
    services = [service_id for service_id, service_name in available_services()]
    modes = [
        ScheduledRule.MODE_TIMES,
        ScheduledRule.MODE_INTERVAL,
        ScheduledRule.MODE_WINDOW,
    ]
    return service in services and mode in modes


class RuleDeleteView(View):
    def post(self, request, rule_id, *args, **kwargs):
        rule = get_object_or_404(ScheduledRule, pk=rule_id)
        notify_rule_service(rule)
        rule.delete()
        NabPlannerD.signal_daemon()
        return HttpResponseRedirect(reverse("nabplanner.index"))


class RuleRunView(View):
    def post(self, request, rule_id, *args, **kwargs):
        import asyncio

        rule = get_object_or_404(ScheduledRule, pk=rule_id)
        asyncio.run(trigger_service(rule.service, rule.action))
        return JsonResponse({"status": "ok"})


def apply_rule_form(rule, post):
    rule.service = post.get("service", "")
    rule.action = post.get("action", "")
    rule.name = service_name(rule.service)
    if rule.service == "nabtts":
        rule.action = tts_rfid_data.serialize_payload(
            post.get("tts_message", ""),
            post.get("tts_voice", ""),
            post.get("tts_style", ""),
            post.get("tts_provider", ""),
        )
    if rule.service == "nabsound":
        rule.action = sound_rfid_data.serialize(
            "set",
            post.get("sound_value", ""),
        ).decode("utf8")
    if rule.service in ("nabtaichid", "nabsurprised"):
        rule.action = "active_window"
    rule.color = normalize_color(post.get("color", ""))
    rule.enabled = post.get("enabled") == "on"
    rule.mode = post.get("mode", ScheduledRule.MODE_TIMES)
    if rule.service in ("nabtaichid", "nabsurprised") or rule.action == "active_window":
        rule.mode = ScheduledRule.MODE_WINDOW
    if rule.service == "nabsound":
        rule.mode = ScheduledRule.MODE_TIMES
    rule.weekdays = parse_weekdays(post.getlist("weekdays"))
    if rule.mode == ScheduledRule.MODE_WINDOW:
        rule.start_time = parse_time(post.get("start_time", ""))
        rule.end_time = parse_time(post.get("end_time", ""))
        rule.trigger_times = []
        rule.interval_minutes = None
    elif rule.mode == ScheduledRule.MODE_INTERVAL:
        rule.start_time = parse_time(
            post.get("interval_start_time", "") or post.get("start_time", "")
        )
        rule.end_time = parse_time(
            post.get("interval_end_time", "") or post.get("end_time", "")
        )
        rule.trigger_times = []
        rule.interval_minutes = parse_int(post.get("interval_minutes", ""))
    else:
        rule.start_time = None
        rule.end_time = None
        rule.trigger_times = parse_trigger_times(post.get("trigger_times", ""))
        rule.interval_minutes = None
    rule.last_triggered_key = None


def parse_time(value):
    value = value.strip()
    if not value:
        return None
    hour, minute = value.split(":")[:2]
    return datetime.time(int(hour), int(minute))


def parse_trigger_times(value):
    times = []
    for part in value.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        parsed = parse_time(part)
        if parsed is not None:
            times.append(parsed.strftime("%H:%M"))
    return times


def parse_int(value):
    value = value.strip()
    if not value:
        return None
    return int(value)


def notify_rule_service(rule):
    if rule.service == "nabtaichid":
        from nabtaichid.nabtaichid import NabTaichid

        NabTaichid.signal_daemon()
    elif rule.service == "nabsurprised":
        from nabsurprised.nabsurprised import NabSurprised

        NabSurprised.signal_daemon()


def service_name(service):
    for service_id, label in available_services():
        if service_id == service:
            return label
    return service


def parse_weekdays(values):
    if not values:
        return []
    return [int(value) for value in values]


def decorate_rules(rules):
    for rule in rules:
        rule.weekday_set = set(int(day) for day in (rule.weekdays or []))
        rule.weekday_labels = [
            label for value, label in WEEKDAYS if value in rule.weekday_set
        ]
        rule.timeline_label = display_rule(rule)
        rule.display_color = rule_color(rule)
        rule.display_text_color = contrast_text_color(rule.display_color)
        if rule.service == "nabtts":
            payload = tts_rfid_data.unserialize_payload(rule.action)
            rule.tts_message = payload["text"]
            rule.tts_provider = payload["provider"]
            rule.tts_voice = payload["voice"]
            rule.tts_style = payload["style"]
        if rule.service == "nabsound":
            action = sound_rfid_data.unserialize(rule.action)
            rule.sound_value = sound_rfid_data.set_action_value(action)


def build_timeline(rules, sleep_segments):
    rows = []
    for weekday, label in WEEKDAYS:
        items = []
        for rule in rules:
            if not is_active_weekday(rule, weekday):
                continue
            segment = timeline_segment(rule)
            if segment is not None:
                items.append(segment)
        rows.append(
            {
                "label": label,
                "sleep_segments": sleep_segments[weekday],
                "segments": layout_timeline_items(items),
            }
        )
    return rows


def layout_timeline_items(items):
    lanes = []
    for item in items:
        if item["kind"] == "points":
            item["lane"] = 0
            continue
        start = float(item["left"])
        end = start + float(item["width"])
        lane_index = first_available_lane(lanes, start, end)
        if lane_index == len(lanes):
            lanes.append([])
        lanes[lane_index].append((start, end))
        item["lane"] = lane_index
    lane_count = max(len(lanes), 1)
    for item in items:
        item["lane_count"] = lane_count
    return items


def first_available_lane(lanes, start, end):
    for index, lane in enumerate(lanes):
        if all(end <= other_start or start >= other_end for other_start, other_end in lane):
            return index
    return len(lanes)


def timeline_hours():
    hours = []
    hour_count = TIMELINE_HOURS
    for index, hour in enumerate(range(TIMELINE_START_HOUR, TIMELINE_END_HOUR + 1)):
        hours.append(
            {
                "label": f"{hour}h",
                "left": f"{(index / hour_count) * 100:.3f}",
            }
        )
    return hours


def timeline_segment(rule):
    if is_window_rule(rule):
        return timeline_window(rule)
    if rule.mode == ScheduledRule.MODE_TIMES:
        return timeline_points(rule)
    return timeline_interval(rule)


def timeline_window(rule):
    start_minutes = minutes_since_midnight(rule.start_time) if rule.start_time else 0
    end_minutes = (
        minutes_since_midnight(rule.end_time)
        if rule.end_time
        else 24 * 60 - 1
    )
    visible_start = TIMELINE_START_HOUR * 60
    visible_end = TIMELINE_HOURS * 60
    if end_minutes < start_minutes:
        end_minutes = 24 * 60 - 1
    start_minutes = max(start_minutes, visible_start)
    end_minutes = min(end_minutes, visible_end)
    if end_minutes <= start_minutes:
        return None

    total = visible_end - visible_start
    left = ((start_minutes - visible_start) / total) * 100
    width = ((end_minutes - start_minutes) / total) * 100
    return {
        "kind": "segment",
        "rule_id": rule.id,
        "label": display_rule(rule),
        "class": service_class(rule.service, rule.enabled),
        "color": rule_color(rule),
        "text_color": contrast_text_color(rule_color(rule)),
        "left": f"{left:.3f}",
        "width": f"{width:.3f}",
        "markers": timeline_markers(rule, start_minutes, end_minutes, total),
    }


def timeline_points(rule):
    visible_start = TIMELINE_START_HOUR * 60
    visible_end = TIMELINE_HOURS * 60
    points = []
    for trigger_time in parse_times(rule.trigger_times):
        minute = minutes_since_midnight(trigger_time)
        if not is_in_window(trigger_time, rule.start_time, rule.end_time):
            continue
        if visible_start <= minute < visible_end:
            points.append(
                {
                    "left": f"{((minute - visible_start) / (visible_end - visible_start)) * 100:.3f}",
                    "time": trigger_time.strftime("%H:%M"),
                }
            )
    if not points:
        return None
    return {
        "kind": "points",
        "rule_id": rule.id,
        "label": display_rule(rule),
        "service_name": rule.name,
        "class": service_class(rule.service, rule.enabled),
        "color": rule_color(rule),
        "points": points,
    }


def timeline_interval(rule):
    points = interval_points(rule)
    if points and len(points) <= MAX_INTERVAL_POINTS:
        return {
            "kind": "points",
            "rule_id": rule.id,
            "label": display_rule(rule),
            "service_name": rule.name,
            "class": service_class(rule.service, rule.enabled),
            "color": rule_color(rule),
            "points": points,
        }
    return timeline_window(rule)


def interval_points(rule):
    if not rule.interval_minutes or rule.interval_minutes <= 0 or not rule.start_time:
        return []
    start_minutes = minutes_since_midnight(rule.start_time)
    end_minutes = (
        minutes_since_midnight(rule.end_time)
        if rule.end_time
        else 24 * 60 - 1
    )
    if end_minutes < start_minutes:
        end_minutes = 24 * 60 - 1

    visible_start = TIMELINE_START_HOUR * 60
    visible_end = TIMELINE_HOURS * 60
    minute = max(start_minutes, visible_start)
    if minute > start_minutes:
        offset = (minute - start_minutes) % rule.interval_minutes
        if offset:
            minute += rule.interval_minutes - offset

    points = []
    while minute <= end_minutes and minute < visible_end:
        points.append(
            {
                "left": f"{((minute - visible_start) / (visible_end - visible_start)) * 100:.3f}",
                "time": f"{minute // 60:02d}:{minute % 60:02d}",
            }
        )
        minute += rule.interval_minutes
    return points


def timeline_markers(rule, start_minutes, end_minutes, total):
    markers = []
    if rule.mode == ScheduledRule.MODE_INTERVAL:
        if not rule.interval_minutes:
            return markers
        minute = minutes_since_midnight(rule.start_time) if rule.start_time else 0
        while minute <= end_minutes:
            if minute >= start_minutes:
                markers.append(marker_position(minute, start_minutes, end_minutes))
            minute += rule.interval_minutes
    else:
        for trigger_time in parse_times(rule.trigger_times):
            minute = minutes_since_midnight(trigger_time)
            if start_minutes <= minute <= end_minutes:
                markers.append(marker_position(minute, start_minutes, end_minutes))
    return markers


def marker_position(minute, start_minutes, end_minutes):
    duration = end_minutes - start_minutes
    if duration <= 0:
        return "0"
    return f"{((minute - start_minutes) / duration) * 100:.3f}"


def display_rule(rule):
    if rule.service == "nabtts":
        payload = tts_rfid_data.unserialize_payload(rule.action)
        message = payload["text"]
        if len(message) > 28:
            message = message[:28].strip() + "..."
        if not message:
            message = "Message"
        return f"{rule.name} - {message}"
    if rule.service == "nabsound":
        action = sound_rfid_data.unserialize(rule.action)
        if sound_rfid_data.is_set_action(action):
            return (
                f"{rule.name} - volume "
                f"{sound_rfid_data.set_action_value(action)}"
            )
        return f"{rule.name} - {action}"
    if is_window_rule(rule):
        return rule.name
    elif rule.mode == ScheduledRule.MODE_INTERVAL:
        cadence = f"toutes les {rule.interval_minutes} min"
        if rule.start_time:
            cadence = f"{cadence} a partir de {rule.start_time.strftime('%H:%M')}"
        if rule.end_time:
            cadence = f"{cadence} jusqu'a {rule.end_time.strftime('%H:%M')}"
    else:
        cadence = ", ".join(rule.trigger_times or [])
    return f"{rule.name} - {cadence}"


def is_window_rule(rule):
    return (
        rule.service in ("nabtaichid", "nabsurprised")
        or rule.mode == ScheduledRule.MODE_WINDOW
        or rule.action == "active_window"
    )


def service_class(service, enabled):
    if not enabled:
        return "planner-service-disabled"
    if service == "nabweatherd":
        return "planner-service-weather"
    if service == "nabmenudujour":
        return "planner-service-menu"
    if service == "nabtts":
        return "planner-service-tts"
    if service == "nabsound":
        return "planner-service-sound"
    if service == "nabtaichid":
        return "planner-service-taichi"
    if service == "nabsurprised":
        return "planner-service-surprise"
    return "planner-service-default"


def normalize_color(value):
    value = value.strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            pass
    return ""


def rule_color(rule):
    if rule.color:
        return rule.color
    if not rule.enabled:
        return "#adb5bd"
    if rule.service == "nabweatherd":
        return "#2077b4"
    if rule.service == "nabmenudujour":
        return "#27865a"
    if rule.service == "nabtts":
        return "#5b6c8f"
    if rule.service == "nabsound":
        return "#6f42c1"
    if rule.service == "nabtaichid":
        return "#b45f06"
    if rule.service == "nabsurprised":
        return "#c2185b"
    return "#6f42c1"


def contrast_text_color(background_color):
    color = normalize_color(background_color)
    if not color:
        return "#ffffff"
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    luminance = (red * 299 + green * 587 + blue * 114) / 1000
    return "#212529" if luminance >= 150 else "#ffffff"


def clock_sleep_segments():
    from nabclockd.models import Config

    config = Config.load()
    segments_by_day = {}
    for weekday, day_name in enumerate(
        [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
    ):
        wakeup, sleep = clock_times_for_day(config, day_name)
        segments_by_day[weekday] = sleep_segments_for_day(wakeup, sleep)
    return segments_by_day


def clock_times_for_day(config, day_name):
    if config.settings_per_day:
        wakeup = datetime.time(
            getattr(config, "wakeup_hour_" + day_name),
            getattr(config, "wakeup_min_" + day_name),
        )
        sleep = datetime.time(
            getattr(config, "sleep_hour_" + day_name),
            getattr(config, "sleep_min_" + day_name),
        )
    else:
        wakeup = datetime.time(config.wakeup_hour, config.wakeup_min)
        sleep = datetime.time(config.sleep_hour, config.sleep_min)
    return wakeup, sleep


def sleep_segments_for_day(wakeup, sleep):
    wakeup_min = minutes_since_midnight(wakeup)
    sleep_min = minutes_since_midnight(sleep)
    if wakeup_min == sleep_min:
        return []
    if sleep_min > wakeup_min:
        ranges = [(0, wakeup_min), (sleep_min, 24 * 60)]
    else:
        ranges = [(sleep_min, wakeup_min)]
    return [timeline_range_segment(start, end) for start, end in ranges if end > start]


def timeline_range_segment(start_minute, end_minute):
    total = TIMELINE_HOURS * 60
    return {
        "left": f"{(start_minute / total) * 100:.3f}",
        "width": f"{((end_minute - start_minute) / total) * 100:.3f}",
    }
