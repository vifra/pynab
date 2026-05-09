import unittest
from unittest import mock

import pytest
import requests
from asgiref.sync import async_to_sync
from django.test import Client

from nabd.tests.utils import close_old_async_connections
from nabhomeassistant import models
from nabhomeassistant.nabhomeassistant import NabHomeAssistant


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.exceptions.HTTPError(
                f"{self.status_code} Error"
            )
            error.response = self
            raise error

    def json(self):
        return self._json_data


@pytest.mark.django_db
class TestNabHomeAssistant(unittest.TestCase):
    def tearDown(self):
        close_old_async_connections()

    def _configure_home_assistant(self):
        config = models.Config.load()
        config.base_url = "http://homeassistant.local:8123/"
        config.access_token = "token"
        config.save()

    def _service_with_spoken_texts(self):
        service = NabHomeAssistant()
        spoken_texts = []

        async def say(text):
            spoken_texts.append(text)

        service._say = say
        return service, spoken_texts

    def test_read_state_says_value(self):
        self._configure_home_assistant()
        service, spoken_texts = self._service_with_spoken_texts()
        action = {"entity_id": "sensor.salon_temperature"}

        with mock.patch(
            "nabhomeassistant.nabhomeassistant.requests.get",
            return_value=FakeResponse(
                json_data={
                    "state": "21.5",
                    "attributes": {
                        "friendly_name": "Temperature salon",
                        "unit_of_measurement": "C",
                    },
                }
            ),
        ) as get:
            async_to_sync(service._read_home_assistant_state)(action, "uid")

        get.assert_called_once_with(
            "http://homeassistant.local:8123/api/states/"
            "sensor.salon_temperature",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )
        self.assertEqual(spoken_texts, ["Temperature salon vaut 21.5 C"])

    def test_read_state_reports_missing_entity(self):
        self._configure_home_assistant()
        service, spoken_texts = self._service_with_spoken_texts()
        action = {"entity_id": "sensor.inconnue"}

        with mock.patch(
            "nabhomeassistant.nabhomeassistant.requests.get",
            return_value=FakeResponse(status_code=404),
        ):
            async_to_sync(service._read_home_assistant_state)(action, "uid")

        self.assertEqual(
            spoken_texts,
            ["Je ne trouve pas l'entite Home Assistant sensor.inconnue."],
        )

    def test_read_state_reports_invalid_token(self):
        self._configure_home_assistant()
        service, spoken_texts = self._service_with_spoken_texts()
        action = {"entity_id": "sensor.salon_temperature"}

        with mock.patch(
            "nabhomeassistant.nabhomeassistant.requests.get",
            return_value=FakeResponse(status_code=401),
        ):
            async_to_sync(service._read_home_assistant_state)(action, "uid")

        self.assertEqual(
            spoken_texts,
            [
                "Home Assistant refuse le jeton d'acces. "
                "Verifie le jeton dans les reglages."
            ],
        )


@pytest.mark.django_db
class TestNabHomeAssistantViews(unittest.TestCase):
    def setUp(self):
        config = models.Config.load()
        config.base_url = "http://homeassistant.local:8123/"
        config.access_token = "token"
        config.save()
        self.client = Client()

    def test_test_connection(self):
        with mock.patch(
            "nabhomeassistant.views.requests.get",
            return_value=FakeResponse(json_data={"message": "API running."}),
        ) as get:
            response = self.client.get("/nabhomeassistant/test-connection")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        get.assert_called_once_with(
            "http://homeassistant.local:8123/api/",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )

    def test_entities(self):
        with mock.patch(
            "nabhomeassistant.views.requests.get",
            return_value=FakeResponse(
                json_data=[
                    {
                        "entity_id": "sensor.salon_temperature",
                        "state": "21.5",
                        "attributes": {
                            "friendly_name": "Temperature salon",
                            "unit_of_measurement": "C",
                        },
                    }
                ]
            ),
        ):
            response = self.client.get("/nabhomeassistant/entities")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["entities"],
            [
                {
                    "entity_id": "sensor.salon_temperature",
                    "name": "Temperature salon",
                    "state": "21.5",
                    "unit": "C",
                }
            ],
        )

    def test_preview_state(self):
        with mock.patch(
            "nabhomeassistant.views.requests.get",
            return_value=FakeResponse(
                json_data={
                    "state": "21.5",
                    "attributes": {
                        "friendly_name": "Temperature salon",
                        "unit_of_measurement": "C",
                    },
                }
            ),
        ) as get:
            response = self.client.get(
                "/nabhomeassistant/preview-state",
                {"entity_id": "sensor.salon_temperature"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "entity_id": "sensor.salon_temperature",
                "name": "Temperature salon",
                "value": "21.5 C",
                "spoken_text": "Temperature salon vaut 21.5 C",
            },
        )
        get.assert_called_once_with(
            "http://homeassistant.local:8123/api/states/"
            "sensor.salon_temperature",
            headers={"Authorization": "Bearer token"},
            timeout=10,
        )

    def test_preview_state_applies_speech_rewrite(self):
        with mock.patch(
            "nabhomeassistant.views.requests.get",
            return_value=FakeResponse(
                json_data={
                    "state": "2396.0",
                    "attributes": {
                        "friendly_name": "SOLR Day Production",
                        "unit_of_measurement": "Wh",
                    },
                }
            ),
        ):
            response = self.client.get(
                "/nabhomeassistant/preview-state",
                {
                    "entity_id": "sensor.solr_day_production",
                    "speech_regex": r"^SOLR Day Production vaut (.+) Wh$",
                    "speech_replacement": r"La production est de \1 Watt heure",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["spoken_text"],
            "La production est de 2396.0 Watt heure",
        )
