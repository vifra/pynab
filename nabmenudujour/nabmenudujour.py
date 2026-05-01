import datetime
import hashlib
import json
import logging
import os
import sys
from urllib.request import Request, urlopen

from asgiref.sync import sync_to_async

from nabcommon.nabservice import NabRecurrentService
from nabcommon.typing import NabdPacket

from .menu import MenuError, fetch_menu_json, meal_for_date, tts_audio_urls


class NabMenuDuJour(NabRecurrentService):
    async def get_config(self):
        from . import models

        config = await models.Config.load_async()
        return (
            config.next_performance_date,
            config.next_performance_type,
            config.json_url,
        )

    async def update_next(self, next_date, next_args):
        from . import models

        config = await models.Config.load_async()
        config.next_performance_date = next_date
        config.next_performance_type = next_args
        await config.save_async()

    def compute_next(self, saved_date, saved_args, config, reason):
        if saved_date is not None:
            return saved_date, saved_args
        return None

    async def perform(self, expiration_date, args, config):
        try:
            data = await sync_to_async(fetch_menu_json, thread_sensitive=True)(
                config
            )
            meal = meal_for_date(data)
        except MenuError as err:
            logging.error(f"menu du jour: {err}")
            return
        except Exception as err:
            logging.error(f"menu du jour fetch failed: {err}")
            return

        meal_text = meal.get("text", "")
        audio_urls = await self._audio_resources(meal)
        if not audio_urls:
            logging.info(f"menu du jour: {meal_text}")
            return

        packet = {
            "type": "message",
            "body": [{"audio": audio_urls}],
            "expiration": expiration_date.isoformat(),
            "request_id": "nabmenudujour",
        }
        self.writer.write((json.dumps(packet) + "\r\n").encode("utf8"))
        await self.writer.drain()

    async def _audio_resources(self, meal):
        audio_url = meal.get("audio_url", "")
        if audio_url:
            return [audio_url]
        meal_text = meal.get("text", "")
        return await sync_to_async(
            self._download_tts_audio, thread_sensitive=True
        )(meal_text)

    def _download_tts_audio(self, text):
        resources = []
        for index, url in enumerate(tts_audio_urls(text)):
            digest = hashlib.sha1(url.encode("utf8")).hexdigest()  # nosec B324
            path = f"/tmp/nabmenudujour-{index}-{digest}.mp3"
            if not os.path.isfile(path):
                request = Request(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (compatible; Nabaztag Menu du Jour)"
                        )
                    },
                )
                with urlopen(request, timeout=10) as response:  # nosec B310
                    with open(path, "wb") as output:
                        output.write(response.read())
            resources.append(path)
        return resources

    async def _do_perform(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        _, _, config = await self.get_config()
        await self.perform(now + datetime.timedelta(minutes=1), "today", config)

    async def process_nabd_packet(self, packet: NabdPacket):
        if (
            packet["type"] == "asr_event"
            and packet["nlu"]["intent"] == "nabmenudujour/menu"
        ):
            await self._do_perform()
        elif (
            packet["type"] == "rfid_event"
            and packet["app"] == "nabmenudujour"
            and packet["event"] == "detected"
        ):
            await self._do_perform()


if __name__ == "__main__":
    NabMenuDuJour.main(sys.argv[1:])
