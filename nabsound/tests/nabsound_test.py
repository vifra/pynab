import unittest

from nabsound import rfid_data


class TestNabSoundRFIDData(unittest.TestCase):
    def test_serialize_regular_actions(self):
        self.assertEqual(b"mute", rfid_data.serialize("mute"))
        self.assertEqual(b"up", rfid_data.serialize("up"))
        self.assertEqual(b"down", rfid_data.serialize("down"))
        self.assertEqual(b"reset", rfid_data.serialize("reset"))

    def test_serialize_set_action(self):
        self.assertEqual(b"set:210", rfid_data.serialize("set", "210"))
        self.assertEqual(b"set:0", rfid_data.serialize("set", "-1"))
        self.assertEqual(b"set:255", rfid_data.serialize("set", "300"))
        self.assertEqual(b"set:255", rfid_data.serialize("set", "bad"))

    def test_unserialize_set_action(self):
        self.assertEqual("set:210", rfid_data.unserialize(b"set:210"))
        self.assertEqual("set:255", rfid_data.unserialize("set:300"))
        self.assertEqual("reset", rfid_data.unserialize("set"))
        self.assertEqual("reset", rfid_data.unserialize("set:bad"))

    def test_set_action_helpers(self):
        self.assertTrue(rfid_data.is_set_action("set:210"))
        self.assertFalse(rfid_data.is_set_action("reset"))
        self.assertEqual(210, rfid_data.set_action_value("set:210"))
        self.assertEqual(255, rfid_data.set_action_value("reset"))
