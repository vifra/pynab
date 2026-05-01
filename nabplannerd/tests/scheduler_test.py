import datetime
import unittest

from nabplannerd.models import ScheduledRule
from nabplannerd.scheduler import due_trigger_key


class SchedulerTest(unittest.TestCase):
    def test_fixed_time_allows_scheduler_tick_after_exact_minute(self):
        rule = ScheduledRule(
            id=1,
            enabled=True,
            mode=ScheduledRule.MODE_TIMES,
            trigger_times=["14:20"],
            weekdays=[4],
        )

        key = due_trigger_key(
            rule,
            datetime.datetime(2026, 5, 1, 14, 21, 5),
        )

        self.assertEqual(key, "2026-05-01:1:time:14:20")

    def test_fixed_time_does_not_trigger_old_time(self):
        rule = ScheduledRule(
            id=1,
            enabled=True,
            mode=ScheduledRule.MODE_TIMES,
            trigger_times=["14:20"],
            weekdays=[4],
        )

        key = due_trigger_key(
            rule,
            datetime.datetime(2026, 5, 1, 14, 23, 0),
        )

        self.assertIsNone(key)

    def test_interval_uses_due_slot_key(self):
        rule = ScheduledRule(
            id=2,
            enabled=True,
            mode=ScheduledRule.MODE_INTERVAL,
            start_time=datetime.time(10, 30),
            end_time=datetime.time(19, 30),
            interval_minutes=60,
            weekdays=[4],
        )

        key = due_trigger_key(
            rule,
            datetime.datetime(2026, 5, 1, 11, 31, 0),
        )

        self.assertEqual(key, "2026-05-01:2:interval:11:30")
