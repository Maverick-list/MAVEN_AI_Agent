"""Maverick DevOS - Voice Interaction User Interface."""

import os
import select
import sys
import termios
import time
import tty
from typing import Optional

from maverick.voice.audio import calculate_rms
from maverick.voice.config import VoiceConfig
from maverick.voice.controller import VoiceController
from maverick.voice.session import VoiceSession, VoiceState


class VoiceUI:
    """
    Polished, minimal terminal voice interface for Ubuntu GNOME Wayland.
    Displays real-time state, live RMS energy activity, and transcripts.
    """

    STATE_COLORS = {
        VoiceState.IDLE: "\033[90m",  # Dark Gray
        VoiceState.WAKE_WORD_DETECTED: "\033[93;1m",  # Bold Yellow
        VoiceState.LISTENING: "\033[96;1m",  # Bold Cyan
        VoiceState.PROCESSING: "\033[95;1m",  # Bold Magenta
        VoiceState.SPEAKING: "\033[92;1m",  # Bold Green
        VoiceState.INTERRUPTED: "\033[91;1m",  # Bold Red
        VoiceState.ERROR: "\033[31;1m",  # Red
    }
    RESET = "\033[0m"

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        controller: Optional[VoiceController] = None,
    ):
        self.config = config or VoiceConfig()
        self.controller = controller or VoiceController(self.config)
        self.session = self.controller.session
        self._running = False
        self._last_state: Optional[VoiceState] = None
        self._last_transcript = ""
        self._last_response = ""

    def render_meter(self, rms: float, width: int = 20) -> str:
        """Render a genuine RMS audio energy meter bar without fake waveforms."""
        filled = int(min(1.0, max(0.0, rms * 5.0)) * width)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(min(100, rms * 500))
        return f"[{bar}] {pct:>3}%"

    def render_header(self) -> None:
        """Render the status header."""
        state = self.session.state
        color = self.STATE_COLORS.get(state, self.RESET)
        state_label = state.value.upper()

        if self.session.is_muted:
            state_label = "MUTED"
            color = "\033[33m"

        sys.stdout.write("\033[H\033[J")  # Clear screen and move to top
        sys.stdout.write("=" * 60 + "\n")
        sys.stdout.write("  ⚡ MAVEN JARVIS — VOICE INTERACTION LAYER (Wayland)\n")
        sys.stdout.write("=" * 60 + "\n\n")
        sys.stdout.write(f"  Status: {color}● {state_label}{self.RESET}\n")
        sys.stdout.write(f"  Device: {self.config.device_input}\n")
        sys.stdout.write(f"  Model:  {self.config.model_id}\n\n")

        if self._last_transcript:
            sys.stdout.write(f"  🎙️ You:   \"{self._last_transcript}\"\n")
        if self._last_response:
            sys.stdout.write(f"  🔊 Maven: \"{self._last_response}\"\n\n")

        sys.stdout.write("-" * 60 + "\n")
        sys.stdout.write("  [Space/Enter] Push-to-Talk | [m] Mute | [s] Stop | [q] Quit\n")
        sys.stdout.write("-" * 60 + "\n")
        sys.stdout.flush()

    def run(self) -> None:
        """Run the interactive voice loop."""
        if not sys.stdin.isatty():
            return

        self._running = True
        self.session.audio.start()
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setcbreak(sys.stdin.fileno())
            self.render_header()

            while self._running:
                # 1. Non-blocking key check
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "\x03"):  # q or Ctrl+C
                        break
                    elif ch in (" ", "\n"):
                        self.session.trigger_wake_word()
                        self.render_header()
                    elif ch == "m":
                        self.session.set_muted(not self.session.is_muted)
                        self.render_header()
                    elif ch == "s":
                        self.session.interrupt()
                        self.render_header()

                # 2. Step session
                utterance = self.session.step()

                # 3. Re-render if state changed
                current_state = self.session.state
                if current_state != self._last_state:
                    self._last_state = current_state
                    self.render_header()

                # 4. If listening, print dynamic RMS meter
                if current_state == VoiceState.LISTENING and not self.session.is_muted:
                    chunk = bytes(self.session._audio_buffer[-1024:]) if self.session._audio_buffer else b""
                    rms = calculate_rms(chunk)
                    meter = self.render_meter(rms)
                    sys.stdout.write(f"\r  🎙️ Audio Level: {meter} ")
                    sys.stdout.flush()

                # 5. Process utterance if completed
                if utterance:
                    self.render_header()
                    transcript = self.controller.stt.transcribe(utterance)
                    if not transcript:
                        self._last_transcript = "[No intelligible speech detected]"
                        self._last_response = ""
                        self.render_header()
                        self.session.reset()
                        continue

                    self._last_transcript = transcript
                    res = self.controller.handle_voice_command(transcript)
                    response_text = res.get("response", "")
                    self._last_response = response_text
                    self.render_header()

                    if response_text:
                        self.session.speak(response_text, wait=True)
                        self.render_header()

        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            self.session.audio.stop()
            self.session.reset()
            sys.stdout.write("\n\033[92m✔ Voice session safely terminated.\033[0m\n")
            sys.stdout.flush()
