"""Maverick DevOS - Persistent Context Memory Engine with Multi-Tier Categorization & Retention."""

from enum import Enum
import hashlib
import json
import math
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from maverick.core.security import redact_sensitive_text


class MemoryCategory(str, Enum):
    """Canonical categories for Maven JARVIS context memory."""
    SHORT_TERM_CONVERSATION = "short_term_conversation"
    ACTIVE_TASK = "active_task"
    USER_PREFERENCES = "user_preferences"
    PROJECT_CONTEXT = "project_context"
    TASK_HISTORY = "task_history"
    VERIFIED_KNOWLEDGE = "verified_knowledge"
    GENERAL = "general"  # Backward compatibility alias


# Strict retention policies per category to ensure bounded RAM and disk usage
RETENTION_POLICIES: Dict[str, Dict[str, Optional[int]]] = {
    MemoryCategory.SHORT_TERM_CONVERSATION.value: {"ttl_sec": 86400, "max_entries": 100},      # 24 hours
    MemoryCategory.ACTIVE_TASK.value: {"ttl_sec": 604800, "max_entries": 50},                   # 7 days
    MemoryCategory.TASK_HISTORY.value: {"ttl_sec": 2592000, "max_entries": 100},                # 30 days
    MemoryCategory.PROJECT_CONTEXT.value: {"ttl_sec": None, "max_entries": 200},                # Indefinite
    MemoryCategory.USER_PREFERENCES.value: {"ttl_sec": None, "max_entries": 500},               # Indefinite
    MemoryCategory.VERIFIED_KNOWLEDGE.value: {"ttl_sec": None, "max_entries": 500},            # Indefinite
    MemoryCategory.GENERAL.value: {"ttl_sec": 2592000, "max_entries": 200},                     # 30 days
    # Legacy category aliases
    "project": {"ttl_sec": None, "max_entries": 200},
    "preferences": {"ttl_sec": None, "max_entries": 500},
    "conversation": {"ttl_sec": 86400, "max_entries": 100},
    "task": {"ttl_sec": 604800, "max_entries": 50},
}


class ContextMemory:
    """
    Transparent, user-controlled persistent memory store for Maven JARVIS.
    Stores project context, user preferences, past decisions, and environment details across
    canonical memory categories with bounded retention and automatic temporal decay ranking.
    Enforces strict credential scrubbing: NEVER stores passwords, API keys, or tokens.
    Persists locally in ~/.config/maverick/memory.json with 0600 permissions.
    """

    DEFAULT_STORE_PATH = os.path.expanduser("~/.config/maverick/memory.json")

    def __init__(self, store_path: Optional[str] = None, storage_dir: Optional[str] = None):
        if storage_dir:
            self.store_path = os.path.join(storage_dir, "memory.json")
        elif store_path:
            self.store_path = store_path
        else:
            self.store_path = self.DEFAULT_STORE_PATH
        self._lock = threading.Lock()
        self._ensure_storage()

    def _ensure_storage(self) -> None:
        """Ensure parent directory exists and file has restrictive permissions."""
        dir_name = os.path.dirname(self.store_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name, mode=0o700, exist_ok=True)
        if not os.path.isfile(self.store_path):
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "memories": {}}, f, indent=2)
            try:
                os.chmod(self.store_path, 0o600)
            except OSError:
                pass

    def _read_store(self) -> Dict[str, Any]:
        """Read data from storage file with corruption fallback."""
        if not os.path.isfile(self.store_path):
            return {"version": 2, "memories": {}}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "memories" in data:
                    return data
        except Exception:
            pass
        return {"version": 2, "memories": {}}

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

    def _normalize_category(self, cat: Union[MemoryCategory, str]) -> str:
        if isinstance(cat, MemoryCategory):
            return cat.value
        val = str(cat).strip().lower()
        return val if val else MemoryCategory.GENERAL.value

    def _enforce_retention(self, memories: Dict[str, Dict[str, Any]]) -> int:
        """Prune expired memories and enforce max entry bounds per category. Returns pruned count."""
        now = time.time()
        to_delete = []

        # 1. TTL expiration
        for mid, rec in memories.items():
            exp = rec.get("expires_at")
            if exp is not None and now >= exp:
                to_delete.append(mid)

        for mid in to_delete:
            del memories[mid]

        pruned = len(to_delete)

        # 2. Max entries per category (LRU based on updated_at)
        cat_map: Dict[str, List[Tuple[float, str]]] = {}
        for mid, rec in memories.items():
            c = rec.get("category", MemoryCategory.GENERAL.value)
            cat_map.setdefault(c, []).append((rec.get("updated_at", 0.0), mid))

        for c, entries in cat_map.items():
            policy = RETENTION_POLICIES.get(c, RETENTION_POLICIES[MemoryCategory.GENERAL.value])
            max_ent = policy.get("max_entries") or 200
            if len(entries) > max_ent:
                # Sort ascending by updated_at (oldest first)
                entries.sort(key=lambda x: x[0])
                excess = len(entries) - max_ent
                for _, mid in entries[:excess]:
                    if mid in memories:
                        del memories[mid]
                        pruned += 1

        return pruned

    def store(
        self,
        content: str,
        category: Union[MemoryCategory, str] = MemoryCategory.GENERAL,
        tags: Optional[List[str]] = None,
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Store a new piece of persistent memory.
        Strictly scrubs sensitive credentials, tokens, and keys before persisting.
        Calculates expiration timestamp according to category retention policy.
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty.")

        clean_content = redact_sensitive_text(content.strip())
        now = time.time()
        mem_id = self._generate_id(clean_content)
        norm_tags = [t.strip().lower() for t in (tags or []) if t.strip()]
        norm_cat = self._normalize_category(category)

        # Calculate TTL if applicable
        policy = RETENTION_POLICIES.get(norm_cat, RETENTION_POLICIES[MemoryCategory.GENERAL.value])
        ttl = policy.get("ttl_sec")
        expires_at = (now + ttl) if ttl is not None else None

        record = {
            "id": mem_id,
            "category": norm_cat,
            "content": clean_content,
            "tags": norm_tags,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "expires_at": expires_at,
            "access_count": 0,
            "metadata": metadata or {},
        }

        with self._lock:
            data = self._read_store()
            data["memories"][mem_id] = record
            self._enforce_retention(data["memories"])
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
        category: Optional[Union[MemoryCategory, str]] = None,
        limit: int = 5,
        min_score: float = 0.5,
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
        cat_filter = self._normalize_category(category) if category else None

        with self._lock:
            data = self._read_store()
            self._enforce_retention(data["memories"])
            memories = list(data["memories"].values())

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for mem in memories:
            if cat_filter and mem.get("category") != cat_filter:
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

            if final_score >= min_score:
                scored.append((final_score, dict(mem)))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, item in scored[:limit]:
            item["relevance_score"] = round(score, 3)
            results.append(item)

        return results

    def get_active_task(self) -> Optional[Dict[str, Any]]:
        """Retrieve current active task memory record."""
        tasks = self.list_all(category=MemoryCategory.ACTIVE_TASK, limit=1)
        return tasks[0] if tasks else None

    def get_preferences(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieve stored user preferences."""
        return self.list_all(category=MemoryCategory.USER_PREFERENCES, limit=limit)

    def get_project_context(self, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve context memories related to projects."""
        if project_name:
            return self.search(project_name, category=MemoryCategory.PROJECT_CONTEXT, limit=10)
        return self.list_all(category=MemoryCategory.PROJECT_CONTEXT, limit=20)

    def prune_expired(self) -> int:
        """Explicitly run retention policy pass. Returns number of purged records."""
        with self._lock:
            data = self._read_store()
            pruned = self._enforce_retention(data["memories"])
            if pruned > 0:
                self._write_store(data)
            return pruned

    def update(
        self,
        memory_id: str,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
            if metadata is not None:
                rec["metadata"] = metadata
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

    def clear_category(self, category: Union[MemoryCategory, str]) -> int:
        """Delete all memories in a given category. Returns count of deleted records."""
        cat_clean = self._normalize_category(category)
        with self._lock:
            data = self._read_store()
            initial = len(data["memories"])
            data["memories"] = {
                k: v for k, v in data["memories"].items()
                if v.get("category") != cat_clean
            }
            deleted = initial - len(data["memories"])
            if deleted > 0:
                self._write_store(data)
            return deleted

    def wipe_all(self, category: Optional[Union[MemoryCategory, str]] = None) -> int:
        """User-controlled complete wipe of all memory records or by category. Returns count deleted."""
        if category is not None:
            return self.clear_category(category)
        with self._lock:
            data = self._read_store()
            count = len(data.get("memories", {}))
            data["memories"] = {}
            self._write_store(data)
            return count

    def list_all(
        self,
        category: Optional[Union[MemoryCategory, str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List memories ordered by updated_at descending."""
        cat_filter = self._normalize_category(category) if category else None
        with self._lock:
            data = self._read_store()
            memories = list(data["memories"].values())

        if cat_filter:
            memories = [m for m in memories if m.get("category") == cat_filter]

        memories.sort(key=lambda m: m.get("updated_at", 0.0), reverse=True)
        return memories[:limit]

    def format_context_prompt(
        self,
        query: str,
        limit: int = 4,
        categories: Optional[List[Union[MemoryCategory, str]]] = None,
    ) -> str:
        """
        Format top-scoring memories as a concise context injection block
        for the AI model's system prompt.
        """
        matches: List[Dict[str, Any]] = []
        if categories:
            for cat in categories:
                matches.extend(self.search(query, category=cat, limit=limit))
            matches.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)
            matches = matches[:limit]
        else:
            matches = self.search(query, limit=limit)

        if not matches:
            return ""

        lines = ["Relevant Persistent Context & Preferences:"]
        for m in matches:
            cat = m.get("category", "general")
            content = m.get("content", "")
            lines.append(f"- [{cat.upper()}] {content}")

        return "\n".join(lines)
