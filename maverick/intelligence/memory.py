"""Maverick DevOS - Persistent Context Memory Engine."""

import hashlib
import json
import math
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from maverick.core.security import redact_sensitive_text


class ContextMemory:
    """
    Transparent, user-controlled persistent memory store for Maven JARVIS.
    Stores project context, user preferences, past decisions, and environment details.
    Ranks memories by semantic keyword relevance, tag overlap, and temporal recency decay.
    Enforces strict credential scrubbing: NEVER stores passwords, API keys, or tokens.
    Persists locally in ~/.config/maverick/memory.json with 0600 permissions.
    """

    DEFAULT_STORE_PATH = os.path.expanduser("~/.config/maverick/memory.json")

    def __init__(self, store_path: str = DEFAULT_STORE_PATH):
        self.store_path = store_path
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure parent directory exists and file has restrictive permissions."""
        dir_name = os.path.dirname(self.store_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o700, exist_ok=True)
        if not os.path.isfile(self.store_path):
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "memories": {}}, f, indent=2)
            try:
                os.chmod(self.store_path, 0o600)
            except OSError:
                pass

    def _read_store(self) -> Dict[str, Any]:
        """Read data from storage file with corruption fallback."""
        if not os.path.isfile(self.store_path):
            return {"version": 1, "memories": {}}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "memories" in data:
                    return data
        except Exception:
            pass
        return {"version": 1, "memories": {}}

    def _write_store(self, data: Dict[str, Any]) -> None:
        """Atomic write to storage file with 0600 permissions."""
        tmp_path = f"{self.store_path}.tmp.{os.getpid()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.store_path)
            try:
                os.chmod(self.store_path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _generate_id(content: str) -> str:
        """Generate deterministic 10-char hex identifier from content hash + epoch."""
        h = hashlib.sha256(f"{content}_{time.time()}".encode("utf-8")).hexdigest()
        return f"mem_{h[:10]}"

    def store(
        self,
        content: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        source: str = "user",
    ) -> Dict[str, Any]:
        """
        Store a new piece of persistent memory.
        Strictly scrubs sensitive credentials, tokens, and keys before persisting.
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty.")

        # Security scrub
        clean_content = redact_sensitive_text(content.strip())
        now = time.time()
        mem_id = self._generate_id(clean_content)
        norm_tags = [t.strip().lower() for t in (tags or []) if t.strip()]

        record = {
            "id": mem_id,
            "category": category.strip().lower(),
            "content": clean_content,
            "tags": norm_tags,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "access_count": 0,
        }

        with self._lock:
            data = self._read_store()
            data["memories"][mem_id] = record
            self._write_store(data)

        return record

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a memory record by ID and increment access counter."""
        with self._lock:
            data = self._read_store()
            rec = data["memories"].get(memory_id)
            if rec:
                rec["access_count"] = rec.get("access_count", 0) + 1
                self._write_store(data)
                return dict(rec)
            return None

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search memories by semantic keyword relevance, tag overlap, and temporal recency decay.
        Returns ranked list of matching memory dictionaries with relevance score.
        """
        if not query or not query.strip():
            return self.list_all(category=category, limit=limit)

        q_clean = query.lower()
        q_tokens = set(re.findall(r"\w+", q_clean))
        now = time.time()

        with self._lock:
            data = self._read_store()
            memories = list(data["memories"].values())

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for mem in memories:
            if category and mem.get("category") != category.lower():
                continue

            content = mem.get("content", "").lower()
            tags = set(mem.get("tags", []))
            c_tokens = set(re.findall(r"\w+", content))

            # 1. Exact phrase boost
            exact_match_score = 4.0 if q_clean in content else 0.0

            # 2. Token overlap (Jaccard / intersection)
            shared_tokens = q_tokens.intersection(c_tokens)
            token_score = len(shared_tokens) * 2.0

            # 3. Tag overlap
            tag_score = len(q_tokens.intersection(tags)) * 3.0

            base_score = exact_match_score + token_score + tag_score
            if base_score <= 0.0:
                continue

            # 4. Temporal recency decay: half-life of 30 days (2,592,000s)
            age_sec = max(0.0, now - mem.get("updated_at", now))
            decay_factor = math.exp(-age_sec / 2592000.0)
            final_score = base_score * (0.6 + 0.4 * decay_factor)

            scored.append((final_score, dict(mem)))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, item in scored[:limit]:
            item["relevance_score"] = round(score, 3)
            results.append(item)

        return results

    def update(
        self,
        memory_id: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Update content or tags of an existing memory."""
        clean_content = redact_sensitive_text(content.strip())
        with self._lock:
            data = self._read_store()
            if memory_id not in data["memories"]:
                return False
            rec = data["memories"][memory_id]
            rec["content"] = clean_content
            if tags is not None:
                rec["tags"] = [t.strip().lower() for t in tags if t.strip()]
            rec["updated_at"] = time.time()
            self._write_store(data)
            return True

    def delete(self, memory_id: str) -> bool:
        """Delete a memory record by ID."""
        with self._lock:
            data = self._read_store()
            if memory_id in data["memories"]:
                del data["memories"][memory_id]
                self._write_store(data)
                return True
            return False

    def clear_category(self, category: str) -> int:
        """Delete all memories in a given category. Returns count of deleted records."""
        cat_lower = category.strip().lower()
        with self._lock:
            data = self._read_store()
            initial = len(data["memories"])
            data["memories"] = {
                k: v for k, v in data["memories"].items()
                if v.get("category") != cat_lower
            }
            deleted = initial - len(data["memories"])
            if deleted > 0:
                self._write_store(data)
            return deleted

    def list_all(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List all memories ordered by updated_at descending."""
        with self._lock:
            data = self._read_store()
            memories = list(data["memories"].values())

        if category:
            memories = [m for m in memories if m.get("category") == category.lower()]

        memories.sort(key=lambda m: m.get("updated_at", 0.0), reverse=True)
        return memories[:limit]

    def format_context_prompt(self, query: str, limit: int = 4) -> str:
        """
        Format top-scoring memories as a concise context injection block
        for the AI model's system prompt.
        """
        matches = self.search(query, limit=limit)
        if not matches:
            return ""

        lines = ["Relevant Persistent Context & Preferences:"]
        for m in matches:
            cat = m.get("category", "general")
            content = m.get("content", "")
            lines.append(f"- [{cat.upper()}] {content}")

        return "\n".join(lines)
