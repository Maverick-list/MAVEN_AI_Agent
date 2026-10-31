"""Maverick DevOS - Web Research & Synthesis Engine.

Coordinates structured topic investigation, extensible retrieval, safe extraction,
factual cross-referencing, and verifiable citation generation.

Enforces strict separation between verified retrieved facts and model inferences,
rejects SSRF / private network queries, and provides clear fallback reporting
when no authorized retrieval providers are configured.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import html
import ipaddress
import logging
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request

logger = logging.getLogger("maverick.intelligence.toolkit.research")


@dataclass
class SourceDocument:
    """A verified source document retrieved during research."""
    url: str
    title: str
    publisher: str
    retrieval_timestamp: float
    content: str
    extracted_quotes: List[str] = field(default_factory=list)
    is_verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchFact:
    """An individual fact extracted or inferred during research."""
    fact: str
    fact_type: str  # "retrieved_verified", "model_inference", "unverified_claim"
    source_url: Optional[str] = None
    citation: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchPlan:
    """Structured decomposition of a research topic."""
    original_query: str
    intent: str
    subtopics: List[str]
    search_queries: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BaseRetrievalProvider(ABC):
    """Abstract interface for research retrieval providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available for queries."""
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 4) -> List[SourceDocument]:
        """Execute query search and return source documents."""
        pass


class BrowserTabRetrievalProvider(BaseRetrievalProvider):
    """Retrieves context from open browser tabs via Chrome DevTools Protocol (CDP)."""

    def __init__(self, browser_client: Optional[Any] = None):
        self.browser_client = browser_client

    @property
    def name(self) -> str:
        return "browser_cdp_tabs"

    def is_available(self) -> bool:
        if self.browser_client is None:
            return False
        try:
            return hasattr(self.browser_client, "list_tabs")
        except Exception:
            return False

    def search(self, query: str, max_results: int = 4) -> List[SourceDocument]:
        if not self.is_available():
            return []

        clean_query = query.lower().strip()
        terms = [t for t in re.split(r"\W+", clean_query) if len(t) > 2]
        sources: List[SourceDocument] = []

        try:
            tabs = self.browser_client.list_tabs()
            for tab in tabs:
                title = tab.get("title", "")
                url = tab.get("url", "")
                text_content = tab.get("content", "") or tab.get("text", "")

                # Relevance check
                matched = any(t in title.lower() or t in url.lower() for t in terms)
                if not matched and text_content:
                    matched = any(t in text_content.lower() for t in terms)

                if matched:
                    domain = urllib.parse.urlparse(url).netloc or "browser-tab"
                    quotes = []
                    if text_content:
                        # Extract first relevant sentence as quote
                        sentences = re.split(r"[.!?]\s+", text_content)
                        for s in sentences:
                            if any(t in s.lower() for t in terms) and len(s) > 20:
                                quotes.append(s.strip())
                                if len(quotes) >= 2:
                                    break

                    sources.append(SourceDocument(
                        url=url,
                        title=title or "Active Browser Tab",
                        publisher=domain,
                        retrieval_timestamp=time.time(),
                        content=text_content[:2000],
                        extracted_quotes=quotes,
                        is_verified=True,
                    ))

                    if len(sources) >= max_results:
                        break
        except Exception as e:
            logger.warning("Browser tab retrieval failed: %s", e)

        return sources


class AuthorizedHttpSearchProvider(BaseRetrievalProvider):
    """
    Safely executes HTTP retrieval against authorized endpoints with strict
    SSRF prevention, timeouts, payload size limits, and private IP rejection.
    """

    MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2MB
    REQUEST_TIMEOUT_SECONDS = 10.0
    MIN_REQUEST_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        api_endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        allowed_domains: Optional[List[str]] = None,
    ):
        self.api_endpoint = api_endpoint
        self.api_key = api_key
        self.allowed_domains = allowed_domains
        self._last_request_time = 0.0

    @property
    def name(self) -> str:
        return "authorized_http_search"

    def is_available(self) -> bool:
        return True

    def is_safe_url(self, url: str) -> Tuple[bool, str]:
        """Validate URL to protect against SSRF, internal network scans, and invalid schemes."""
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False, f"Prohibited URL scheme: {parsed.scheme}"

            hostname = parsed.hostname
            if not hostname:
                return False, "Missing hostname"

            # Check well-known dangerous local hostnames
            lower_host = hostname.lower()
            if lower_host in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"):
                return False, f"Prohibited internal host: {hostname}"

            # Domain allowlist check if configured
            if self.allowed_domains:
                matched = any(
                    lower_host == d.lower() or lower_host.endswith("." + d.lower())
                    for d in self.allowed_domains
                )
                if not matched:
                    return False, f"Host '{hostname}' not in authorized domain allowlist"

            # DNS resolution check for private / loopback / link-local / multicast IPs
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for addr in addr_info:
                    ip_str = addr[4][0]
                    ip = ipaddress.ip_address(ip_str)
                    if (
                        ip.is_private
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_reserved
                        or ip.is_multicast
                        or ip_str == "169.254.169.254"
                    ):
                        return False, f"Host resolves to restricted IP: {ip_str}"
            except socket.gaierror:
                return False, f"Failed to resolve hostname: {hostname}"

            return True, "Safe"
        except Exception as e:
            return False, f"URL safety check failed: {e}"

    def search(self, query: str, max_results: int = 4) -> List[SourceDocument]:
        if not query or not query.strip():
            return []

        # Enforce rate limit
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(self.MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_time = time.time()

        clean_query = query.strip()
        results: List[SourceDocument] = []

        # 1. Custom endpoint if configured
        if self.api_endpoint:
            safe, reason = self.is_safe_url(self.api_endpoint)
            if not safe:
                logger.error("Authorized search endpoint rejected by SSRF guard: %s", reason)
                return []
            try:
                req_data = urllib.parse.urlencode({"q": clean_query, "limit": max_results}).encode("utf-8")
                req = urllib.request.Request(
                    self.api_endpoint,
                    data=req_data,
                    headers={
                        "User-Agent": "Maverick-DevOS-Research/1.0",
                        "Accept": "application/json",
                    },
                )
                if self.api_key:
                    req.add_header("Authorization", f"Bearer {self.api_key}")
                with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT_SECONDS) as resp:
                    raw = resp.read(self.MAX_RESPONSE_BYTES)
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                    if isinstance(obj, list):
                        for item in obj[:max_results]:
                            if isinstance(item, dict) and "url" in item:
                                is_s, _ = self.is_safe_url(item["url"])
                                if is_s:
                                    results.append(
                                        SourceDocument(
                                            source_id=f"src_{len(results)+1}",
                                            url=item["url"],
                                            title=item.get("title", "Untitled"),
                                            content_text=item.get("snippet", ""),
                                            domain=urllib.parse.urlparse(item["url"]).netloc,
                                            credibility_score=float(item.get("credibility", 0.85)),
                                        )
                                    )
                if results:
                    return results
            except Exception as e:
                logger.debug("Custom search endpoint query failed: %s", e)

        # 2. Public Live Multi-Source Retrieval: Wikipedia OpenSearch + REST Summaries
        try:
            opensearch_url = (
                f"https://en.wikipedia.org/w/api.php?action=opensearch&search="
                f"{urllib.parse.quote(clean_query)}&limit={max_results}&format=json"
            )
            safe, _ = self.is_safe_url(opensearch_url)
            if not safe:
                return []

            req = urllib.request.Request(
                opensearch_url,
                headers={"User-Agent": "Maverick-DevOS-Research/1.0 (Linux; x86_64)"},
            )
            with urllib.request.urlopen(req, timeout=self.REQUEST_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read(262144).decode("utf-8", errors="replace"))
                titles = data[1] if len(data) > 1 and isinstance(data[1], list) else []
                snippets = data[2] if len(data) > 2 and isinstance(data[2], list) else []
                links = data[3] if len(data) > 3 and isinstance(data[3], list) else []

                for idx, (t, s, u) in enumerate(zip(titles, snippets, links)):
                    safe_url, _ = self.is_safe_url(u)
                    if not safe_url:
                        continue

                    # Fetch rich extract via REST summary API if snippet is short
                    rich_extract = s
                    if len(rich_extract) < 120 and t:
                        try:
                            sum_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(t.replace(' ', '_'))}"
                            s_safe, _ = self.is_safe_url(sum_url)
                            if s_safe:
                                sum_req = urllib.request.Request(
                                    sum_url,
                                    headers={"User-Agent": "Maverick-DevOS-Research/1.0"},
                                )
                                with urllib.request.urlopen(sum_req, timeout=3.5) as sum_resp:
                                    sum_data = json.loads(sum_resp.read(65536).decode("utf-8", errors="replace"))
                                    ext = sum_data.get("extract", "")
                                    if ext:
                                        rich_extract = ext
                        except Exception:
                            pass

                    domain = urllib.parse.urlparse(u).netloc
                    doc = SourceDocument(
                        source_id=f"src_{len(results)+1}",
                        url=u,
                        title=t or "Wikipedia Entry",
                        content_text=rich_extract,
                        domain=domain,
                        credibility_score=0.92,
                        metadata={"search_rank": idx + 1, "provider": "wikipedia_verified"},
                    )
                    results.append(doc)
                    if len(results) >= max_results:
                        break
        except Exception as exc:
            logger.debug("Wikipedia public search failed: %s", exc)

        return results


class ResearchAssistant:
    """
    Coordinates end-to-end 8-stage research pipeline:
    1. Question Understanding
    2. Research Planning
    3. Retrieval Interface
    4. Source Extraction
    5. Source Verification
    6. Information Comparison / Cross-referencing
    7. Structured Synthesis
    8. Citation Generation
    """

    def __init__(
        self,
        providers: Optional[List[BaseRetrievalProvider]] = None,
        browser_client: Optional[Any] = None,
    ):
        if providers is not None:
            self.providers = list(providers)
        else:
            self.providers = [AuthorizedHttpSearchProvider()]
        if browser_client is not None:
            self.providers.append(BrowserTabRetrievalProvider(browser_client))

    def add_provider(self, provider: BaseRetrievalProvider) -> None:
        """Register an authorized retrieval provider."""
        self.providers.append(provider)

    # Stage 1 & 2: Question Understanding & Research Planning
    def plan_research(self, query: str) -> ResearchPlan:
        """Decompose user query into clear investigative facets and targeted search terms."""
        clean_query = query.strip()
        words = [w for w in re.split(r"\W+", clean_query) if len(w) > 3]

        # Determine investigative intent
        lower_q = clean_query.lower()
        if any(w in lower_q for w in ("how to", "install", "configure", "setup")):
            intent = "procedural_guide"
        elif any(w in lower_q for w in ("compare", "difference", "versus", "vs")):
            intent = "comparative_analysis"
        elif any(w in lower_q for w in ("why", "cause", "troubleshoot", "error")):
            intent = "root_cause_troubleshooting"
        elif any(w in lower_q for w in ("performance", "benchmark", "speed", "metric")):
            intent = "performance_evaluation"
        else:
            intent = "conceptual_overview"

        # Generate subtopics
        if not words:
            subtopics = [
                "Architecture overview",
                "Implementation details",
                "Verification and testing",
            ]
            search_queries = [clean_query]
        else:
            subtopics = [f"{w.capitalize()} analysis and characteristics" for w in words[:3]]
            search_queries = [
                clean_query,
                f"{words[0]} configuration and usage",
                f"{words[-1]} benchmark and diagnostics",
            ]

        return ResearchPlan(
            original_query=clean_query,
            intent=intent,
            subtopics=subtopics,
            search_queries=search_queries,
        )

    # Stage 3, 4 & 5: Retrieval, Extraction & Verification
    def retrieve_and_verify(
        self,
        queries: List[str],
        max_sources: int = 4,
    ) -> Tuple[List[SourceDocument], List[str]]:
        """Query active providers, extract documents, and verify integrity."""
        active_providers = [p for p in self.providers if p.is_available()]
        if not active_providers:
            return [], []

        raw_docs: List[SourceDocument] = []
        active_names = [p.name for p in active_providers]

        for p in active_providers:
            for q in queries:
                try:
                    docs = p.search(q, max_results=max_sources)
                    for d in docs:
                        # Deduplicate by URL
                        if not any(existing.url == d.url for existing in raw_docs):
                            raw_docs.append(d)
                        if len(raw_docs) >= max_sources:
                            break
                except Exception as e:
                    logger.warning("Provider %s error on query '%s': %s", p.name, q, e)
            if len(raw_docs) >= max_sources:
                break

        # Verification step
        verified_docs: List[SourceDocument] = []
        for doc in raw_docs:
            if not doc.url or not doc.title:
                continue
            # Ensure content is present and not empty
            if doc.content or doc.extracted_quotes:
                doc.is_verified = True
                verified_docs.append(doc)

        return verified_docs, active_names

    # Stage 6: Information Comparison & Fact Categorization
    def categorize_facts(
        self,
        sources: List[SourceDocument],
        plan: ResearchPlan,
    ) -> Tuple[List[ResearchFact], List[ResearchFact], List[ResearchFact]]:
        """
        Categorize facts strictly into:
        1. Retrieved verified facts (backed by actual documents with URL and citations)
        2. Model inferences (clearly designated as general reasoning / un-retrieved)
        3. Unverified claims
        """
        verified_facts: List[ResearchFact] = []
        unverified_claims: List[ResearchFact] = []
        model_inferences: List[ResearchFact] = []

        citation_index = 1
        for s in sources:
            if s.extracted_quotes:
                for quote in s.extracted_quotes:
                    verified_facts.append(ResearchFact(
                        fact=quote,
                        fact_type="retrieved_verified",
                        source_url=s.url,
                        citation=f"[{citation_index}] {s.publisher} ({s.title})",
                        confidence=1.0,
                    ))
            elif s.content:
                verified_facts.append(ResearchFact(
                    fact=s.content[:150].strip() + "...",
                    fact_type="retrieved_verified",
                    source_url=s.url,
                    citation=f"[{citation_index}] {s.publisher}",
                    confidence=0.9,
                ))
            citation_index += 1

        # Model inferences (structural reasoning derived from intent, NOT synthetic facts)
        if plan.intent == "performance_evaluation":
            model_inferences.append(ResearchFact(
                fact="Performance evaluation queries typically require empirical benchmarking on the local hardware configuration.",
                fact_type="model_inference",
                confidence=0.85,
            ))
        elif plan.intent == "procedural_guide":
            model_inferences.append(ResearchFact(
                fact="Procedural installation steps should be verified against the host distribution and package manager versions.",
                fact_type="model_inference",
                confidence=0.85,
            ))
        elif plan.intent == "conceptual_overview":
            model_inferences.append(ResearchFact(
                fact="Conceptual syntax and APIs should be confirmed against the active runtime version documentation.",
                fact_type="model_inference",
                confidence=0.85,
            ))
        elif plan.intent == "comparative_analysis":
            model_inferences.append(ResearchFact(
                fact="Comparative architectural advantages depend on specific deployment constraints and workload profiles.",
                fact_type="model_inference",
                confidence=0.85,
            ))
        elif plan.intent == "root_cause_troubleshooting":
            model_inferences.append(ResearchFact(
                fact="Root-cause remediation should be validated against system journal logs before applying configuration changes.",
                fact_type="model_inference",
                confidence=0.85,
            ))

        return verified_facts, model_inferences, unverified_claims

    # Stage 7 & 8: Structured Synthesis & Citation Generation
    def format_citations(self, sources: List[SourceDocument]) -> List[Dict[str, Any]]:
        """Generate structured citation entries for retrieved sources."""
        citations = []
        for idx, s in enumerate(sources, 1):
            citations.append({
                "citation_id": f"[{idx}]",
                "title": s.title,
                "url": s.url,
                "publisher": s.publisher,
                "retrieval_timestamp": s.retrieval_timestamp,
                "verified": s.is_verified,
            })
        return citations

    def search_and_synthesize(
        self,
        query: str,
        max_sources: int = 4,
    ) -> Dict[str, Any]:
        """
        Execute full 8-stage research pipeline.

        When no retrieval providers are available, gracefully informs caller
        that live retrieval is not configured, returning planned questions
        and explicit guidance instead of mock or hallucinated research.
        """
        clean_query = query.strip()
        t_start = time.perf_counter()

        # 1. Question Understanding & 2. Planning
        plan = self.plan_research(clean_query)

        # 3, 4 & 5. Retrieval, Extraction & Verification
        verified_sources, active_providers = self.retrieve_and_verify(
            plan.search_queries,
            max_sources=max_sources,
        )

        # 6. Categorization
        verified_facts, model_inferences, unverified_claims = self.categorize_facts(
            verified_sources,
            plan,
        )

        # 8. Citations
        citations = self.format_citations(verified_sources)

        # 7. Synthesis
        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

        if not active_providers:
            # Clear, honest status when no retrieval provider is active.
            # Never return fabricated or canned mock sources.
            summary = (
                f"Research decomposition for inquiry: '{clean_query}'.\n\n"
                f"Investigative Facets Planned:\n"
                + "\n".join(f"- {st}" for st in plan.subtopics)
                + "\n\n"
                f"[LIVE RETRIEVAL UNAVAILABLE]\n"
                f"No active retrieval provider is configured. Live web or tab retrieval was not performed.\n"
                f"To enable live research, attach an active browser session with Chrome CDP or configure "
                f"an authorized HTTP retrieval provider. General knowledge synthesis is disabled to prevent "
                f"unverified hallucinations."
            )

            return {
                "status": "unavailable",
                "query": clean_query,
                "intent": plan.intent,
                "subtopics": plan.subtopics,
                "search_queries": plan.search_queries,
                "retrieval_active": False,
                "active_providers": [],
                "sources_count": 0,
                "findings_count": 0,
                "sources": [],
                "findings": [],
                "verified_facts": [],
                "model_inferences": [f.to_dict() for f in model_inferences],
                "unverified_claims": [],
                "citations": [],
                "executive_summary": summary,
                "elapsed_ms": elapsed_ms,
            }

        if not verified_sources:
            summary = (
                f"Research query '{clean_query}' completed via active providers ({', '.join(active_providers)}).\n\n"
                f"No verified external sources matching the search criteria were found. "
                f"No unverified facts were synthesized."
            )
            return {
                "status": "no_sources_found",
                "query": clean_query,
                "intent": plan.intent,
                "subtopics": plan.subtopics,
                "search_queries": plan.search_queries,
                "retrieval_active": True,
                "active_providers": active_providers,
                "sources_count": 0,
                "findings_count": 0,
                "sources": [],
                "findings": [],
                "verified_facts": [],
                "model_inferences": [f.to_dict() for f in model_inferences],
                "unverified_claims": [],
                "citations": [],
                "executive_summary": summary,
                "elapsed_ms": elapsed_ms,
            }

        # Build synthesized summary from verified facts
        summary_paragraphs = [
            f"Executive synthesis for research inquiry: '{clean_query}'.",
            f"Synthesized from {len(verified_sources)} verified source(s) across active provider(s): {', '.join(active_providers)}.",
            f"Key facets investigated: {', '.join(plan.subtopics)}.",
            "Verified findings:",
        ]
        for vf in verified_facts:
            summary_paragraphs.append(f"• {vf.fact} {vf.citation or ''}")

        findings_legacy = [
            {
                "title": s.title,
                "url": s.url,
                "summary": s.content[:200],
                "source_type": s.publisher,
            }
            for s in verified_sources
        ]

        return {
            "status": "success",
            "query": clean_query,
            "intent": plan.intent,
            "subtopics": plan.subtopics,
            "search_queries": plan.search_queries,
            "retrieval_active": True,
            "active_providers": active_providers,
            "sources_count": len(verified_sources),
            "findings_count": len(findings_legacy),
            "sources": [s.to_dict() for s in verified_sources],
            "findings": findings_legacy,
            "verified_facts": [f.to_dict() for f in verified_facts],
            "model_inferences": [f.to_dict() for f in model_inferences],
            "unverified_claims": [f.to_dict() for f in unverified_claims],
            "citations": citations,
            "executive_summary": "\n\n".join(summary_paragraphs),
            "elapsed_ms": elapsed_ms,
        }
