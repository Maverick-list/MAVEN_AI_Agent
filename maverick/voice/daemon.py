"""Maverick DevOS - Headless Background Voice Assistant Daemon."""

import os
import signal
import sys
import time
from typing import Optional

from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.session import VoiceSession, VoiceState


class VoiceDaemon:
    """
    Continuous headless voice assistant service.
    Runs background audio capture, wake-word detection, speech-to-text,
    bilingual intent dispatch, and verbal TTS feedback without requiring a TTY.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        controller: Optional[VoiceController] = None,
    ):
        self.config = config or VoiceConfig()
        self.controller = controller or VoiceController(self.config)
        self.session = self.controller.session
        self._running = False

    def stop(self, *args) -> None:
        """Signal daemon to gracefully shut down."""
        self._running = False

    def run(self) -> None:
        """Execute the continuous background voice interaction loop."""
        self._running = True
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)

        self.session.audio.start()

        # Log startup
        sys.stdout.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Maven Voice Daemon initialized and listening on {self.config.device_input}...\n")
        sys.stdout.flush()

        try:
            while self._running:
                utterance = self.session.step()

                if utterance:
                    transcript = self.controller.stt.transcribe(utterance)
                    if not transcript:
                        self.session.reset()
                        continue

                    sys.stdout.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Heard: \"{transcript}\"\n")
                    sys.stdout.flush()

                    res = self.controller.handle_voice_command(transcript)
                    response_text = res.get("response", "")

                    if response_text:
                        sys.stdout.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Speaking: \"{response_text}\"\n")
                        sys.stdout.flush()
                        self.session.speak(response_text, wait=True)

                    self.session.reset()

                # Sleep small delta to yield CPU during IDLE
                time.sleep(0.01)

        except Exception as e:
            sys.stderr.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Daemon encountered error: {str(e)}\n")
            sys.stderr.flush()
        finally:
            self.session.audio.stop()
            self.session.reset()
            sys.stdout.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Maven Voice Daemon stopped.\n")
            sys.stdout.flush()


def run_daemon() -> None:
    """Entry point for maverick.cli voice daemon."""
    daemon = VoiceDaemon()
    daemon.run()


if __name__ == "__main__":
    run_daemon()
