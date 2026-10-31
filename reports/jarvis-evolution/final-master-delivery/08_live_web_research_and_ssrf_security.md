# 08 — LIVE WEB RESEARCH & SSRF SECURITY

## 1. Zero-Key Multi-Source Retrieval Pipeline

`ResearchAssistant` delivers factual, cited external intelligence without requiring third-party search API subscription keys:
1. **Public Live Multi-Source Retrieval:**
   - Queries Wikipedia OpenSearch API for title matches and disambiguation.
   - Retrieves authoritative summaries via Wikimedia REST API (`/api/rest_v1/page/summary/{title}`).
   - Cross-references across query dimensions (background, state-of-the-art, performance benchmarks).
2. **Structured Synthesis Output:**
   - Yields executive summary, key findings, source documents, credibility ratings (0.0 to 1.0), and timestamped citation links.

---

## 2. Server-Side Request Forgery (SSRF) Defense

Because research agents fetch remote URLs, strict URL validation was implemented in `AuthorizedHttpSearchProvider.is_safe_url()`:
- **Scheme Restriction:** Only `http` and `https` allowed.
- **DNS Resolution Guard:** Resolves hostname to physical IP addresses via `socket.getaddrinfo()`.
- **Private & Loopback Filtering:**
  - `127.0.0.0/8` (Loopback) -> BLOCKED
  - `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (RFC 1918 Private) -> BLOCKED
  - `169.254.0.0/16` (Link-local / Cloud Metadata) -> BLOCKED
  - `::1`, `fc00::/7`, `fe80::/10` (IPv6 Local) -> BLOCKED
- Verified in `tests/test_research_pipeline.py`: Rejections verified against `http://127.0.0.1:8765`, `http://169.254.169.254/latest/meta-data`, and private LAN addresses.
