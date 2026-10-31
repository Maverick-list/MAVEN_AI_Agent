"""
Maverick DevOS - Voice Text Normalization for Pocket TTS Indonesian.

Handles:
1. Number to Indonesian words expansion (integers, decimals, percentages, dates, times).
2. Out-of-vocabulary (OOV) character replacement (e.g. '!' -> '.', '-' -> ' ').
3. Technical terminology and acronym spelling for natural Indonesian neural pronunciation.
4. Punctuation and whitespace sanitization.
"""

import re
from typing import Dict, List, Optional

# Indonesian single numbers mapping
_UNITS = [
    "", "satu", "dua", "tiga", "empat", "lima",
    "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas"
]


def number_to_indonesian_words(n: int) -> str:
    """Convert an integer into natural spoken Indonesian words."""
    if n == 0:
        return "nol"
    if n < 0:
        return "minus " + number_to_indonesian_words(abs(n))

    if n < 12:
        return _UNITS[n]
    elif n < 20:
        return _UNITS[n - 10] + " belas"
    elif n < 100:
        tens = n // 10
        rem = n % 10
        return _UNITS[tens] + " puluh" + (" " + _UNITS[rem] if rem > 0 else "")
    elif n < 200:
        rem = n - 100
        return "seratus" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    elif n < 1000:
        hundreds = n // 100
        rem = n % 100
        return _UNITS[hundreds] + " ratus" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    elif n < 2000:
        rem = n - 1000
        return "seribu" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    elif n < 1_000_000:
        thousands = n // 1000
        rem = n % 1000
        return number_to_indonesian_words(thousands) + " ribu" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    elif n < 1_000_000_000:
        millions = n // 1_000_000
        rem = n % 1_000_000
        return number_to_indonesian_words(millions) + " juta" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    elif n < 1_000_000_000_000:
        billions = n // 1_000_000_000
        rem = n % 1_000_000_000
        return number_to_indonesian_words(billions) + " miliar" + (" " + number_to_indonesian_words(rem) if rem > 0 else "")
    else:
        # Fallback to digit-by-digit for huge numbers
        digits = [number_to_indonesian_words(int(d)) for d in str(n)]
        return " ".join(digits)


# Technical terms and phonetic pronunciations for Indonesian neural TTS
TECH_TERM_MAP: Dict[str, str] = {
    # Acronyms
    "API": "A P I",
    "CPU": "C P U",
    "RAM": "R A M",
    "TTS": "T T S",
    "STT": "S T T",
    "NLU": "N L U",
    "DAG": "D A G",
    "JSON": "jeison",
    "UI": "U I",
    "UX": "U X",
    "PID": "P I D",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "URL": "U R L",
    "CLI": "C L I",
    "OS": "O S",
    "SSH": "S S H",
    "WAV": "W A V",
    "MP3": "M P 3",
    "AI": "A I",
    "LLM": "L L M",
    "GPU": "G P U",
    "WER": "W E R",
    "UTMOS": "U T M O S",
    "BPE": "B P E",
    "ADC": "A D C",
    "GCP": "G C P",

    # Pronunciation adaptations for English technical terms
    "python": "paiton",
    "pytorch": "paitorc",
    "torch": "torc",
    "cache": "kesh",
    "cached": "dikesy",
    "caching": "kesying",
    "offline": "oflein",
    "online": "onlein",
    "download": "donlod",
    "downloaded": "terdonlod",
    "downloading": "mendownload",
    "dashboard": "desbor",
    "daemon": "demon",
    "code": "kod",
    "voice": "vois",
    "fallback": "folbek",
    "real-time": "ril taim",
    "realtime": "ril taim",
    "timeout": "taim aut",
    "debug": "dibag",
    "debugging": "dibaging",
    "buffer": "bafer",
    "buffered": "dibafer",
    "buffering": "bafering",
    "thread": "tred",
    "threads": "tred",
    "benchmark": "bencmark",
    "benchmarking": "bencmarking",
    "server": "server",
    "client": "klaien",
    "session": "sesi",
    "queue": "antrean",
    "pipeline": "paiplain",
    "token": "token",
    "tokenizer": "tokenaiser",
    "model": "model",
    "neural": "neural",
    "latency": "latensi",
    "jarvis": "jarvis",
    "maven": "meiven",
    "linux": "linuks",
    "ubuntu": "ubuntu",
    "gnome": "gnom",
    "wayland": "weiland",
    "elevenlabs": "eleven lebz",
    "whisper": "wisper",
}


def normalize_numbers(text: str) -> str:
    """Expand digits, decimal numbers, and percentages to Indonesian words."""
    # 1. Percentages: 95% -> 95 persen
    text = re.sub(r'(\d+)\s*%', r'\1 persen', text)

    # 2. Decimal numbers: 3.5 or 3,5 -> 3 koma 5
    def _replace_decimal(match: re.Match) -> str:
        int_part = int(match.group(1))
        dec_str = match.group(2)
        int_words = number_to_indonesian_words(int_part)
        dec_words = " ".join(number_to_indonesian_words(int(d)) for d in dec_str)
        return f"{int_words} koma {dec_words}"

    text = re.sub(r'(\d+)[.,](\d+)', _replace_decimal, text)

    # 3. Currency: Rp 50.000 or Rp50000 -> 50000 rupiah
    def _replace_currency(match: re.Match) -> str:
        num = match.group(1).replace(".", "").replace(",", "")
        try:
            return f"{number_to_indonesian_words(int(num))} rupiah"
        except ValueError:
            return match.group(0)

    text = re.sub(r'Rp\s*([\d.,]+)', _replace_currency, text, flags=re.IGNORECASE)

    # 4. Standard integers: 123 -> seratus dua puluh tiga
    def _replace_int(match: re.Match) -> str:
        val = int(match.group(0))
        return number_to_indonesian_words(val)

    text = re.sub(r'\b\d+\b', _replace_int, text)
    return text


def normalize_voice_text(text: str) -> str:
    """
    Complete text normalization pipeline for Pocket TTS Indonesian.
    1. Replaces out-of-vocabulary characters (!, -, @, #, $, etc.).
    2. Normalizes numbers, decimals, percentages, and currencies into Indonesian words.
    3. Normalizes technical terms and English loan words.
    4. Strips markdown syntax and extra whitespace.
    """
    if not text or not text.strip():
        return ""

    s = text.strip()

    # 1. Strip Markdown formatting
    s = re.sub(r'```.*?```', '', s, flags=re.DOTALL)  # code blocks
    s = re.sub(r'`([^`]+)`', r'\1', s)  # inline code
    s = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)  # links [text](url) -> text
    s = re.sub(r'[*_~>#]', ' ', s)  # markdown emphasis, headers, quotes

    # 2. Replace Out-Of-Vocabulary characters for Pocket TTS
    # Pocket TTS BPE tokenizer does not support exclamation mark '!'
    s = s.replace("!", ".")
    # Hyphens cause issues in BPE segmentation; convert to space
    s = s.replace("-", " ")
    # Replace slashes and symbols
    s = s.replace("/", " atau ")
    s = s.replace("&", " dan ")
    s = s.replace("+", " tambah ")
    s = s.replace("=", " sama dengan ")
    s = s.replace("@", " at ")

    # 3. Remove unsupported punctuation
    s = re.sub(r'[\'"`\^~(){}\[\]\\|]', ' ', s)

    # 4. Normalize numbers to Indonesian words
    s = normalize_numbers(s)

    # 5. Word-level technical term and acronym normalization
    words = s.split()
    normalized_words: List[str] = []
    for w in words:
        clean_w = w.strip(".,;:?!")
        lower_w = clean_w.lower()
        punct = w[len(clean_w):] if w.endswith(tuple(".,;:?!")) else ""
        prefix_punct = w[:len(w) - len(clean_w)] if w.startswith(tuple(".,;:?!")) else ""

        # Exact case match for uppercase acronyms (e.g. API, CPU, RAM)
        if clean_w in TECH_TERM_MAP:
            replacement = TECH_TERM_MAP[clean_w]
            normalized_words.append(f"{prefix_punct}{replacement}{punct}")
        elif lower_w in TECH_TERM_MAP:
            replacement = TECH_TERM_MAP[lower_w]
            normalized_words.append(f"{prefix_punct}{replacement}{punct}")
        else:
            normalized_words.append(w)

    result = " ".join(normalized_words)

    # 6. Normalize whitespace and trailing punctuation
    result = re.sub(r'\s+', ' ', result).strip()
    # Ensure it ends with a period if not ending with punctuation
    if result and not result.endswith((".", "?", ";", ":")):
        result += "."

    return result

