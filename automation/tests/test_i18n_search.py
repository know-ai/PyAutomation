import unittest

from automation.i18n_search import expand_search_term, get_translation_map


class TestI18nSearch(unittest.TestCase):
    SAMPLE_MAP = {
        "User logged in": "Usuario inició sesión",
        "User logged out": "Usuario cerró sesión",
        "Alarm acknowledged": "Alarma reconocida",
        "Alarms acknowledged": "Alarmas reconocidas",
    }

    def test_expand_spanish_partial_user(self):
        terms = expand_search_term("usuar", self.SAMPLE_MAP)
        self.assertIn("usuar", terms)
        self.assertIn("User logged in", terms)
        self.assertIn("User logged out", terms)

    def test_expand_spanish_partial_alarma(self):
        terms = expand_search_term("alarma", self.SAMPLE_MAP)
        self.assertIn("alarma", terms)
        self.assertIn("Alarm acknowledged", terms)
        self.assertIn("Alarms acknowledged", terms)

    def test_english_term_still_works(self):
        terms = expand_search_term("user", self.SAMPLE_MAP)
        self.assertEqual(terms, ["user"])

    def test_empty_term(self):
        self.assertEqual(expand_search_term("", self.SAMPLE_MAP), [])
        self.assertEqual(expand_search_term("   ", self.SAMPLE_MAP), [])

    def test_translation_map_loads(self):
        mapping = get_translation_map()
        self.assertIsInstance(mapping, dict)
        self.assertIn("User logged in", mapping)
        self.assertEqual(mapping["User logged in"], "Usuario inició sesión")


if __name__ == "__main__":
    unittest.main()
