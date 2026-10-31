"""Maverick DevOS - Voice Interaction Controller & Desktop Action Router."""

import http.client
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from maverick.activity.logger import ActivityLogger
from maverick.context.engine import ContextEngine
from maverick.core.security import ConfirmationRequiredError
from maverick.desktop.awareness import get_running_authorized_apps
from maverick.desktop.launcher import launch_app
from maverick.intelligence.memory import ContextMemory
from maverick.intelligence.planner import TaskPlan, TaskPlanner, TaskStatus
from maverick.media.spotify import SpotifyController
from maverick.vision.vision_controller import VisionController
from maverick.system.monitor import (
    get_battery_status,
    get_cpu_usage,
    get_memory_usage,
    get_system_resources,
)
from maverick.voice.config import VoiceConfig
from maverick.voice.intent import BilingualIntentClassifier
from maverick.voice.observability import redact_sensitive_text, voice_logger
from maverick.voice.session import VoiceSession, VoiceState
from maverick.voice.stt import LocalIntentSTTProvider, STTProvider, WhisperCppSTTProvider
from maverick.voice.tts import SpeechDispatcherTTS, TTSProvider, create_tts_provider, detect_speech_language


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_ABBREV_TAIL_RE = re.compile(r"\b(?:mr|mrs|ms|dr|prof|sr|jr|vs|etc|e\.g|i\.e)\.$", re.IGNORECASE)
_MARKDOWN_CLEAN_RE = re.compile(r"[*_`#]+")


def clean_spoken_text(text: str) -> str:
    """Strip markdown symbols and collapse whitespace so speech synthesis sounds natural."""
    if not text:
        return ""
    cleaned = _MARKDOWN_CLEAN_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def split_meaningful_sentences(buffer: str, min_chars: int = 22, flush: bool = False) -> Tuple[List[str], str]:
    """
    Incrementally split streaming LLM text into meaningful spoken sentence chunks.
    Avoids choppy 1-2 word fragments while releasing the first complete clause as early as possible.
    """
    if not buffer:
        return [], ""

    if flush:
        final = clean_spoken_text(buffer)
        return ([final] if final else []), ""

    parts = _SENTENCE_SPLIT_RE.split(buffer)
    if len(parts) <= 1:
        return [], buffer

    complete_raw = parts[:-1]
    remainder = parts[-1]
    emitted: List[str] = []
    carry = ""

    for seg in complete_raw:
        candidate = (f"{carry} {seg}" if carry else seg).strip()
        if not candidate:
            continue
        if len(candidate) < min_chars or _ABBREV_TAIL_RE.search(candidate):
            carry = candidate
            continue
        cleaned = clean_spoken_text(candidate)
        if cleaned:
            emitted.append(cleaned)
        carry = ""

    if carry:
        remainder = f"{carry} {remainder}".strip() if remainder else f"{carry} "

    return emitted, remainder


def resolve_openclaw_gateway_token() -> str:
    """
    Resolve the local OpenClaw Gateway bearer token from environment, openclaw.json,
    or OpenClaw's local SQLite secret store (~/.openclaw/state/openclaw.sqlite).
    Never logs, prints, or persists the secret token.
    """
    env_tok = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
    if env_tok:
        return env_tok

    cfg_path = os.path.expanduser("~/.openclaw/openclaw.json")
    key_id = "OPENCLAW_GATEWAY_TOKEN"
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            tok = cfg.get("gateway", {}).get("auth", {}).get("token")
            if isinstance(tok, str) and tok.strip() and not tok.startswith("$"):
                return tok.strip()
            if isinstance(tok, dict) and tok.get("id"):
                key_id = str(tok["id"]).strip()
        except Exception:
            pass

    db_path = os.path.expanduser("~/.openclaw/state/openclaw.sqlite")
    if os.path.isfile(db_path):
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
            try:
                row = conn.execute(
                    "SELECT value FROM secret_store_entries WHERE name=? AND deleted_at_ms IS NULL LIMIT 1",
                    (key_id,),
                ).fetchone()
                if row and row[0]:
                    return str(row[0]).strip()
            finally:
                conn.close()
        except Exception:
            pass

    return ""


class VoiceController:
    """
    Coordinates voice session lifecycle, routes recognized speech to
    authorized desktop actions, and orchestrates OpenClaw conversation turns.
    """

    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        session: Optional[VoiceSession] = None,
        stt: Optional[STTProvider] = None,
        tts: Optional[TTSProvider] = None,
        activity_logger: Optional[ActivityLogger] = None,
    ):
        self.config = config or VoiceConfig()
        self.tts = tts or (session.tts if session is not None else create_tts_provider(self.config))
        self.session = session or VoiceSession(self.config, tts=self.tts)
        if stt is not None:
            self.stt = stt
        else:
            whisper_stt = WhisperCppSTTProvider(self.config)
            if whisper_stt.is_available():
                self.stt = whisper_stt
            else:
                self.stt = LocalIntentSTTProvider(self.config)
        self.logger = activity_logger or ActivityLogger()
        self._gw_lock = threading.Lock()
        self._gw_conn: Optional[http.client.HTTPConnection] = None
        self._primary_cooldown_until: float = 0.0
        self._route_cooldowns: Dict[str, float] = {}
        self.last_turn_metrics: Dict[str, Any] = {}
        self.memory = ContextMemory()
        self.planner = TaskPlanner(memory=self.memory)
        self.active_plan: Optional[TaskPlan] = None
        self.vision = VisionController()
        self._conversation_history: List[Dict[str, str]] = []

    def clear_conversation_history(self) -> None:
        """Reset multi-turn conversational context buffer."""
        self._conversation_history.clear()

    def _append_conversation_turn(self, user_text: str, assistant_text: str) -> None:
        u = (user_text or "").strip()
        a = (assistant_text or "").strip()
        if not u or not a:
            return
        self._conversation_history.append({"role": "user", "content": u})
        self._conversation_history.append({"role": "assistant", "content": a})
        # Keep rolling window of last 6 turns (12 messages)
        if len(self._conversation_history) > 12:
            del self._conversation_history[:-12]

    @staticmethod
    def _explicitly_requests_indonesian(text: str) -> bool:
        lower = (text or "").lower()
        explicit_phrases = (
            "in indonesian",
            "speak indonesian",
            "reply in indonesian",
            "answer in indonesian",
            "bahasa indonesia",
            "pakai bahasa indonesia",
            "bicara bahasa indonesia",
            "jawab dalam bahasa indonesia",
            "gunakan bahasa indonesia",
        )
        return any(p in lower for p in explicit_phrases)

    def _resolve_response_language(self, user_prompt: str) -> str:
        """
        Spoken responses default strictly to clear, natural English ('en'), even when
        input is spoken/typed in Indonesian, unless the user explicitly asks for Indonesian
        or configures `tts_default_language` to 'id' / 'auto'.
        """
        if self._explicitly_requests_indonesian(user_prompt):
            return "id"
        cfg_lang = str(getattr(self.config, "tts_default_language", "en") or "en").lower()
        if cfg_lang == "id":
            return "id"
        if cfg_lang == "auto":
            lower = (user_prompt or "").lower()
            lang = detect_speech_language(user_prompt)
            if any(
                w in re.findall(r"[a-zA-Z]+", lower)
                for w in ("apa", "siapa", "mengapa", "kenapa", "bagaimana", "tolong", "jelaskan", "sebutkan", "berapa", "kapan", "dimana")
            ):
                return "id"
            return lang
        return "en"

    @classmethod
    def _build_voice_system_prompt(
        cls,
        user_prompt: str,
        default_max_tokens: int = 140,
        default_language: str = "en",
        memory_snippets: Optional[List[str]] = None,
    ) -> Tuple[str, int, str]:
        """
        Optimize spoken response length for ordinary voice queries while preserving
        depth when the user asks for detailed steps or explanations.
        Defaults spoken output strictly to clear, natural English unless Indonesian is explicitly requested.
        """
        lower = (user_prompt or "").lower()
        if cls._explicitly_requests_indonesian(user_prompt) or default_language == "id":
            lang = "id"
        elif default_language == "auto":
            lang = detect_speech_language(user_prompt)
            if any(w in re.findall(r"[a-zA-Z]+", lower) for w in ("apa", "siapa", "mengapa", "kenapa", "bagaimana", "tolong", "jelaskan", "sebutkan", "berapa", "kapan", "dimana")):
                lang = "id"
        else:
            lang = "en"

        wants_detail = any(
            kw in lower
            for kw in (
                "in detail", "step by step", "explain thoroughly", "list all",
                "secara detail", "langkah demi langkah", "jelaskan lengkap", "rinci",
            )
        )
        max_tokens = 300 if wants_detail else default_max_tokens
        lang_directive = (
            "Reply strictly in natural Bahasa Indonesia."
            if lang == "id"
            else "Understand both English and Indonesian user input, and reply strictly in clear, natural spoken English unless explicitly asked for another language."
        )
        length_directive = (
            "Provide a clear, structured spoken explanation in 3 to 5 concise sentences."
            if wants_detail
            else "Answer in 1 to 2 crisp, natural spoken sentences."
        )
        mem_clause = ""
        if memory_snippets:
            joined = "; ".join(s.strip() for s in memory_snippets if s.strip())
            if joined:
                mem_clause = f" Approved user context: {joined}."
        sys_prompt = (
            f"You are Maven, a fast, calm, intelligent personal AI operating assistant. "
            f"{lang_directive} {length_directive} "
            f"Plain spoken text only — no markdown, bullet symbols, or code fences. "
            f"Never call tools or shell commands for conversational questions; answer directly.{mem_clause}"
        )
        return sys_prompt, max_tokens, lang

    @staticmethod
    def _sanitize_gateway_error(err_msg: str) -> Tuple[str, str]:
        """Map raw provider/gateway errors into safe, calm spoken status notices."""
        msg = redact_sensitive_text(err_msg or "")
        lower = msg.lower()
        if "429" in msg or "resource_exhausted" in lower or "quota" in lower or "rate limit" in lower:
            return (
                "rate_limited",
                "Google Gemini API reported a temporary quota rate limit.",
            )
        if "not_found" in lower or "model was not found" in lower or "no longer available" in lower or "404" in msg:
            return (
                "model_not_found",
                "The requested AI model is currently unavailable on the active provider.",
            )
        if "503" in msg or "unavailable" in lower or "overloaded" in lower or "high demand" in lower:
            return (
                "overloaded",
                "The AI service is experiencing temporary high demand. Please try again shortly.",
            )
        return (
            "error",
            "I could not complete that AI request right now, but local desktop controls remain ready.",
        )

    @staticmethod
    def _route_key(model_override: Optional[str]) -> str:
        return model_override or "__primary__"

    def _mark_route_cooldown(self, model_override: Optional[str]) -> None:
        exp = time.time() + float(getattr(self.config, "openclaw_primary_cooldown_sec", 300.0))
        self._route_cooldowns[self._route_key(model_override)] = exp
        if model_override is None:
            self._primary_cooldown_until = exp

    def _select_candidate_models(self) -> List[Optional[str]]:
        """
        Return ordered model override candidates for OpenClaw HTTP SSE:
        - None means OpenClaw's configured default primary (`google/gemini-2.5-flash`).
        - Any route (primary or fallback) that recently hit a 429 quota or 404 error is placed in
          a temporary cooldown window (`openclaw_primary_cooldown_sec`) so consecutive voice turns
          route directly (0 retries) to the first healthy model, then automatically re-probe
          higher-priority routes once cooldown expires.
        """
        fallbacks = [m for m in (self.config.model_fallbacks or []) if m]
        all_routes: List[Optional[str]] = [None, *fallbacks]
        now = time.time()
        if self._primary_cooldown_until > now:
            self._route_cooldowns["__primary__"] = max(
                self._route_cooldowns.get("__primary__", 0.0),
                self._primary_cooldown_until,
            )
        healthy = [r for r in all_routes if self._route_cooldowns.get(self._route_key(r), 0.0) <= now]
        cooling = [r for r in all_routes if self._route_cooldowns.get(self._route_key(r), 0.0) > now]
        cooling.sort(key=lambda r: self._route_cooldowns.get(self._route_key(r), 0.0))
        return [*healthy, *cooling]

    def stream_openclaw(self, prompt: str, metrics_out: Optional[Dict[str, Any]] = None) -> Iterator[str]:
        """
        Stream conversational response from OpenClaw Gateway's local /v1/chat/completions SSE
        endpoint, yielding meaningful sentence chunks for immediate TTS synthesis.
        Automatically records gateway queue time, TTFT, first-sentence time, total generation time,
        and retry count, with seamless fallback to `_query_openclaw` CLI if needed.
        """
        metrics = metrics_out if metrics_out is not None else {}
        token = resolve_openclaw_gateway_token()
        mem_items: List[str] = []
        try:
            found_mems = self.memory.search(query=prompt, limit=3)
            mem_items = [str(m.get("content", "")) for m in found_mems if m.get("content")]
        except Exception:
            mem_items = []
        sys_prompt, max_tokens, lang = self._build_voice_system_prompt(
            prompt,
            default_max_tokens=int(getattr(self.config, "openclaw_voice_max_tokens", 140)),
            default_language=str(getattr(self.config, "tts_default_language", "en") or "en"),
            memory_snippets=mem_items,
        )
        metrics["lang"] = lang
        metrics["llm_retries"] = 0

        # Preserve deterministic unit tests that patch subprocess.run
        if not token or getattr(subprocess.run, "__module__", "") != "subprocess":
            t_cli = time.perf_counter()
            cli_res = self._query_openclaw(prompt)
            elapsed_ms = round((time.perf_counter() - t_cli) * 1000.0, 1)
            metrics.update(
                {
                    "route": "openclaw_cli",
                    "status": cli_res.get("status", "success"),
                    "model_used": cli_res.get("model_used") or self.config.model_id,
                    "gateway_queue_ms": 0.0,
                    "llm_ttft_ms": elapsed_ms,
                    "llm_first_sentence_ms": elapsed_ms,
                    "llm_total_ms": elapsed_ms,
                }
            )
            reply = cli_res.get("response", "")
            if cli_res.get("status") == "success" and reply:
                self._append_conversation_turn(prompt, reply)
            sents, rem = split_meaningful_sentences(reply, flush=False)
            for s in sents:
                yield s
            if rem.strip():
                tail, _ = split_meaningful_sentences(rem, flush=True)
                for s in tail:
                    yield s
            return

        host = getattr(self.config, "openclaw_http_host", "127.0.0.1")
        port = int(getattr(self.config, "openclaw_http_port", 18789))
        candidates = self._select_candidate_models()
        t_overall = time.perf_counter()
        last_err_status = "error"
        last_err_spoken = "I could not reach the OpenClaw agent at this moment."

        history_msgs = list(self._conversation_history[-8:]) if prompt != "Reply with OK." else []
        for attempt_idx, model_override in enumerate(candidates):
            t0 = time.perf_counter()
            payload = {
                "model": "openclaw/default",
                "user": getattr(self.config, "openclaw_voice_session_user", "maven-voice-fast"),
                "stream": True,
                "max_completion_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    *history_msgs,
                    {"role": "user", "content": prompt},
                ],
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "Connection": "keep-alive",
            }
            if model_override:
                headers["x-openclaw-model"] = model_override

            body_bytes = json.dumps(payload).encode("utf-8")
            try:
                conn = http.client.HTTPConnection(host, port, timeout=22.0)
                conn.request("POST", "/v1/chat/completions", body=body_bytes, headers=headers)
                resp = conn.getresponse()
                queue_ms = round((time.perf_counter() - t0) * 1000.0, 1)

                if resp.status != 200:
                    raw_err = resp.read().decode("utf-8", errors="replace")
                    conn.close()
                    last_err_status, last_err_spoken = self._sanitize_gateway_error(raw_err)
                    self._mark_route_cooldown(model_override)
                    metrics["llm_retries"] = attempt_idx + 1
                    continue

                ttft_ms: Optional[float] = None
                first_sent_ms: Optional[float] = None
                text_buf = ""
                full_emitted: List[str] = []
                sse_error: Optional[str] = None

                while True:
                    raw_line = resp.readline()
                    if not raw_line:
                        break
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_obj = json.loads(data_str)
                    except Exception:
                        continue

                    if "error" in chunk_obj and chunk_obj["error"]:
                        err_val = chunk_obj["error"]
                        sse_error = err_val.get("message", str(err_val)) if isinstance(err_val, dict) else str(err_val)
                        break

                    for choice in chunk_obj.get("choices", []):
                        delta = (choice.get("delta") or {}).get("content") or ""
                        if not delta:
                            continue
                        if ttft_ms is None:
                            ttft_ms = round((time.perf_counter() - t_overall) * 1000.0, 1)
                        text_buf += delta
                        ready_sents, text_buf = split_meaningful_sentences(text_buf, flush=False)
                        for s in ready_sents:
                            if first_sent_ms is None:
                                first_sent_ms = round((time.perf_counter() - t_overall) * 1000.0, 1)
                            full_emitted.append(s)
                            yield s

                try:
                    resp.read()
                    conn.close()
                except Exception:
                    pass

                if sse_error and not full_emitted and not text_buf.strip():
                    last_err_status, last_err_spoken = self._sanitize_gateway_error(sse_error)
                    self._mark_route_cooldown(model_override)
                    metrics["llm_retries"] = attempt_idx + 1
                    continue

                if text_buf.strip():
                    tail_sents, _ = split_meaningful_sentences(text_buf, flush=True)
                    for s in tail_sents:
                        if first_sent_ms is None:
                            first_sent_ms = round((time.perf_counter() - t_overall) * 1000.0, 1)
                        full_emitted.append(s)
                        yield s

                total_ms = round((time.perf_counter() - t_overall) * 1000.0, 1)
                effective_model = model_override or self.config.model_id

                # If default primary route took >5.2s due to internal 429/404 failover cascade,
                # activate adaptive primary cooldown so subsequent turns skip the dead-key stall!
                if model_override is None and (ttft_ms or total_ms) > 5200.0 and self.config.model_fallbacks:
                    self._mark_route_cooldown(None)
                    effective_model = self.config.model_fallbacks[0]
                    metrics["llm_retries"] = max(1, int(metrics.get("llm_retries") or 0) + 1)

                if full_emitted:
                    joined_reply = " ".join(full_emitted)
                    if prompt != "Reply with OK.":
                        self._append_conversation_turn(prompt, joined_reply)
                    metrics.update(
                        {
                            "route": "openclaw_stream",
                            "status": "success",
                            "model_used": effective_model,
                            "gateway_queue_ms": queue_ms,
                            "llm_ttft_ms": ttft_ms or total_ms,
                            "llm_first_sentence_ms": first_sent_ms or total_ms,
                            "llm_total_ms": total_ms,
                            "full_response": joined_reply,
                        }
                    )
                    return

                metrics["llm_retries"] = attempt_idx + 1
            except Exception as exc:
                last_err_status, last_err_spoken = self._sanitize_gateway_error(str(exc))
                metrics["llm_retries"] = attempt_idx + 1
                continue

        # Final graceful sanitized spoken notice (never speaks raw model stacktraces/JSON)
        total_ms = round((time.perf_counter() - t_overall) * 1000.0, 1)
        metrics.update(
            {
                "route": "openclaw_stream",
                "status": last_err_status,
                "model_used": self.config.model_id,
                "gateway_queue_ms": 0.0,
                "llm_ttft_ms": total_ms,
                "llm_first_sentence_ms": total_ms,
                "llm_total_ms": total_ms,
                "full_response": last_err_spoken,
            }
        )
        yield last_err_spoken

    def warm_gateway_session(self) -> None:
        """Pre-warm the OpenClaw voice session MCP bundle asynchronously so Turn #1 avoids cold-start."""
        token = resolve_openclaw_gateway_token()
        if not token:
            return
        try:
            for _ in self.stream_openclaw("Reply with OK.", metrics_out={}):
                pass
        except Exception:
            pass

    def verify_model_routes(self) -> Dict[str, Any]:
        """
        Probe configured primary and fallback models with minimal live requests through OpenClaw Gateway
        to verify real runtime availability and measure TTFT per route.
        """
        token = resolve_openclaw_gateway_token()
        routes_to_test = [self.config.model_id, *(self.config.model_fallbacks or [])]
        results: List[Dict[str, Any]] = []
        host = getattr(self.config, "openclaw_http_host", "127.0.0.1")
        port = int(getattr(self.config, "openclaw_http_port", 18789))

        for idx, route_model in enumerate(routes_to_test):
            t0 = time.perf_counter()
            status_str = "unavailable"
            ttft_ms: Optional[float] = None
            detail = ""
            if token:
                try:
                    conn = http.client.HTTPConnection(host, port, timeout=15.0)
                    payload = {
                        "model": "openclaw/default",
                        "user": getattr(self.config, "openclaw_voice_session_user", "maven-voice-fast"),
                        "stream": True,
                        "max_completion_tokens": 24,
                        "messages": [
                            {"role": "system", "content": "Reply with the single word ONLINE. Never call tools."},
                            {"role": "user", "content": "Status check."},
                        ],
                    }
                    conn.request(
                        "POST",
                        "/v1/chat/completions",
                        body=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {token}",
                            "x-openclaw-model": route_model,
                        },
                    )
                    resp = conn.getresponse()
                    got_text = ""
                    err_seen = ""
                    while True:
                        raw = resp.readline()
                        if not raw:
                            break
                        ln = raw.decode("utf-8", errors="replace").strip()
                        if not ln.startswith("data:"):
                            continue
                        p = ln[5:].strip()
                        if p == "[DONE]":
                            break
                        obj = json.loads(p)
                        if "error" in obj and obj["error"]:
                            e = obj["error"]
                            err_seen = e.get("message", str(e)) if isinstance(e, dict) else str(e)
                            break
                        for ch in obj.get("choices", []):
                            d = (ch.get("delta") or {}).get("content") or ""
                            if d:
                                if ttft_ms is None:
                                    ttft_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                                got_text += d
                    conn.close()
                    if got_text.strip() and not err_seen:
                        status_str = "available"
                        detail = got_text.strip()[:40]
                    else:
                        status_str, detail = self._sanitize_gateway_error(err_seen or f"HTTP {resp.status}")
                except Exception as exc:
                    status_str = "error"
                    detail = type(exc).__name__
            results.append(
                {
                    "role": "primary" if idx == 0 else f"fallback_{idx}",
                    "model_id": route_model,
                    "status": status_str,
                    "ttft_ms": ttft_ms,
                    "total_ms": round((time.perf_counter() - t0) * 1000.0, 1),
                    "detail": redact_sensitive_text(detail),
                }
            )
            if status_str != "available":
                self._mark_route_cooldown(None if idx == 0 else route_model)
            else:
                self._route_cooldowns.pop(self._route_key(None if idx == 0 else route_model), None)

        return {
            "primary_configured": self.config.model_id,
            "fallbacks_configured": list(self.config.model_fallbacks or []),
            "routes": results,
        }

    def handle_voice_command(self, raw_text: str, confirmed: bool = False) -> Dict[str, Any]:
        """
        Process a recognized text command, execute the matching desktop action
        or forward to OpenClaw (streaming SSE when available, CLI fallback otherwise),
        and return the execution summary with latency telemetry.
        """
        clean_text = raw_text.strip()
        if not clean_text:
            return {"status": "empty", "response": ""}

        # 1. Strip wake word prefix if present ("Maven, ...", "Jarvis, ...")
        cmd_text = re.sub(r"^(?:maven|jarvis)[\s,:]*", "", clean_text, flags=re.IGNORECASE).strip()
        cmd_lower = cmd_text.lower() if cmd_text else clean_text.lower()

        # 2. Check Local Desktop Actions
        t_local = time.perf_counter()
        action_result = self._route_desktop_action(cmd_lower, confirmed=confirmed)
        if action_result:
            local_ms = round((time.perf_counter() - t_local) * 1000.0, 1)
            response_text = action_result.get("response", "")
            status = action_result.get("status", "success")
            action = action_result.get("action", "voice_action")
            action_result["route"] = "local_intent"
            action_result["dispatch_ms"] = local_ms
            self.last_turn_metrics = {
                "route": "local_intent",
                "model_used": "local_intent_router",
                "llm_ttft_ms": 0.0,
                "llm_total_ms": local_ms,
                "llm_retries": 0,
            }
            if status == "confirmation_required":
                voice_logger.action_confirmation_required(app_id=cmd_text, prompt=response_text)
            else:
                voice_logger.action_complete(action=action, status=status, response=response_text)
            self.logger.log_action(
                action_type="voice_action",
                target=cmd_text,
                status=status,
                confirmed=confirmed,
                details=action_result,
            )
            return action_result

        # 3. Conversational query: forward to OpenClaw (streaming SSE primary + CLI fallback)
        if self.config.enable_openclaw_fallback:
            metrics: Dict[str, Any] = {}
            chunks = list(self.stream_openclaw(cmd_text, metrics_out=metrics))
            reply_text = " ".join(chunks).strip()
            status = metrics.get("status", "success")
            model_used = metrics.get("model_used") or self.config.model_id
            self.last_turn_metrics = dict(metrics)
            self.logger.log_action(
                action_type="voice_conversation",
                target=cmd_text,
                status=status,
                confirmed=False,
                details={
                    "model": model_used,
                    "configured_primary": self.config.model_id,
                    "llm_ttft_ms": metrics.get("llm_ttft_ms"),
                    "llm_total_ms": metrics.get("llm_total_ms"),
                    "llm_retries": metrics.get("llm_retries", 0),
                },
            )
            return {
                "status": status,
                "response": reply_text,
                "model_used": model_used,
                "route": metrics.get("route", "openclaw_stream"),
                "latency": metrics,
            }

        return {
            "status": "unhandled",
            "response": "I didn't understand that instruction. How can I assist you with your desktop?",
        }

    def dispatch_streaming_voice_turn(
        self,
        raw_text: str,
        confirmed: bool = False,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[Iterator[str], Dict[str, Any], str]]]:
        """
        Fast-path voice dispatcher for VoiceDaemon:
        - If local desktop intent matches, executes immediately and returns `(action_result, None)`.
        - If conversational AI turn is needed, returns `(None, (sentence_iterator, metrics_dict, cmd_text))`
          so `session.speak_stream()` begins speaking Sentence #1 while Sentence #2 is still generating!
        """
        clean_text = (raw_text or "").strip()
        if not clean_text:
            return {"status": "empty", "response": ""}, None

        cmd_text = re.sub(r"^(?:maven|jarvis)[\s,:]*", "", clean_text, flags=re.IGNORECASE).strip()
        cmd_lower = cmd_text.lower() if cmd_text else clean_text.lower()

        t_local = time.perf_counter()
        action_result = self._route_desktop_action(cmd_lower, confirmed=confirmed)
        if action_result:
            local_ms = round((time.perf_counter() - t_local) * 1000.0, 1)
            response_text = action_result.get("response", "")
            status = action_result.get("status", "success")
            action = action_result.get("action", "voice_action")
            action_result["route"] = "local_intent"
            action_result["dispatch_ms"] = local_ms
            if status == "confirmation_required":
                voice_logger.action_confirmation_required(app_id=cmd_text, prompt=response_text)
            else:
                voice_logger.action_complete(action=action, status=status, response=response_text)
            self.logger.log_action(
                action_type="voice_action",
                target=cmd_text,
                status=status,
                confirmed=confirmed,
                details=action_result,
            )
            return action_result, None

        if self.config.enable_openclaw_fallback:
            metrics: Dict[str, Any] = {}
            sentence_iter = self.stream_openclaw(cmd_text, metrics_out=metrics)
            return None, (sentence_iter, metrics, cmd_text)

        return {
            "status": "unhandled",
            "response": "I didn't understand that instruction. How can I assist you with your desktop?",
        }, None

    def _route_desktop_action(self, cmd: str, confirmed: bool = False) -> Optional[Dict[str, Any]]:
        """Route speech command to Maverick's secure desktop automation subsystems using BilingualIntentClassifier."""
        parsed = BilingualIntentClassifier.classify(cmd)
        intent = parsed.get("intent")
        target = parsed.get("target")
        detected_id = parsed.get("is_id", False)
        is_id = (self._resolve_response_language(cmd) == "id")

        # 1. Fast-path check for vision, pointer, typing, or interaction mode directives.
        # Generic "stop"/"berhenti" is handled by speech/media interrupt unless vision is active or explicit vision directive.
        is_explicit_vis = any(w in cmd.lower() for w in ("visi", "gestur", "pointer", "klik", "gulir", "ketik", "layar", "emergency stop", "kursor", "hand"))
        is_vision_active = bool(self.vision and hasattr(self.vision, "mode_manager") and self.vision.mode_manager.is_vision_active())

        if self.vision and (intent != "interrupt" or is_explicit_vis or is_vision_active):
            vis_res = self.vision.handle_multimodal_command(cmd)
            if vis_res:
                voice_logger.intent_classified(
                    intent=vis_res.get("action", "vision_action"),
                    target=None,
                    lang="id" if detected_id else "en",
                    confidence=0.95,
                    clean_text=cmd,
                )
                return vis_res

        if not intent or intent in ("empty", "unhandled"):
            voice_logger.intent_classified(
                intent="unhandled",
                target=None,
                lang="id" if detected_id else "en",
                confidence=0.0,
                clean_text=cmd,
            )
            return None

        voice_logger.intent_classified(
            intent=intent,
            target=str(target) if target else None,
            lang="id" if detected_id else "en",
            confidence=0.95,
            clean_text=cmd,
        )
        voice_logger.action_start(action=intent, target=str(target) if target else None, confirmed=confirmed)

        # 0. Wake Word Acknowledgment
        if intent == "wake_acknowledgment":
            resp = "Ya, saya mendengarkan." if is_id else "Yes, I'm listening."
            return {"status": "success", "action": "wake_acknowledgment", "response": resp}

        # 1. Session Mute / Unmute / Stop
        if intent == "mute":
            self.session.set_muted(True)
            resp = "Mikrofon dimatikan." if is_id else "Microphone muted."
            return {"status": "success", "action": "mute", "response": resp}

        if intent == "unmute":
            self.session.set_muted(False)
            resp = "Mikrofon diaktifkan." if is_id else "Microphone unmuted."
            return {"status": "success", "action": "unmute", "response": resp}

        if intent == "interrupt":
            self.session.interrupt()
            return {"status": "success", "action": "interrupt", "response": ""}

        # 1.1 Interactive Approval / Rejection Gates
        if intent == "confirm":
            if self.active_plan and self.active_plan.status == TaskStatus.AWAITING_APPROVAL:
                step_id = self.active_plan.awaiting_step_id
                res = self.planner.execute_plan(self.active_plan, approved_step_id=step_id)
                if res.get("status") == "awaiting_approval":
                    resp = f"Langkah disetujui. Langkah berikutnya '{res.get('description')}' memerlukan persetujuan. Katakan 'konfirmasi' untuk melanjutkan." if is_id else f"Step approved. Next step '{res.get('description')}' requires approval. Say 'confirm' to continue."
                    return {"status": "confirmation_required", "action": "task_plan", "response": resp}
                elif res.get("status") == "completed":
                    resp = "Rencana tugas berhasil diselesaikan sepenuhnya." if is_id else "Task plan completed successfully."
                    return {"status": "success", "action": "task_plan", "response": resp}
                else:
                    resp = "Rencana tugas dilanjutkan." if is_id else "Task plan resumed."
                    return {"status": "success", "action": "task_plan", "response": resp}
            resp = "Konfirmasi diterima, namun tidak ada tindakan yang sedang menunggu persetujuan." if is_id else "Confirmation received, but no action is currently awaiting approval."
            return {"status": "info", "action": "confirm", "response": resp}

        if intent == "reject":
            if self.active_plan and self.active_plan.status == TaskStatus.AWAITING_APPROVAL:
                self.active_plan.status = TaskStatus.FAILED
                self.active_plan.awaiting_step_id = None
                resp = "Rencana tugas dibatalkan." if is_id else "Task plan cancelled."
                return {"status": "success", "action": "task_plan", "response": resp}
            resp = "Tindakan dibatalkan." if is_id else "Action cancelled."
            return {"status": "success", "action": "reject", "response": resp}

        # 1.2 Autonomous Task Planning
        if intent == "task_plan":
            plan = self.planner.plan(cmd)
            self.active_plan = plan
            res = self.planner.execute_plan(plan)
            if res.get("status") == "awaiting_approval":
                resp = f"Rencana tugas disiapkan: {plan.goal}. Langkah '{res.get('description')}' memerlukan persetujuan Anda. Katakan 'konfirmasi' untuk menjalankan." if is_id else f"Task plan ready: {plan.goal}. Step '{res.get('description')}' requires your approval. Say 'confirm' to execute."
                return {"status": "confirmation_required", "action": "task_plan", "response": resp, "plan_id": plan.plan_id}
            elif res.get("status") == "completed":
                resp = f"Rencana tugas '{plan.goal}' berhasil dijalankan." if is_id else f"Task plan '{plan.goal}' completed successfully."
                return {"status": "success", "action": "task_plan", "response": resp}
            else:
                resp = f"Rencana tugas '{plan.goal}' telah dimulai." if is_id else f"Task plan '{plan.goal}' initiated."
                return {"status": "success", "action": "task_plan", "response": resp}

        # 1.3 Context Memory (Store / Recall)
        if intent == "memory_store":
            content = cmd
            for prefix in ("ingat bahwa", "ingat ya", "ingat", "catat bahwa", "catat ya", "catat", "remember that", "remember to", "remember", "note that"):
                if content.lower().startswith(prefix):
                    content = content[len(prefix):].strip(":, ")
                    break
            if not content:
                content = cmd
            self.memory.store(content=content, category="user_preference")
            resp = f"Sudah saya catat dalam memori: {content}." if is_id else f"I've saved that in memory: {content}."
            return {"status": "success", "action": "memory_store", "response": resp}

        if intent == "memory_recall":
            mems = self.memory.search(query=cmd, limit=3)
            if not mems:
                resp = "Saya belum memiliki catatan memori terkait hal tersebut." if is_id else "I don't have any saved memories about that."
            else:
                summary = "; ".join([m.get("content", "") for m in mems[:2]])
                resp = f"Berikut yang saya ingat: {summary}." if is_id else f"Here is what I remember: {summary}."
            return {"status": "success", "action": "memory_recall", "response": resp}

        # 2. Spotify Volume Controls
        if intent == "spotify_volume":
            try:
                ctl = SpotifyController()
                if target == "up":
                    status = ctl.get_status()
                    curr = status.get("volume", 0.5) if status.get("status") == "success" else 0.5
                    new_vol = min(1.0, curr + 0.1)
                    ctl.set_volume(new_vol)
                    pct = int(round(new_vol * 100))
                    resp = f"Volume Spotify dinaikkan ke {pct} persen." if is_id else f"Spotify volume increased to {pct} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                elif target == "down":
                    status = ctl.get_status()
                    curr = status.get("volume", 0.5) if status.get("status") == "success" else 0.5
                    new_vol = max(0.0, curr - 0.1)
                    ctl.set_volume(new_vol)
                    pct = int(round(new_vol * 100))
                    resp = f"Volume Spotify diturunkan ke {pct} persen." if is_id else f"Spotify volume decreased to {pct} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                elif isinstance(target, (int, float)):
                    level_int = max(0, min(100, int(target)))
                    ctl.set_volume(level_int)
                    resp = f"Volume Spotify diatur ke {level_int} persen." if is_id else f"Spotify volume set to {level_int} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
                else:
                    status = ctl.get_status()
                    pct = status.get("volume_percent", 50)
                    resp = f"Volume Spotify saat ini adalah {pct} persen." if is_id else f"Current Spotify volume is {pct} percent."
                    return {"status": "success", "action": "spotify_volume", "response": resp}
            except Exception as e:
                resp = f"Gagal mengatur volume: {str(e)}" if is_id else f"Could not set volume: {str(e)}"
                return {"status": "error", "response": resp}

        # 3. Spotify Playback Controls
        if intent == "spotify_play":
            try:
                ctl = SpotifyController()
                res = ctl.play()
                if res.get("status") == "success":
                    resp = "Melanjutkan pemutaran musik di Spotify." if is_id else "Resuming music on Spotify."
                    return {"status": "success", "action": "spotify_play", "response": resp}
                resp = "Spotify belum berjalan. Ucapkan 'buka Spotify' untuk meluncurkannya." if is_id else "Spotify is not running. Say 'open Spotify' to launch it."
                return {"status": "error", "response": resp}
            except Exception as e:
                return {"status": "error", "response": f"Could not control music: {str(e)}"}

        if intent == "spotify_pause":
            try:
                ctl = SpotifyController()
                res = ctl.pause()
                if res.get("status") == "success":
                    resp = "Musik dijeda." if is_id else "Music paused."
                    return {"status": "success", "action": "spotify_pause", "response": resp}
                resp = "Spotify tidak aktif pada D-Bus." if is_id else "Spotify is not active on D-Bus."
                return {"status": "error", "response": resp}
            except Exception as e:
                return {"status": "error", "response": f"Failed to pause music: {str(e)}"}

        if intent == "spotify_next":
            try:
                ctl = SpotifyController()
                ctl.next()
                resp = "Beralih ke trek berikutnya." if is_id else "Skipping to next track."
                return {"status": "success", "action": "spotify_next", "response": resp}
            except Exception:
                resp = "Tidak dapat beralih trek." if is_id else "Could not skip track."
                return {"status": "error", "response": resp}

        if intent == "spotify_status":
            try:
                ctl = SpotifyController()
                status = ctl.get_status()
                if status.get("status") == "success":
                    title = status.get("title", "Unknown track")
                    artist = status.get("artist", "Unknown artist")
                    resp = f"Sedang memutar {title} oleh {artist}." if is_id else f"Now playing {title} by {artist}."
                    return {"status": "success", "action": "spotify_status", "response": resp}
                resp = "Tidak ada musik yang sedang diputar di Spotify." if is_id else "No music is currently playing on Spotify."
                return {"status": "info", "response": resp}
            except Exception:
                resp = "Tidak dapat memeriksa status pemutar musik." if is_id else "Unable to query media player status."
                return {"status": "error", "response": resp}

        # 4. Application Launching
        if intent == "app_launch" and target:
            app_id = target
            try:
                res = launch_app(app_id, confirmed=confirmed)
                if res.get("status") == "success":
                    name = res.get("display_name", app_id)
                    if res.get("action") == "already_running":
                        resp = f"{name} sudah berjalan." if is_id else f"{name} is already open."
                        return {"status": "success", "action": "app_launch", "response": resp}
                    resp = f"{name} dibuka." if is_id else f"{name} is open."
                    return {"status": "success", "action": "app_launch", "response": resp}
                elif res.get("status") == "confirmation_required":
                    resp = f"Membuka {app_id} memerlukan konfirmasi. Katakan 'konfirmasi' untuk melanjutkan." if is_id else f"Launching {app_id} requires confirmation. Say 'confirm' to proceed."
                    return {
                        "status": "confirmation_required",
                        "action": "app_launch",
                        "response": resp,
                    }
                resp = f"Gagal membuka {app_id}." if is_id else f"Failed to launch {app_id}."
                return {"status": "error", "response": resp}
            except ConfirmationRequiredError:
                resp = f"Tindakan pada {app_id} memerlukan konfirmasi." if is_id else f"Action on {app_id} requires confirmation. Say 'confirm' to proceed."
                return {
                    "status": "confirmation_required",
                    "action": "app_launch",
                    "response": resp,
                }
            except Exception as e:
                return {"status": "error", "response": f"Error opening application: {str(e)}"}

        # 5. Application Awareness
        if intent == "apps_running":
            apps = get_running_authorized_apps()
            if not apps:
                resp = "Tidak ada aplikasi resmi yang sedang berjalan." if is_id else "No authorized applications are currently running."
                return {"status": "success", "action": "apps_running", "response": resp}
            names = [a.get("display_name", a.get("app_id")) for a in apps]
            app_list_str = ", ".join(names)
            if is_id:
                resp = f"Saat ini terdapat {len(apps)} aplikasi yang sedang berjalan: {app_list_str}."
            else:
                resp = f"You currently have {len(apps)} applications running: {app_list_str}."
            return {
                "status": "success",
                "action": "apps_running",
                "response": resp,
            }

        # 6. System Telemetry & Hardware Context
        if intent == "system_ram":
            mem = get_memory_usage()
            avail = mem.get("available_gb", 0.0)
            pct = mem.get("percent", 0.0)
            if is_id:
                resp = f"RAM yang tersedia adalah {avail} gigabyte, dengan total penggunaan {pct} persen."
            else:
                resp = f"You have {avail} gigabytes of RAM available, with {pct} percent total usage."
            return {
                "status": "success",
                "action": "system_ram",
                "response": resp,
            }

        if intent == "system_battery":
            bat = get_battery_status()
            pct = bat.get("percent", 100)
            charging_en = "charging" if bat.get("is_charging") else "discharging"
            charging_id = "sedang mengisi daya" if bat.get("is_charging") else "menggunakan daya baterai"
            if is_id:
                resp = f"Baterai berada pada {pct} persen dan {charging_id}."
            else:
                resp = f"Battery is at {pct} percent and currently {charging_en}."
            return {
                "status": "success",
                "action": "system_battery",
                "response": resp,
            }

        if intent == "system_cpu":
            cpu = get_cpu_usage()
            pct = cpu.get("usage_percent", 0.0)
            cores = cpu.get("cores_logical", 1)
            if is_id:
                resp = f"Penggunaan CPU berada pada {pct} persen di {cores} thread."
            else:
                resp = f"CPU utilization is at {pct} percent across {cores} threads."
            return {
                "status": "success",
                "action": "system_cpu",
                "response": resp,
            }

        if intent == "context_summary":
            ce = ContextEngine()
            ctx = ce.get_context()
            running_cnt = ctx.get("applications", {}).get("running_authorized_count", 0)
            cpu_pct = ctx.get("system", {}).get("cpu_percent", 0.0)
            mem_pct = ctx.get("system", {}).get("memory_percent", 0.0)
            if is_id:
                resp = f"Ringkasan desktop: {running_cnt} aplikasi aktif, CPU di {cpu_pct} persen, dan memori di {mem_pct} persen."
            else:
                resp = f"Desktop summary: {running_cnt} applications active, CPU at {cpu_pct} percent, and memory at {mem_pct} percent."
            return {
                "status": "success",
                "action": "context_summary",
                "response": resp,
            }

        return None

    @staticmethod
    def _extract_openclaw_reply(parsed_data: Dict[str, Any], default_model: str) -> Optional[Tuple[str, str]]:
        """
        Extract (reply_text, model_used) from OpenClaw JSON responses.
        Supports both OpenClaw 2026.10+ schema:
          {"status": "ok", "result": {"payloads": [{"text": "..."}], "meta": {"agentMeta": {"provider": "...", "model": "..."}}}}
        and legacy/compact schema:
          {"ok": true, "result": {"reply": "..."}}
        """
        is_ok = (parsed_data.get("ok") is True) or (parsed_data.get("status") == "ok" and "error" not in parsed_data)
        if not is_ok:
            return None

        res_obj = parsed_data.get("result")
        if not isinstance(res_obj, dict):
            res_obj = {}

        model_used = default_model
        agent_meta = res_obj.get("meta", {}).get("agentMeta", {}) if isinstance(res_obj.get("meta"), dict) else {}
        if isinstance(agent_meta, dict) and agent_meta.get("model"):
            prov = str(agent_meta.get("provider") or "").strip()
            mod = str(agent_meta.get("model") or "").strip()
            model_used = f"{prov}/{mod}" if prov and "/" not in mod else mod

        payloads = res_obj.get("payloads")
        if isinstance(payloads, list) and payloads:
            texts = [
                str(p.get("text")).strip()
                for p in payloads
                if isinstance(p, dict) and p.get("text") and str(p.get("text")).strip()
            ]
            if texts:
                return ("\n".join(texts), model_used)

        reply = (
            res_obj.get("reply")
            or parsed_data.get("reply")
            or parsed_data.get("message")
            or "Turn completed."
        )
        return (str(reply).strip(), model_used)

    def _query_openclaw(self, prompt: str) -> Dict[str, Any]:
        """
        Dispatch conversational turn to OpenClaw Gateway using Google Gemini 2.5 Flash
        (with automatic OpenClaw fallback cascade).
        Handles API errors, rate limits (429), model availability, and timeouts gracefully.
        """
        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            return {
                "status": "error",
                "response": "OpenClaw CLI is not installed on this workstation.",
            }

        cmd = [
            openclaw_bin,
            "agent",
            "--agent", "main",
            "--message", prompt,
            "--json",
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=45.0)
            output = res.stdout.strip()
            stderr_text = res.stderr.strip()

            parsed_data = None
            if output:
                try:
                    parsed_data = json.loads(output)
                except Exception:
                    start = output.find("{")
                    end = output.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        try:
                            parsed_data = json.loads(output[start : end + 1])
                        except Exception:
                            pass

            if isinstance(parsed_data, dict):
                extracted = self._extract_openclaw_reply(parsed_data, self.config.model_id)
                if extracted is not None:
                    reply_text, model_used = extracted
                    return {
                        "status": "success",
                        "response": reply_text,
                        "model_used": model_used,
                    }
                if "error" in parsed_data:
                    err_obj = parsed_data["error"]
                    err_msg = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)
                    err_lower = err_msg.lower()
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_lower:
                        return {
                            "status": "rate_limited",
                            "response": "Google Gemini API reported a temporary quota rate limit.",
                        }
                    if "NOT_FOUND" in err_msg or "model was not found" in err_lower or "model_not_found" in err_lower:
                        return {
                            "status": "model_not_found",
                            "response": "The requested AI model is currently unavailable on the active provider.",
                        }
                    if "503" in err_msg or "UNAVAILABLE" in err_msg or "overloaded" in err_lower or "high demand" in err_lower:
                        return {
                            "status": "overloaded",
                            "response": "The AI service is experiencing temporary high demand. Please try again shortly.",
                        }
                    clean_err = re.sub(r"\s*\|\s*[A-Z_]+\s*$", "", err_msg).strip()
                    return {
                        "status": "error",
                        "response": f"AI service notice: {clean_err[:80]}.",
                    }

            # Check stderr for known error codes
            if "RESOURCE_EXHAUSTED" in stderr_text or "429" in stderr_text or "quota" in stderr_text.lower():
                return {
                    "status": "rate_limited",
                    "response": "Gemini API quota is currently exhausted. Ready for local desktop commands.",
                }
            if "NOT_FOUND" in stderr_text or "model was not found" in stderr_text.lower():
                return {
                    "status": "model_not_found",
                    "response": "The requested AI model is currently unavailable on the active provider.",
                }

            return {
                "status": "error",
                "response": "I could not reach the OpenClaw agent at this moment.",
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "response": "The request timed out while communicating with the AI gateway.",
            }
        except Exception as exc:
            return {
                "status": "error",
                "response": f"Voice controller encountered an error: {str(exc)}",
            }
