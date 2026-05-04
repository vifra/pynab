import logging
import sys

from nabcommon.nabservice import NabService

from . import audio_config, rfid_data


class NabSound(NabService):
    def __init__(self):
        super().__init__()

    async def reload_config(self):
        pass

    async def process_nabd_packet(self, packet):
        if (
            packet["type"] == "rfid_event"
            and packet["app"] == "nabsound"
            and packet["event"] == "detected"
        ):
            action = rfid_data.unserialize(packet.get("data", "reset"))
            status = self.apply_action(action)
            if status["ok"]:
                logging.info("Applied NFC sound action: %s", action)
            else:
                logging.error(
                    "NFC sound action %s failed: %s",
                    action,
                    status["message"],
                )

    def apply_action(self, action):
        if rfid_data.is_set_action(action):
            return audio_config.set_speaker_base(
                rfid_data.set_action_value(action)
            )
        if action == "mute":
            return audio_config.mute_speaker()
        if action == "up":
            return audio_config.volume_up()
        if action == "down":
            return audio_config.volume_down()
        return audio_config.reset_speaker_volume()


if __name__ == "__main__":
    NabSound.main(sys.argv[1:])
