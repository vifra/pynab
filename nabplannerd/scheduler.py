import datetime
import logging
from typing import Iterable, Optional

from asgiref.sync import sync_to_async
from dateutil import tz

from .models import ScheduledRule


TRIGGER_GRACE_MINUTES = 2

SERVICE_CHOICES = [
    ("nabweatherd", "Meteo"),
    ("nabmenudujour", "Menu du jour"),
    ("nabtaichid", "Tai Chi"),
    ("nabsurprised", "Humeurs"),
]

ACTION_CHOICES = {
    "nabweatherd": [
        ("today", "Aujourd'hui"),
        ("tomorrow", "Demain"),
    ],
    "nabmenudujour": [
        ("today", "Menu du jour"),
    ],
    "nabtaichid": [
        ("active_window", "Plage active"),
    ],
    "nabsurprised": [
        ("active_window", "Plage active"),
    ],
}


def available_services():
    return SERVICE_CHOICES


def available_actions():
    return ACTION_CHOICES


def local_now():
    return datetime.datetime.now(tz=tz.gettz(get_system_tz()))


def get_system_tz():
    try:
        with open("/etc/timezone") as timezone_file:
            return timezone_file.read().strip()
    except OSError:
        return None


async def run_due_rules(now: Optional[datetime.datetime] = None):
    if now is None:
        now = local_now()
    rules = await sync_to_async(list, thread_sensitive=True)(
        ScheduledRule.objects.filter(enabled=True)
    )
    for rule in rules:
        due_key = due_trigger_key(rule, now)
        if due_key is None or due_key == rule.last_triggered_key:
            continue
        try:
            logging.info(f"planner triggering {rule.service}/{rule.action}")
            await trigger_service(rule.service, rule.action)
        except Exception as err:
            logging.error(f"planner trigger failed for {rule.name}: {err}")
            continue
        rule.last_triggered_key = due_key
        await sync_to_async(rule.save, thread_sensitive=True)(
            update_fields=["last_triggered_key"]
        )


def due_trigger_key(rule: ScheduledRule, now: datetime.datetime):
    if not is_active_weekday(rule, now.weekday()):
        return None
    current_time = now.time().replace(second=0, microsecond=0)
    if rule.mode == ScheduledRule.MODE_WINDOW or rule.action == "active_window":
        return None
    if rule.mode == ScheduledRule.MODE_INTERVAL:
        return interval_due_key(rule, now, current_time)
    return fixed_time_due_key(rule, now, current_time)


def fixed_time_due_key(
    rule: ScheduledRule, now: datetime.datetime, current_time: datetime.time
):
    current_minutes = minutes_since_midnight(current_time)
    for trigger_time in parse_times(rule.trigger_times):
        trigger_minutes = minutes_since_midnight(trigger_time)
        if 0 <= current_minutes - trigger_minutes < TRIGGER_GRACE_MINUTES:
            return (
                f"{now.date().isoformat()}:{rule.id}:time:"
                f"{trigger_time.strftime('%H:%M')}"
            )
    return None


def interval_due_key(
    rule: ScheduledRule, now: datetime.datetime, current_time: datetime.time
):
    if not rule.interval_minutes or rule.interval_minutes <= 0:
        return None
    start_time = rule.start_time or datetime.time(0, 0)
    end_time = rule.end_time or datetime.time(23, 59)
    if not is_in_window(current_time, start_time, end_time):
        return None

    current_minutes = minutes_since_midnight(current_time)
    start_minutes = minutes_since_midnight(start_time)
    if end_time < start_time and current_time < start_time:
        current_minutes += 24 * 60
    elapsed = current_minutes - start_minutes
    if elapsed < 0:
        return None
    due_delta = elapsed % rule.interval_minutes
    if due_delta >= TRIGGER_GRACE_MINUTES:
        return None
    due_minutes = current_minutes - due_delta
    due_time = datetime.time(due_minutes // 60 % 24, due_minutes % 60)
    return (
        f"{now.date().isoformat()}:{rule.id}:interval:"
        f"{due_time.strftime('%H:%M')}"
    )


def is_in_window(
    current_time: datetime.time,
    start_time: Optional[datetime.time],
    end_time: Optional[datetime.time],
):
    if start_time is None and end_time is None:
        return True
    if start_time is None:
        return current_time <= end_time
    if end_time is None:
        return current_time >= start_time
    if start_time <= end_time:
        return start_time <= current_time <= end_time
    return current_time >= start_time or current_time <= end_time


def parse_times(values: Iterable[str]):
    times = []
    for value in values or []:
        try:
            hour, minute = str(value).split(":")[:2]
            times.append(datetime.time(int(hour), int(minute)))
        except (TypeError, ValueError):
            pass
    return times


def minutes_since_midnight(value: datetime.time):
    return value.hour * 60 + value.minute


def is_active_weekday(rule: ScheduledRule, weekday: int):
    weekdays = rule.weekdays
    if weekdays is None or weekdays == []:
        return True
    return weekday in [int(day) for day in weekdays]


async def trigger_service(service, action):
    if service == "nabweatherd":
        from nabweatherd.models import Config
        from nabweatherd.nabweatherd import NabWeatherd

        config = await Config.load_async()
        config.next_performance_date = datetime.datetime.now(
            datetime.timezone.utc
        )
        config.next_performance_type = action or "today"
        await config.save_async()
        NabWeatherd.signal_daemon()
    elif service == "nabmenudujour":
        from nabmenudujour.models import Config
        from nabmenudujour.nabmenudujour import NabMenuDuJour

        config = await Config.load_async()
        config.next_performance_date = datetime.datetime.now(
            datetime.timezone.utc
        )
        config.next_performance_type = action or "today"
        await config.save_async()
        NabMenuDuJour.signal_daemon()
    elif service == "nabtaichid":
        from nabtaichid.nabtaichid import NabTaichid

        NabTaichid.signal_daemon()
    elif service == "nabsurprised":
        from nabsurprised.nabsurprised import NabSurprised

        NabSurprised.signal_daemon()
    else:
        raise ValueError(f"Unknown planned service: {service}")
