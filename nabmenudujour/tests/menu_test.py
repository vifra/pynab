import datetime
import unittest

from nabmenudujour.menu import MenuError, meal_for_date, tts_audio_urls


class MenuDuJourTest(unittest.TestCase):
    def test_reads_date_keyed_menu(self):
        meal = meal_for_date(
            {"2026-05-01": "Poulet frites"},
            datetime.date(2026, 5, 1),
        )

        self.assertEqual(meal["text"], "Poulet frites")
        self.assertEqual(meal["audio_url"], "")

    def test_reads_menu_collection(self):
        meal = meal_for_date(
            {
                "menus": [
                    {"date": "2026-04-30", "repas": "Riz"},
                    {
                        "date": "2026-05-01",
                        "menu": "Lasagnes",
                        "audio_url": "https://example.com/menu.mp3",
                    },
                ]
            },
            datetime.date(2026, 5, 1),
        )

        self.assertEqual(meal["text"], "Lasagnes")
        self.assertEqual(meal["audio_url"], "https://example.com/menu.mp3")

    def test_reads_google_script_menu(self):
        meal = meal_for_date(
            {
                "titre": "Menu du Jour",
                "dateLongue": "Vendredi 1 Mai 2026",
                "dateTexte": "01/05/2026",
                "midi": "Pizza",
                "soir": "Poisson pane\nLegumes couscous\n",
                "midiIntrouvable": False,
                "soirIntrouvable": False,
                "labels": {"midi": "Midi", "soir": "Soir"},
            },
            datetime.date(2026, 5, 1),
        )

        self.assertEqual(
            meal["text"],
            "Vendredi 1 Mai 2026. Midi: Pizza. Soir: Poisson pane, "
            "Legumes couscous",
        )

    def test_raises_when_no_menu_matches_day(self):
        with self.assertRaises(MenuError):
            meal_for_date([], datetime.date(2026, 5, 1))

    def test_builds_tts_urls(self):
        urls = tts_audio_urls("Midi: Pizza")

        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].startswith("https://translate.google.com/"))
