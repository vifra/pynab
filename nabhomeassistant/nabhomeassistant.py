import json
import logging
import re
import sys
import datetime

from asgiref.sync import sync_to_async
import requests

from nabcommon.nabservice import NabService
from nabtts.tts import tts_audio_resources

from . import rfid_data


def home_assistant_state_text(entity_id, state):
    attributes = state.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    name = str(attributes.get("friendly_name") or entity_id).strip()
    value = str(state.get("state", "")).strip()
    unit = str(attributes.get("unit_of_measurement") or "").strip()
    if unit:
        return f"{name} vaut {value} {unit}"
    return f"{name} vaut {value}"


def apply_speech_rewrite(action, text):
    speech_regex = action.get("speech_regex", "").strip()
    speech_replacement = action.get("speech_replacement", "")
    if not speech_regex:
        return text
    try:
        return re.sub(speech_regex, speech_replacement, text, count=1)
    except re.error as err:
        logging.error("Invalid Home Assistant speech regexp: %s", err)
        return text


class NabHomeAssistant(NabService):
    async def reload_config(self):
        pass

    async def _say(self, text):
        try:
            audio_resources = await sync_to_async(
                tts_audio_resources, thread_sensitive=True
            )(text)
        except Exception as err:
            logging.error("Home Assistant TTS failed: %s", err)
            return
        if not audio_resources:
            return
        packet = {
            "type": "message",
            "body": [{"audio": audio_resources}],
            "expiration": (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=1)
            ).isoformat(),
            "request_id": "nabhomeassistant",
        }
        self.writer.write((json.dumps(packet) + "\r\n").encode("utf8"))
        await self.writer.drain()

    async def _read_home_assistant_state(self, action, uid):
        from . import models

        config = await models.Config.load_async()
        base_url = (config.base_url or "").rstrip("/")
        access_token = config.access_token or ""
        entity_id = action.get("entity_id", "").strip()

        if not base_url or not access_token or not entity_id:
            logging.warning("Home Assistant state read is not configured for uid %s", uid)
            return

        state_url = f"{base_url}/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            result = requests.get(state_url, headers=headers, timeout=10)
            result.raise_for_status()
            state = result.json()
            if not isinstance(state, dict):
                raise ValueError("Home Assistant returned a non-object state")
        except requests.exceptions.HTTPError as err:
            status_code = (
                err.response.status_code if err.response is not None else None
            )
            logging.error(
                "Home Assistant state read failed for %s: HTTP %s",
                entity_id,
                status_code,
            )
            if status_code in (401, 403):
                await self._say(
                    "Home Assistant refuse le jeton d'acces. "
                    "Verifie le jeton dans les reglages."
                )
            elif status_code == 404:
                await self._say(
                    f"Je ne trouve pas l'entite Home Assistant {entity_id}."
                )
            else:
                await self._say(
                    "Home Assistant a renvoye une erreur en lisant cette valeur."
                )
            return
        except requests.exceptions.Timeout as err:
            logging.error("Home Assistant state read timed out: %s", err)
            await self._say("Home Assistant ne repond pas assez vite.")
            return
        except requests.exceptions.RequestException as err:
            logging.error("Home Assistant state read failed: %s", err)
            await self._say("Je n'arrive pas a joindre Home Assistant.")
            return
        except Exception as err:
            logging.error("Home Assistant state read failed: %s", err)
            await self._say(
                "Je n'arrive pas a comprendre la reponse de Home Assistant."
            )
            return

        text = home_assistant_state_text(entity_id, state)
        logging.warning("Home Assistant speech before rewrite: %s", text)
        logging.warning("Home Assistant action: %s", action)

        text = apply_speech_rewrite(action, text)
        logging.warning("Home Assistant speech after rewrite: %s", text)

        await self._say(text)

    async def _call_home_assistant(self, action, uid):
        from . import models

        config = await models.Config.load_async()
        base_url = (config.base_url or "").rstrip("/")
        access_token = config.access_token or ""
        service_path = action.get("service_path", "").strip()

        if not base_url or not access_token or "." not in service_path:
            logging.warning("Home Assistant is not configured for uid %s", uid)
            return

        domain, service = service_path.split(".", 1)
        service_url = f"{base_url}/api/services/{domain}/{service}"
        payload = {}

        service_data = action.get("service_data", "").strip()
        if service_data:
            try:
                payload = json.loads(service_data)
            except Exception as err:
                logging.error("Invalid Home Assistant JSON data: %s", err)
                return

        entity_id = action.get("entity_id", "").strip()
        if entity_id:
            payload["entity_id"] = entity_id

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        logging.info("Calling Home Assistant service %s", service_path)
        try:
            result = requests.post(
                service_url, headers=headers, json=payload, timeout=10
            )
            logging.info("Home Assistant result: %s", result.reason)
            result.raise_for_status()
        except Exception as err:
            logging.error("Home Assistant call failed: %s", err)

    async def process_nabd_packet(self, packet):
        if (
            packet["type"] == "rfid_event"
            and packet["app"] == "nabhomeassistant"
            and packet["event"] == "detected"
        ):
            action = await rfid_data.read_data_ui(packet["uid"])
            if action.get("action_type") == "call_service":
                await self._call_home_assistant(action, packet["uid"])
            else:
                await self._read_home_assistant_state(action, packet["uid"])


if __name__ == "__main__":
    NabHomeAssistant.main(sys.argv[1:])
