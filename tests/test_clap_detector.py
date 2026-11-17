"""Unit tests for DualClapDetector acoustic pattern recognition."""

import time
import unittest
import numpy as np

from maverick.voice.config import VoiceConfig
from maverick.voice.clap import DualClapDetector


def generate_clap_frame(peak_amplitude: float = 0.85, samples_count: int = 512) -> bytes:
    """Generate a realistic impulsive clap waveform with sharp attack and rapid decay."""
    samples = np.zeros(samples_count, dtype=np.float32)
    # Spike in first 10-20 samples
    decay = np.exp(-np.linspace(0, 8, samples_count - 10))
    samples[10:] = peak_amplitude * decay * (1.0 - 2.0 * np.random.rand(samples_count - 10))
    # Convert to 16-bit signed PCM
    pcm_int16 = (samples * 32767).astype(np.int16)
    return pcm_int16.tobytes()


def generate_ambient_frame(level: float = 0.05, samples_count: int = 512) -> bytes:
    """Generate steady ambient noise or speech with low crest factor."""
    samples = (np.random.rand(samples_count).astype(np.float32) - 0.5) * (2.0 * level)
    return (samples * 32767).astype(np.int16).tobytes()


class TestClapDetector(unittest.TestCase):
    """Test suite for local dual-clap pattern detector."""

    def setUp(self):
        self.config = VoiceConfig(
            enable_clap_detection=True,
            clap_min_interval_sec=0.10,
            clap_max_interval_sec=0.60,
            clap_cooldown_sec=0.50,
        )
        self.detector = DualClapDetector(self.config)

    def test_ambient_noise_and_silence_rejection(self):
        """Verify steady ambient hum, silence, and low energy never trigger clap detector."""
        silence = b"\x00" * 1024
        for _ in range(10):
            self.assertFalse(self.detector.process_frame(silence))

        ambient = generate_ambient_frame(0.08)
        for _ in range(10):
            self.assertFalse(self.detector.process_frame(ambient))

    def test_single_clap_timeout_rejection(self):
        """A single clap without a follow-up clap must NOT trigger."""
        clap = generate_clap_frame(0.85)
        # First clap
        res1 = self.detector.process_frame(clap)
        self.assertFalse(res1)
        self.assertGreater(self.detector._first_clap_time, 0.0)

        # Ambient silence for 0.7s (exceeds max_interval)
        silence = b"\x00" * 1024
        time.sleep(0.65)
        res2 = self.detector.process_frame(silence)
        self.assertFalse(res2)
        # First clap should have timed out
        self.assertEqual(self.detector._first_clap_time, 0.0)

    def test_valid_dual_clap_trigger(self):
        """Two claps within the cadence window (100ms - 600ms) with decay must trigger."""
        clap1 = generate_clap_frame(0.85)
        decay_silence = b"\x00" * 1024
        clap2 = generate_clap_frame(0.80)

        # Clap 1
        self.assertFalse(self.detector.process_frame(clap1))
        self.assertGreater(self.detector._first_clap_time, 0.0)

        # Inter-clap silence and wait for min_interval
        self.detector.process_frame(decay_silence)
        time.sleep(0.18)
        self.detector.process_frame(decay_silence)

        # Clap 2
        triggered = self.detector.process_frame(clap2)
        self.assertTrue(triggered, "Dual-clap should trigger on valid second clap")

    def test_cooldown_debounce_protection(self):
        """A third clap immediately following a successful dual-clap must be debounced."""
        clap = generate_clap_frame(0.85)
        decay_silence = b"\x00" * 1024

        # Execute dual clap
        self.detector.process_frame(clap)
        self.detector.process_frame(decay_silence)
        time.sleep(0.18)
        self.detector.process_frame(decay_silence)
        self.assertTrue(self.detector.process_frame(clap))

        # Immediate follow-up clap within cooldown (0.5s) must be blocked
        self.assertFalse(self.detector.process_frame(clap))

    def test_enable_disable_toggle(self):
        """Disabled detector must ignore claps completely."""
        self.detector.disable()
        self.assertFalse(self.detector.is_enabled())

        clap = generate_clap_frame(0.95)
        self.assertFalse(self.detector.process_frame(clap))
        self.assertEqual(self.detector._first_clap_time, 0.0)

        self.detector.enable()
        self.assertTrue(self.detector.is_enabled())
        self.detector.process_frame(clap)
        self.assertGreater(self.detector._first_clap_time, 0.0)

    def test_single_and_dual_clap_event_discrimination(self):
        """Verify process_event returns 'single' on timeout and 'dual' on two claps."""
        from maverick.voice.clap import ClapResult

        # 1. Single Clap: first clap, then silence past max_interval
        clap = generate_clap_frame(0.85)
        decay_silence = b"\x00" * 1024

        ev1 = self.detector.process_event(clap)
        self.assertEqual(ev1, ClapResult.NONE)

        # Allow decay
        self.detector.process_event(decay_silence)
        time.sleep(0.65)  # exceeds max_interval (0.60)
        ev2 = self.detector.process_event(decay_silence)
        self.assertEqual(ev2, ClapResult.SINGLE, "Single clap must emit SINGLE event after timeout")

        # Wait past cooldown
        time.sleep(0.55)

        # 2. Dual Clap: first clap, decay, second clap
        ev3 = self.detector.process_event(clap)
        self.assertEqual(ev3, ClapResult.NONE)

        self.detector.process_event(decay_silence)
        time.sleep(0.18)
        self.detector.process_event(decay_silence)

        ev4 = self.detector.process_event(clap)
        self.assertEqual(ev4, ClapResult.DUAL, "Dual clap must emit DUAL event upon second clap")


if __name__ == "__main__":
    unittest.main()

