"""
Maverick DevOS - Voice Text Normalization for Local Neural TTS (English & Indonesian).

Handles:
1. Primary English text normalization for Kyutai Pocket-TTS English 6L (numbers, decimals,
   percentages, Linux file paths, technical acronyms, units, markdown stripping, OOV handling).
2. Secondary Indonesian text normalization for Pocket-TTS Indonesian 6L when explicitly requested.
"""

import re
from typing import Dict, List, Optional

# ==============================================================================
# 1. ENGLISH TEXT NORMALIZATION (PRIMARY DEFAULT)
# ==============================================================================

_EN_ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_EN_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
]


def number_to_english_words(n: int) -> str:
    """Convert an integer into natural spoken English words."""
    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + number_to_english_words(abs(n))
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        return _EN_TENS[tens] + (" " + _EN_ONES[rem] if rem else "")
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        return _EN_ONES[hundreds] + " hundred" + (" " + number_to_english_words(rem) if rem else "")
    if n < 1_000_000:
        thousands, rem = divmod(n, 1000)
        return number_to_english_words(thousands) + " thousand" + (" " + number_to_english_words(rem) if rem else "")
    if n < 1_000_000_000:
        millions, rem = divmod(n, 1_000_000)
        return number_to_english_words(millions) + " million" + (" " + number_to_english_words(rem) if rem else "")
    if n < 1_000_000_000_000:
        billions, rem = divmod(n, 1_000_000_000)
        return number_to_english_words(billions) + " billion" + (" " + number_to_english_words(rem) if rem else "")
    return " ".join(number_to_english_words(int(d)) for d in str(n))


ENGLISH_TECH_TERM_MAP: Dict[str, str] = {
    "API": "A P I",
    "APIs": "A P I s",
    "CPU": "C P U",
    "GPU": "G P U",
    "RAM": "R A M",
    "TTS": "T T S",
    "STT": "S T T",
    "NLU": "N L U",
    "VAD": "V A D",
    "DAG": "D A G",
    "AST": "A S T",
    "SSE": "S S E",
    "JSON": "J S O N",
    "SQL": "S Q L",
    "SQLite": "S Q Lite",
    "WAL": "W A L",
    "UI": "U I",
    "UX": "U X",
    "GUI": "G U I",
    "CLI": "C L I",
    "PID": "P I D",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "URL": "U R L",
    "URLs": "U R L s",
    "SSH": "S S H",
    "SSRF": "S S R F",
    "DNS": "D N S",
    "TLS": "T L S",
    "WAV": "W A V",
    "MP3": "M P three",
    "PDF": "P D F",
    "DOCX": "D O C X",
    "ONNX": "O N N X",
    "AT-SPI": "A T S P I",
    "ATSPI": "A T S P I",
    "OCR": "O C R",
    "LLM": "L L M",
    "AI": "A I",
    "OS": "O S",
    "FPS": "frames per second",
    "GB": "gigabytes",
    "MB": "megabytes",
    "KB": "kilobytes",
    "kHz": "kilohertz",
    "Hz": "hertz",
    "ms": "milliseconds",
}

_EXT_MAP: Dict[str, str] = {
    "py": "p y",
    "js": "j s",
    "ts": "t s",
    "md": "m d",
    "json": "j s o n",
    "yaml": "yaml",
    "yml": "yaml",
    "sh": "s h",
    "txt": "t x t",
    "pdf": "p d f",
    "docx": "d o c x",
    "wav": "w a v",
    "onnx": "o n n x",
    "db": "d b",
    "sqlite": "s q lite",
}


def _expand_file_path_en(match: re.Match) -> str:
    raw = match.group(0)
    prefix = ""
    if raw.startswith("~/"):
        prefix = "home "
        raw = raw[2:]
    elif raw.startswith("/"):
        prefix = "slash "
        raw = raw[1:]

    segments = [seg for seg in raw.split("/") if seg]
    spoken_segments: List[str] = []
    for seg in segments:
        if "." in seg and not seg.startswith("."):
            stem, ext = seg.rsplit(".", 1)
            stem_clean = stem.replace("_", " ").replace("-", " ")
            ext_spoken = _EXT_MAP.get(ext.lower(), ext)
            spoken_segments.append(f"{stem_clean} dot {ext_spoken}")
        else:
            spoken_segments.append(seg.replace("_", " ").replace("-", " "))
    return prefix + " slash ".join(spoken_segments)


def normalize_english_numbers(text: str) -> str:
    """Expand IP addresses, ports, percentages, decimals, and integers into spoken English."""
    # 1. IPv4 + optional port: 127.0.0.1:8765
    def _replace_ip(match: re.Match) -> str:
        octets = [match.group(i) for i in range(1, 5)]
        spoken_ip = " dot ".join(" ".join(number_to_english_words(int(d)) for d in o) if len(o) > 1 and o != "127" else number_to_english_words(int(o)) for o in octets)
        if match.group(5):
            port_digits = " ".join(number_to_english_words(int(d)) for d in match.group(5))
            return f"{spoken_ip} port {port_digits}"
        return spoken_ip

    text = re.sub(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?::(\d{2,5}))?\b", _replace_ip, text)

    # 2. Percentages: 85% or 85.4%
    def _replace_pct(match: re.Match) -> str:
        val = match.group(1)
        if "." in val:
            a, b = val.split(".", 1)
            dec = " ".join(number_to_english_words(int(d)) for d in b)
            return f"{number_to_english_words(int(a))} point {dec} percent"
        return f"{number_to_english_words(int(val))} percent"

    text = re.sub(r"(\d+(?:\.\d+)?)\s*%", _replace_pct, text)

    # 3. Decimals: 3.14 -> three point one four
    def _replace_dec(match: re.Match) -> str:
        int_part = int(match.group(1))
        dec_str = match.group(2)
        dec_words = " ".join(number_to_english_words(int(d)) for d in dec_str)
        return f"{number_to_english_words(int_part)} point {dec_words}"

    text = re.sub(r"\b(\d+)\.(\d+)\b", _replace_dec, text)

    # 4. Dollar currency: $42 -> forty two dollars
    def _replace_usd(match: re.Match) -> str:
        num = int(match.group(1).replace(",", ""))
        unit = "dollar" if num == 1 else "dollars"
        return f"{number_to_english_words(num)} {unit}"

    text = re.sub(r"\$(\d[\d,]*)", _replace_usd, text)

    # 5. Integers (including comma-separated thousands like 16,000)
    def _replace_int(match: re.Match) -> str:
        raw_n = match.group(0).replace(",", "")
        return number_to_english_words(int(raw_n))

    text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b|\b\d+\b", _replace_int, text)
    return text


def normalize_english_voice_text(text: str) -> str:
    """
    Complete English text normalization pipeline for Kyutai Pocket-TTS English.
    """
    if not text or not text.strip():
        return ""

    s = text.strip()

    # 1. Strip Markdown formatting
    s = re.sub(r"```.*?```", " ", s, flags=re.DOTALL)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
    s = re.sub(r"https?://([^\s/]+)(/\S*)?", r"\1", s)
    s = re.sub(r"[*_~>#]", " ", s)

    # 2. Expand AT-SPI hyphenated form before general hyphen handling
    s = re.sub(r"\bAT-SPI\b", "A T S P I", s, flags=re.IGNORECASE)

    # 3. Expand Unix file paths (~/foo/bar.py or /home/user/file.txt)
    s = re.sub(r"(?:~|/)[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+", _expand_file_path_en, s)
    # Standalone filenames like config.yaml or server.py
    def _expand_filename(m: re.Match) -> str:
        stem, ext = m.group(1), m.group(2)
        if ext.lower() in _EXT_MAP:
            return f"{stem.replace('_', ' ')} dot {_EXT_MAP[ext.lower()]}"
        return m.group(0)

    s = re.sub(r"\b([A-Za-z_][A-Za-z0-9_-]*)\.([A-Za-z0-9]{2,6})\b", _expand_filename, s)

    # 4. Pocket-TTS OOV & symbol normalization
    s = s.replace("!", ".")
    s = s.replace("—", ", ").replace("–", ", ")
    s = s.replace("&", " and ")
    s = s.replace("+", " plus ")
    s = s.replace("=", " equals ")
    s = s.replace("@", " at ")
    s = s.replace("/", " slash ")
    s = s.replace("_", " ")
    s = s.replace("-", " ")
    s = re.sub(r"[\"'`\^~(){}\[\]\\|]", " ", s)

    # 5. Expand numbers (after unit separation like 24kHz -> 24 kHz)
    s = re.sub(r"(\d+)(kHz|Hz|GB|MB|KB|ms|s)\b", r"\1 \2", s)
    s = normalize_english_numbers(s)

    # 6. Word-level acronym & unit expansion
    words = s.split()
    out_words: List[str] = []
    for w in words:
        clean_w = w.strip(".,;:?!")
        punct = w[len(clean_w):] if clean_w and w.endswith(tuple(".,;:?!")) else ""
        if clean_w in ENGLISH_TECH_TERM_MAP:
            out_words.append(f"{ENGLISH_TECH_TERM_MAP[clean_w]}{punct}")
        elif clean_w.upper() in ENGLISH_TECH_TERM_MAP and len(clean_w) >= 2 and clean_w.isupper():
            out_words.append(f"{ENGLISH_TECH_TERM_MAP[clean_w.upper()]}{punct}")
        else:
            out_words.append(w)

    result = re.sub(r"\s+", " ", " ".join(out_words)).strip()
    if result and not result.endswith((".", "?", ";", ":")):
        result += "."
    return result


# ==============================================================================
# 2. INDONESIAN TEXT NORMALIZATION (SECONDARY / EXPLICIT OPT-IN)
# ==============================================================================

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
        digits = [number_to_indonesian_words(int(d)) for d in str(n)]
        return " ".join(digits)


TECH_TERM_MAP: Dict[str, str] = {
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
    text = re.sub(r'(\d+)\s*%', r'\1 persen', text)

    def _replace_decimal(match: re.Match) -> str:
        int_part = int(match.group(1))
        dec_str = match.group(2)
        int_words = number_to_indonesian_words(int_part)
        dec_words = " ".join(number_to_indonesian_words(int(d)) for d in dec_str)
        return f"{int_words} koma {dec_words}"

    text = re.sub(r'(\d+)[.,](\d+)', _replace_decimal, text)

    def _replace_currency(match: re.Match) -> str:
        num = match.group(1).replace(".", "").replace(",", "")
        try:
            return f"{number_to_indonesian_words(int(num))} rupiah"
        except ValueError:
            return match.group(0)

    text = re.sub(r'Rp\s*([\d.,]+)', _replace_currency, text, flags=re.IGNORECASE)

    def _replace_int(match: re.Match) -> str:
        val = int(match.group(0))
        return number_to_indonesian_words(val)

    text = re.sub(r'\b\d+\b', _replace_int, text)
    return text


def normalize_voice_text(text: str, language: Optional[str] = None) -> str:
    """
    Normalize text for Pocket TTS synthesis.
    - If `language == "en"`, applies English normalization (`normalize_english_voice_text`).
    - Otherwise (default `"id"` for backward compatibility with Indonesian normalizer calls),
      applies Indonesian normalization.
    """
    if language and language.lower().startswith("en"):
        return normalize_english_voice_text(text)

    if not text or not text.strip():
        return ""

    s = text.strip()

    # 1. Strip Markdown formatting
    s = re.sub(r'```.*?```', '', s, flags=re.DOTALL)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    s = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)
    s = re.sub(r'[*_~>#]', ' ', s)

    # 2. Replace Out-Of-Vocabulary characters for Pocket TTS
    s = s.replace("!", ".")
    s = s.replace("-", " ")
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

        if clean_w in TECH_TERM_MAP:
            replacement = TECH_TERM_MAP[clean_w]
            normalized_words.append(f"{prefix_punct}{replacement}{punct}")
        elif lower_w in TECH_TERM_MAP:
            replacement = TECH_TERM_MAP[lower_w]
            normalized_words.append(f"{prefix_punct}{replacement}{punct}")
        else:
            normalized_words.append(w)

    result = " ".join(normalized_words)
    result = re.sub(r'\s+', ' ', result).strip()
    if result and not result.endswith((".", "?", ";", ":")):
        result += "."

    return result
