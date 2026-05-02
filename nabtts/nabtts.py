import datetime
import json
import logging
import sys

from asgiref.sync import sync_to_async

from nabcommon.nabservice import NabRecurrentService
from nabcommon.typing import NabdPacket

from . import rfid_data
from .tts import tts_audio_resources


class NabTTS(NabRecurrentService):
    async def get_config(self):
        from . import models

        config = await models.Config.load_async()
        return (
            config.next_performance_date,
            config.next_performance_text,
            None,
        )

    async def update_next(self, next_date, next_args):
        from . import models

        config = await models.Config.load_async()
        config.next_performance_date = next_date
        config.next_performance_text = next_args or ""
        await config.save_async()

    def compute_next(self, saved_date, saved_args, config, reason):
        if saved_date is not None:
            return saved_date, saved_args
        return None

    async def perform(self, expiration_date, args, config):
        payload = rfid_data.unserialize_payload(args)
        text = payload["text"]
        if not text:
            return
        try:
            audio_resources = await sync_to_async(
                tts_audio_resources, thread_sensitive=True
            )(text, payload["voice"], payload["style"], payload["provider"])
        except Exception as err:
            logging.error(f"text to speech failed: {err}")
            return
        if not audio_resources:
            logging.info(f"text to speech empty audio for: {text}")
            return

        packet = {
            "type": "message",
            "body": [{"audio": audio_resources}],
            "expiration": expiration_date.isoformat(),
            "request_id": "nabtts",
        }
        self.writer.write((json.dumps(packet) + "\r\n").encode("utf8"))
        await self.writer.drain()

    async def _do_perform_text(self, payload):
        now = datetime.datetime.now(datetime.timezone.utc)
        await self.perform(now + datetime.timedelta(minutes=1), payload, None)

    async def process_nabd_packet(self, packet: NabdPacket):
        if (
            packet["type"] == "rfid_event"
            and packet["app"] == "nabtts"
            and packet["event"] == "detected"
        ):
            payload = await rfid_data.read_data_ui(packet["uid"])
            if not payload["text"]:
                tag_text = rfid_data.unserialize(packet.get("data", ""))
                if tag_text != rfid_data.DATA_IN_LOCAL_DB:
                    payload = rfid_data.unserialize_payload(tag_text)
            await self._do_perform_text(payload)


if __name__ == "__main__":
    NabTTS.main(sys.argv[1:])
