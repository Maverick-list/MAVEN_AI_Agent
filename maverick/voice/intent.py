"""Maverick DevOS - Bilingual Intent Normalizer & Local Intent Classifier."""

import re
from typing import Any, Dict, Optional, Tuple


class BilingualIntentClassifier:
    """
    Robust, deterministic bilingual intent normalization and classification layer
    supporting natural Indonesian and English desktop automation expressions.
    Operates offline with sub-millisecond execution time, eliminating unnecessary
    cloud round-trips for standard desktop controls while safely handing off
    unrecognized requests to conversational AI gateways.
    """

    # Application canonical ID mappings
    APP_TARGETS = {
        "code": [
            "vs code", "vscode", "visual studio code", "visual studio",
            "coding", "code editor", "text editor", "code",
        ],
        "google-chrome": [
            "google chrome", "chrome", "browser", "peramban",
            "web browser", "internet", "browsing",
        ],
        "firefox": [
            "firefox", "fire fox", "mozilla", "mozilla firefox", "peramban firefox",
        ],
        "nautilus": [
            "files", "nautilus", "file manager", "file explorer",
            "manajer berkas", "berkas", "folder", "dokumen",
        ],
        "spotify": [
            "spotify", "spotify client", "pemutar musik",
        ],
        "gnome-terminal": [
            "terminal", "gnome terminal", "command line", "konsol",
            "shell", "bash",
        ],
    }

    ID_WORDS = {
        "buka", "jalankan", "putar", "jeda", "hentikan", "sisa", "tersisa",
        "baterai", "ringkasan", "matikan", "aktifkan", "bisu", "senyapkan",
        "lagu", "musik", "laptopku", "tolong", "aku", "saya", "naikkan",
        "turunkan", "persen", "suara", "cek", "berikutnya", "sedang", "apa",
        "bagaimana", "keadaan", "peramban", "berkas", "tambah", "kurang",
        "diam", "berapa", "kopi", "malam", "pagi", "siang", "sore", "hari",
    }

    EN_WORDS = {
        "open", "launch", "start", "play", "pause", "stop", "resume", "next",
        "track", "song", "volume", "battery", "ram", "memory", "cpu",
        "summarize", "context", "desktop", "please", "can", "could", "want",
        "mute", "unmute", "increase", "decrease", "raise", "lower", "check",
        "how", "what", "is", "left", "available", "running", "applications",
        "apps", "files", "browser", "terminal", "pizza",
    }

    @classmethod
    def detect_language(cls, text: str) -> str:
        """Detect whether command text is primarily Indonesian ('id') or English ('en')."""
        words = set(re.findall(r"\w+", text.lower()))
        id_score = len(words.intersection(cls.ID_WORDS))
        en_score = len(words.intersection(cls.EN_WORDS))

        if id_score > en_score:
            return "id"
        elif en_score > id_score:
            return "en"
        # If tied, check for Indonesian function words / prefixes
        return "id" if any(w in cls.ID_WORDS for w in words) else "en"

    @classmethod
    def normalize_text(cls, raw_text: str) -> Tuple[str, str]:
        """
        Clean and normalize raw text:
        - Lowercase & strip punctuation
        - Remove leading wake words (Maven, Jarvis, etc.)
        - Remove common modal/polite conversational filler prefixes
        Returns (clean_text, language_code).
        """
        clean = raw_text.lower().strip()
        lang = cls.detect_language(clean)

        # 1. Strip leading wake word
        clean = re.sub(
            r"^(?:(?:hey|hei|halo|hai|ok|okay)\s+)?(?:maven|jarvis)[\s,:]*",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()

        # 2. Strip polite / modal prefixes
        prefix_pattern = (
            r"^(?:tolong|mohon|bisa|coba|aku\s+mau|saya\s+mau|mau|tolong\s+dong|"
            r"please|can\s+you|could\s+you|would\s+you|i\s+want\s+to|let's|let\s+us)\s+"
        )
        clean = re.sub(prefix_pattern, "", clean, flags=re.IGNORECASE).strip()

        # 3. Strip trailing punctuation
        clean = re.sub(r"[\.,\?!]+$", "", clean).strip()

        return clean, lang

    @classmethod
    def classify(cls, raw_text: str) -> Dict[str, Any]:
        """
        Classify utterance into a deterministic desktop intent.
        Returns a structured dictionary with:
        - intent: canonical action name
        - target: specific entity (app_id, volume level, etc.)
        - is_id: boolean flag indicating Indonesian context
        - confidence: 1.0 (exact), 0.8 (heuristic/fuzzy), or 0.0 (unhandled)
        - clean_text: normalized text payload
        """
        clean, lang = cls.normalize_text(raw_text)
        is_id = (lang == "id")

        # Check if utterance is purely a wake word greeting (e.g. "Hey Maven", "Maven", "Halo Maven")
        raw_lower = raw_text.lower().strip()
        wake_match = re.search(r"^\s*(?:(?:hey|hei|halo|hai|ok|okay)\s+)?(?:maven|jarvis)[\s\.,!\?]*$", raw_lower)
        if wake_match:
            is_id = any(w in raw_lower for w in ("halo", "hai", "hei"))
            return {
                "intent": "wake_acknowledgment",
                "target": None,
                "is_id": is_id,
                "confidence": 1.0,
                "clean_text": raw_lower,
            }

        if not clean:
            return {"intent": "empty", "target": None, "is_id": is_id, "confidence": 0.0, "clean_text": ""}

        # 1. Session Mute / Unmute / Stop (Checked first to avoid shadowing by volume/audio terms)
        if re.search(r"\b(matikan\s+suara|bisu|senyapkan\s+mikrofon|senyapkan|mute\s+mic|mute\s+microphone|mute)\b", clean):
            return {"intent": "mute", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(aktifkan\s+mikrofon|bunyikan\s+mikrofon|unmute\s+mic|unmute\s+microphone|unmute)\b", clean):
            return {"intent": "unmute", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if clean in ("stop", "cancel", "be quiet", "silence", "berhenti", "diam", "batalkan", "cukup", "diam maven", "stop talking", "berhenti bicara"):
            return {"intent": "interrupt", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        # 2. Spotify Volume Controls
        if re.search(r"\b(volume|suara|keras|pelan|louder|quieter)\b", clean):
            # Up
            if any(w in clean for w in ("up", "increase", "raise", "louder", "naik", "naikkan", "tambah", "perbesar", "lebih keras")):
                return {"intent": "spotify_volume", "target": "up", "is_id": is_id, "confidence": 1.0, "clean_text": clean}
            # Down
            if any(w in clean for w in ("down", "decrease", "lower", "quieter", "turun", "turunkan", "kurang", "kurangi", "perkecil", "pelan")):
                return {"intent": "spotify_volume", "target": "down", "is_id": is_id, "confidence": 1.0, "clean_text": clean}
            # Numeric Level: e.g. "volume 70", "volume-nya 70 persen", "set volume to -20"
            num_match = re.search(r"(-?\d{1,3})", clean)
            if num_match:
                level = max(0, min(100, int(num_match.group(1))))
                return {"intent": "spotify_volume", "target": level, "is_id": is_id, "confidence": 1.0, "clean_text": clean}
            # Query level
            if any(w in clean for w in ("berapa", "cek", "check", "status", "current", "what", "level")):
                return {"intent": "spotify_volume", "target": "query", "is_id": is_id, "confidence": 0.9, "clean_text": clean}

        # 3. Spotify Playback Controls
        if re.search(r"\b(play|resume|putar|mainkan|lanjutkan)\b.*\b(music|spotify|song|playback|musik|lagu)\b", clean) or clean in ("play", "resume", "putar", "mainkan", "putar musik", "mainkan lagu", "resume playback"):
            return {"intent": "spotify_play", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(pause|stop|jeda|hentikan|matikan)\b.*\b(music|spotify|playback|musik|lagu)\b", clean) or clean in ("pause", "jeda", "jeda musik", "hentikan musik", "pause music", "stop playback"):
            return {"intent": "spotify_pause", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(next|berikutnya|selanjutnya|ganti|skip)\b.*\b(track|song|lagu|trek)\b", clean) or clean in ("next", "next song", "next track", "berikutnya", "lagu berikutnya", "ganti lagu", "skip this song"):
            return {"intent": "spotify_next", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(what\s+is\s+playing|now\s+playing|what\s+song|current\s+song|currently\s+playing|lagu\s+apa|sedang\s+memutar|apa\s+yang\s+diputar|judul\s+lagu)\b", clean):
            return {"intent": "spotify_status", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        # 4. Application Launching
        is_launch_syntax = any(
            clean.startswith(p)
            for p in ("open ", "launch ", "start ", "buka ", "jalankan ", "mau ", "mulai ", "ayo ", "siapkan ")
        )
        for app_id, triggers in cls.APP_TARGETS.items():
            for t in triggers:
                # Match explicit app name in launch context
                if is_launch_syntax and t in clean:
                    return {"intent": "app_launch", "target": app_id, "is_id": is_id, "confidence": 1.0, "clean_text": clean}
                # Direct trigger without 'open'
                if clean == t or clean == f"buka {t}" or clean == f"open {t}":
                    return {"intent": "app_launch", "target": app_id, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        # 5. System Telemetry & Awareness
        if re.search(r"\b(ram|memori|memory)\b", clean):
            return {"intent": "system_ram", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(baterai|battery|daya\s+baterai|charging|mengisi\s+daya)\b", clean):
            return {"intent": "system_battery", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(cpu|processor|prosesor)\b", clean):
            return {"intent": "system_cpu", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(desktop\s+context|summarize\s+desktop|ringkasan\s+(?:konteks\s+)?desktop|kondisi\s+laptop\w*|keadaan\s+laptop\w*|ringkasan\s+sistem|status\s+desktop|happening\s+on\s+desktop)\b", clean):
            return {"intent": "context_summary", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        if re.search(r"\b(running\s+(?:authorized\s+)?apps|running\s+(?:authorized\s+)?applications|active\s+applications|apps?\s+(?:are\s+)?running|applications\s+(?:are\s+)?running|aplikasi\s+berjalan|aplikasi\s+aktif|aplikasi\s+.*(?:sedang\s+)?berjalan)\b", clean):
            return {"intent": "apps_running", "target": None, "is_id": is_id, "confidence": 1.0, "clean_text": clean}

        # 6. Unhandled / Conversational Fallback
        return {"intent": "unhandled", "target": None, "is_id": is_id, "confidence": 0.0, "clean_text": clean}
