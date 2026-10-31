"""Unit tests for voice text normalization for Pocket TTS Indonesian."""

import unittest
from maverick.voice.text_normalization import (
    number_to_indonesian_words,
    normalize_numbers,
    normalize_voice_text,
)


class TestTextNormalization(unittest.TestCase):
    def test_number_to_indonesian_words(self):
        self.assertEqual(number_to_indonesian_words(0), "nol")
        self.assertEqual(number_to_indonesian_words(5), "lima")
        self.assertEqual(number_to_indonesian_words(10), "sepuluh")
        self.assertEqual(number_to_indonesian_words(11), "sebelas")
        self.assertEqual(number_to_indonesian_words(17), "tujuh belas")
        self.assertEqual(number_to_indonesian_words(20), "dua puluh")
        self.assertEqual(number_to_indonesian_words(42), "empat puluh dua")
        self.assertEqual(number_to_indonesian_words(100), "seratus")
        self.assertEqual(number_to_indonesian_words(105), "seratus lima")
        self.assertEqual(number_to_indonesian_words(250), "dua ratus lima puluh")
        self.assertEqual(number_to_indonesian_words(1000), "seribu")
        self.assertEqual(number_to_indonesian_words(2026), "dua ribu dua puluh enam")
        self.assertEqual(number_to_indonesian_words(1_500_000), "satu juta lima ratus ribu")

    def test_normalize_numbers(self):
        self.assertEqual(normalize_numbers("Tersisa 15 menit"), "Tersisa lima belas menit")
        self.assertIn("sembilan puluh lima persen", normalize_numbers("Baterai 95%"))
        self.assertIn("tiga koma lima", normalize_numbers("Versi 3.5 rilis"))

    def test_normalize_voice_text_oov_and_symbols(self):
        # Exclamation marks should be replaced with periods
        text = "Halo MAVEN! Sistem siap!"
        norm = normalize_voice_text(text)
        self.assertNotIn("!", norm)
        self.assertIn("meiven", norm.lower())

        # Hyphens should be replaced with spaces
        text2 = "anak-anak bermain"
        self.assertEqual(normalize_voice_text(text2), "anak anak bermain.")

    def test_normalize_voice_text_technical_terms(self):
        text = "CPU usage 85%, RAM tersisa 4 GB. Endpoint API HTTP 200 OK."
        norm = normalize_voice_text(text)
        self.assertIn("C P U", norm)
        self.assertIn("R A M", norm)
        self.assertIn("A P I", norm)
        self.assertIn("H T T P", norm)
        self.assertIn("delapan puluh lima persen", norm)
        self.assertNotIn("%", norm)
        self.assertNotIn("85", norm)

    def test_normalize_voice_text_markdown_stripping(self):
        text = "Hasil **berhasil**, silakan cek `config.yaml` dan [link](http://local)."
        norm = normalize_voice_text(text)
        self.assertNotIn("**", norm)
        self.assertNotIn("`", norm)
        self.assertIn("config.yaml", norm)
        self.assertIn("link", norm)


if __name__ == "__main__":
    unittest.main()

