"""Maverick DevOS - Dynamic System Capabilities & Dependency Verifier.

Probes the host OS environment for available command-line binaries, desktop applications,
and runtime libraries. Prevents missing-binary exceptions and enables dynamic fallback
strategies across autonomous tools.
"""

from dataclasses import dataclass
import logging
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("maverick.core.dependencies")

# Standard desktop binaries and CLI utilities inspected by Maven
CORE_SYSTEM_BINARIES = [
    "code",
    "google-chrome",
    "firefox",
    "nautilus",
    "gnome-terminal",
    "libreoffice",
    "grim",
    "slurp",
    "xdg-open",
    "pdftotext",
    "tesseract",
    "pipewire",
    "pw-play",
    "paplay",
    "python3",
]


@dataclass
class BinaryCapability:
    """Capability descriptor for an inspected host binary."""
    name: str
    is_available: bool
    path: Optional[str] = None
    version: Optional[str] = None
    checked_at: float = 0.0


class SystemDependencyVerifier:
    """
    Dynamically audits and caches availability of system binaries and capabilities.
    """

    _instance: Optional["SystemDependencyVerifier"] = None

    def __init__(self, cache_ttl_seconds: float = 60.0):
        self.cache_ttl = cache_ttl_seconds
        self._cache: Dict[str, BinaryCapability] = {}

    @classmethod
    def get_instance(cls) -> "SystemDependencyVerifier":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def has_binary(self, binary_name: str) -> bool:
        """Check if a binary is present in system PATH."""
        cap = self.inspect_binary(binary_name)
        return cap.is_available

    def get_path(self, binary_name: str) -> Optional[str]:
        """Return absolute path to binary if available."""
        cap = self.inspect_binary(binary_name)
        return cap.path

    def inspect_binary(self, binary_name: str, force_refresh: bool = False) -> BinaryCapability:
        """Query availability and version with TTL caching."""
        now = time.time()
        if not force_refresh and binary_name in self._cache:
            cap = self._cache[binary_name]
            if now - cap.checked_at < self.cache_ttl:
                return cap

        path = shutil.which(binary_name)
        is_available = path is not None
        version = None

        if is_available and path:
            # Query version safely with short timeout
            try:
                proc = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                )
                if proc.returncode == 0:
                    raw_ver = proc.stdout.strip().split("\n")[0]
                    version = raw_ver[:60]
            except Exception:
                version = "installed"

        cap = BinaryCapability(
            name=binary_name,
            is_available=is_available,
            path=path,
            version=version,
            checked_at=now,
        )
        self._cache[binary_name] = cap
        return cap

    def audit_environment(self) -> Dict[str, Any]:
        """Run audit across all known core desktop binaries."""
        results = {}
        for b in CORE_SYSTEM_BINARIES:
            cap = self.inspect_binary(b)
            results[b] = {
                "available": cap.is_available,
                "path": cap.path,
                "version": cap.version,
            }
        return {
            "timestamp": time.time(),
            "capabilities": results,
            "total_probed": len(results),
            "available_count": sum(1 for v in results.values() if v["available"]),
        }


def has_dependency(name: str) -> bool:
    """Convenience module helper."""
    return SystemDependencyVerifier.get_instance().has_binary(name)


def get_dependency_path(name: str) -> Optional[str]:
    """Convenience module helper."""
    return SystemDependencyVerifier.get_instance().get_path(name)
