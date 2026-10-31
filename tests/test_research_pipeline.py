"""Unit and integration tests for Research Assistant and Authorized Retrieval Pipeline.

Verifies:
- 8-stage research pipeline architecture
- Explicit question understanding and query decomposition
- Extensible provider interface (BrowserTabRetrievalProvider, AuthorizedHttpSearchProvider)
- SSRF prevention, private network IP rejection, scheme gating, domain allowlists
- Graceful unavailable-retrieval handling (no hallucinated mock research or canned data)
- Fact classification: retrieved_verified vs model_inference vs unverified_claim
- Structured citations generation
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from maverick.intelligence.toolkit.research import (
    AuthorizedHttpSearchProvider,
    BrowserTabRetrievalProvider,
    ResearchAssistant,
    ResearchFact,
    ResearchPlan,
    SourceDocument,
)


class TestResearchPipeline(unittest.TestCase):
    """Test suite for research pipeline and retrieval security."""

    def test_question_understanding_and_planning(self):
        """Verify query decomposition into intent, subtopics, and targeted search queries."""
        assistant = ResearchAssistant()
        plan = assistant.plan_research("How to configure Wayland display scale on Ubuntu 24.04")

        self.assertIsInstance(plan, ResearchPlan)
        self.assertEqual(plan.intent, "procedural_guide")
        self.assertGreaterEqual(len(plan.subtopics), 3)
        self.assertGreaterEqual(len(plan.search_queries), 2)
        self.assertIn("Wayland", " ".join(plan.subtopics) + " ".join(plan.search_queries))

        # Comparative intent
        plan_comp = assistant.plan_research("Compare X11 versus Wayland input latency")
        self.assertEqual(plan_comp.intent, "comparative_analysis")

        # Performance intent
        plan_perf = assistant.plan_research("Wayland screen capture benchmark fps")
        self.assertEqual(plan_perf.intent, "performance_evaluation")

    def test_no_provider_fallback_no_hallucinations(self):
        """Verify that when no retrieval provider is available, no fake facts are returned."""
        assistant = ResearchAssistant()  # No providers attached
        res = assistant.search_and_synthesize("Linux kernel eBPF observability")

        self.assertEqual(res["status"], "unavailable")
        self.assertFalse(res["retrieval_active"])
        self.assertEqual(res["sources_count"], 0)
        self.assertEqual(res["findings_count"], 0)
        self.assertEqual(res["sources"], [])
        self.assertEqual(res["verified_facts"], [])
        self.assertIn("LIVE RETRIEVAL UNAVAILABLE", res["executive_summary"])
        self.assertIn("No active retrieval provider is configured", res["executive_summary"])

    def test_ssrf_and_private_ip_rejection(self):
        """Verify AuthorizedHttpSearchProvider strictly rejects SSRF, loopback, and private IPs."""
        provider = AuthorizedHttpSearchProvider(
            api_endpoint="https://api.search.example.com",
            allowed_domains=["api.search.example.com"],
        )

        # Loopback / local hostnames
        safe, reason = provider.is_safe_url("http://localhost:8080/admin")
        self.assertFalse(safe)
        self.assertIn("Prohibited internal host", reason)

        safe, reason = provider.is_safe_url("http://127.0.0.1:8765/dashboard")
        self.assertFalse(safe)
        self.assertIn("Prohibited internal host", reason)

        # Prohibited schemes
        safe, reason = provider.is_safe_url("file:///etc/passwd")
        self.assertFalse(safe)
        self.assertIn("Prohibited URL scheme", reason)

        # Cloud metadata service IP
        safe, reason = provider.is_safe_url("http://169.254.169.254/latest/meta-data")
        self.assertFalse(safe)
        self.assertTrue("restricted IP" in reason or "allowlist" in reason or "Prohibited" in reason)

        # Domain not in allowlist
        safe, reason = provider.is_safe_url("https://malicious-site.com/search")
        self.assertFalse(safe)
        self.assertIn("not in authorized domain allowlist", reason)

    def test_browser_tab_retrieval_provider(self):
        """Verify BrowserTabRetrievalProvider extracts matching tab data and quotes."""
        mock_browser = MagicMock()
        mock_browser.list_tabs.return_value = [
            {
                "title": "Ubuntu Wayland Architecture Guide",
                "url": "https://wiki.ubuntu.com/Wayland",
                "content": "Wayland is a display server protocol that replaces X11. It provides direct client rendering.",
            },
            {
                "title": "Random Unrelated Tab",
                "url": "https://example.com/unrelated",
                "content": "Something else entirely.",
            },
        ]

        provider = BrowserTabRetrievalProvider(browser_client=mock_browser)
        self.assertTrue(provider.is_available())

        docs = provider.search("Wayland display protocol", max_results=3)
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc.title, "Ubuntu Wayland Architecture Guide")
        self.assertEqual(doc.publisher, "wiki.ubuntu.com")
        self.assertTrue(doc.is_verified)
        self.assertGreater(len(doc.extracted_quotes), 0)
        self.assertIn("Wayland", doc.extracted_quotes[0])

    def test_full_research_pipeline_with_browser_provider(self):
        """Verify full 8-stage pipeline with active provider produces verified facts and citations."""
        mock_browser = MagicMock()
        mock_browser.list_tabs.return_value = [
            {
                "title": "Python AsyncIO Internals",
                "url": "https://docs.python.org/3/library/asyncio.html",
                "content": "asyncio is a library to write concurrent code using the async/await syntax. It provides event loop management.",
            }
        ]

        assistant = ResearchAssistant(browser_client=mock_browser)
        res = assistant.search_and_synthesize("Python asyncio event loop syntax")

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["retrieval_active"])
        self.assertEqual(res["sources_count"], 1)
        self.assertGreater(len(res["verified_facts"]), 0)
        self.assertEqual(res["verified_facts"][0]["fact_type"], "retrieved_verified")
        self.assertIn("docs.python.org", res["verified_facts"][0]["source_url"])

        # Citations check
        self.assertEqual(len(res["citations"]), 1)
        citation = res["citations"][0]
        self.assertEqual(citation["citation_id"], "[1]")
        self.assertEqual(citation["title"], "Python AsyncIO Internals")
        self.assertEqual(citation["publisher"], "docs.python.org")

        # Inferences check
        self.assertGreaterEqual(len(res["model_inferences"]), 1)
        self.assertEqual(res["model_inferences"][0]["fact_type"], "model_inference")


if __name__ == "__main__":
    unittest.main()

