import datetime
import random
import sys

from asgiref.sync import sync_to_async

from nabcommon.nabservice import NabRandomService, NabRecurrentService
from nabcommon.typing import NabdPacket


class NabTaichid(NabRandomService):
    DAEMON_PIDFILE = "/run/nabtaichid.pid"

    async def get_config(self):
        from . import models
        from nabplannerd.models import ScheduledRule

        config = await models.Config.load_async()
        windows = await sync_to_async(list, thread_sensitive=True)(
            ScheduledRule.objects.filter(
                enabled=True,
                service="nabtaichid",
            )
        )
        return (
            config.next_taichi,
            None,
            (config.taichi_frequency, self.serialize_windows(windows)),
        )

    async def update_next(self, next_date, next_args):
        from . import models

        config = await models.Config.load_async()
        config.next_taichi = next_date
        await config.save_async()

    async def perform(self, expiration, args, config):
        packet = (
            '{"type":"command",'
            '"sequence":[{"choreography":"nabtaichid/taichi.chor"}],'
            '"expiration":"' + expiration.isoformat() + '"}\r\n'
        )
        self.writer.write(packet.encode("utf8"))
        await self.writer.drain()

    def compute_random_delta(self, frequency):
        return (256 - frequency) * 60 * (random.uniform(0, 255) + 64) / 128

    def compute_next(self, saved_date, saved_args, config, reason):
        frequency, windows = config
        now = datetime.datetime.now(datetime.timezone.utc)
        if saved_date is not None and saved_date < now:
            return saved_date, saved_args
        if (
            reason == NabRecurrentService.Reason.BOOT
            and saved_date is not None
            and self.is_in_active_window(saved_date, windows)
        ):
            return saved_date, saved_args
        if frequency == 0:
            return None
        next_date = now + datetime.timedelta(
            seconds=self.compute_random_delta(frequency)
        )
        return (self.adjust_to_active_window(next_date, windows), None)

    def serialize_windows(self, windows):
        return [
            {
                "weekdays": rule.weekdays or [],
                "start": rule.start_time,
                "end": rule.end_time,
            }
            for rule in windows
        ]

    def is_in_active_window(self, date, windows):
        if not windows:
            return True
        local_date = date.astimezone()
        local_time = local_date.time().replace(second=0, microsecond=0)
        weekday = local_date.weekday()
        for window in windows:
            weekdays = [int(day) for day in window["weekdays"]]
            if weekdays and weekday not in weekdays:
                continue
            if self.time_in_window(local_time, window["start"], window["end"]):
                return True
        return False

    def adjust_to_active_window(self, date, windows):
        if not windows or self.is_in_active_window(date, windows):
            return date
        local_now = datetime.datetime.now().astimezone()
        local_candidate = date.astimezone()
        search_from = max(local_now, local_candidate)
        for day_delta in range(0, 8):
            day = (search_from + datetime.timedelta(days=day_delta)).date()
            weekday = day.weekday()
            for window in windows:
                weekdays = [int(day) for day in window["weekdays"]]
                if weekdays and weekday not in weekdays:
                    continue
                start = window["start"] or datetime.time(0, 0)
                candidate = datetime.datetime.combine(
                    day, start, tzinfo=search_from.tzinfo
                )
                if candidate >= search_from:
                    return candidate.astimezone(datetime.timezone.utc)
        return date

    def time_in_window(self, current_time, start_time, end_time):
        if start_time is None and end_time is None:
            return True
        if start_time is None:
            return current_time <= end_time
        if end_time is None:
            return current_time >= start_time
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        return current_time >= start_time or current_time <= end_time

    async def process_nabd_packet(self, packet: NabdPacket):
        if (
            packet["type"] == "asr_event"
            and packet["nlu"]["intent"] == "nabtaichid/taichi"
        ):
            now = datetime.datetime.now(datetime.timezone.utc)
            expiration = now + datetime.timedelta(minutes=1)
            await self.perform(expiration, None, None)
        elif (
            packet["type"] == "rfid_event"
            and packet["app"] == "nabtaichid"
            and packet["event"] == "detected"
        ):
            now = datetime.datetime.now(datetime.timezone.utc)
            expiration = now + datetime.timedelta(minutes=1)
            await self.perform(expiration, None, None)


if __name__ == "__main__":
    NabTaichid.main(sys.argv[1:])
