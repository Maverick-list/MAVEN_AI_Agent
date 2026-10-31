# 06 — COMPUTER USE & AT-SPI ACCESSIBILITY SYNCHRONIZATION

## 1. Resolution of Multi-Threaded AT-SPI Heap Corruption

### The Defect
During concurrent desktop observation and test execution, PyGObject calls to `Atspi.get_desktop(0)` from multiple Python threads resulted in non-deterministic glibc heap aborts:
```
malloc(): unaligned tcache chunk detected
Fatal Python error: Aborted
```
This occurred because the underlying C library `libatspi` does not provide thread-safe re-entrant access to DBus cache registries across simultaneous caller threads.

### The Remediation
In `maverick/computer_use/accessibility.py`, a global re-entrant synchronization lock was introduced:
```python
_GLOBAL_ATSPI_LOCK = threading.RLock()
```
Every invocation into `Atspi` (`get_desktop()`, `get_child_at_index()`, `get_role_name()`, node attribute traversal) is wrapped in `with _GLOBAL_ATSPI_LOCK:`.
- **Result:** Multi-threaded stress tests with 10 concurrent observation threads executed 500 queries with 0 segmentation faults or memory corruption.

---

## 2. Dedicated Chrome Profile Isolation

To avoid session hijacking, cookie collisions, or corrupting the user's primary daily-driver Google Chrome browsing session:
- Maven's browser automation agent operates strictly out of an isolated profile:
  `~/.local/share/maverick/chrome-automation`
- Chrome flags enforced:
  `--remote-debugging-port=9222`
  `--user-data-dir=~/.local/share/maverick/chrome-automation`
  `--no-first-run --no-default-browser-check`
- Network isolation: CDP connects strictly to `127.0.0.1:9222`. Remote access or open interfaces are strictly blocked.
