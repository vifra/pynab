import asyncio
import datetime
import unittest
from unittest import mock

import pytest

from nabplannerd.models import ScheduledRule
from nabplannerd.scheduler import due_trigger_key, trigger_service


class FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


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

    @mock.patch("nabsound.audio_config.set_speaker_base")
    def test_trigger_sound_sets_speaker_base(self, set_speaker_base):
        set_speaker_base.return_value = {"ok": True, "message": ""}

        asyncio.run(trigger_service("nabsound", "set:210"))

        set_speaker_base.assert_called_once_with(210)


@pytest.mark.django_db
class SchedulerDBTest(unittest.TestCase):
    @mock.patch("nabtts.nabtts.NabTTS.signal_daemon")
    @mock.patch("nabplannerd.scheduler.requests.get")
    def test_trigger_homeassistant_reads_entity_and_schedules_tts(
        self, requests_get, signal_daemon
    ):
        from nabhomeassistant.models import Config as HomeAssistantConfig
        from nabplannerd.scheduler import serialize_homeassistant_action
        from nabtts import rfid_data as tts_rfid_data
        from nabtts.models import Config as TTSConfig

        homeassistant_config = HomeAssistantConfig.load()
        homeassistant_config.base_url = "http://homeassistant.local:8123/"
        homeassistant_config.access_token = "token"
        homeassistant_config.save()
        requests_get.return_value = FakeResponse(
            {
                "state": "2396.0",
                "attributes": {
                    "friendly_name": "SOLR Day Production ",
                    "unit_of_measurement": "Wh",
                },
            }
        )
        action = serialize_homeassistant_action(
            "sensor.solr_day_production",
            r"^SOLR Day Production vaut (.+) Wh$",
            r"La production solaire est de \1 Watt heure",
        )

        asyncio.run(trigger_service("nabhomeassistant", action))

        tts_config = TTSConfig.load()
        payload = tts_rfid_data.unserialize_payload(
            tts_config.next_performance_text
        )
        self.assertEqual(
            payload["text"], "La production solaire est de 2396.0 Watt heure"
        )
        requests_get.assert_called_once_with(
            "http://homeassistant.local:8123/api/states/"
            "sensor.solr_day_production",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )
        signal_daemon.assert_called_once()
