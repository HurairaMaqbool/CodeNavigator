import unittest
import os
import sys
import time
import pytest

from app.agent.loop import run

def _run_with_retry(repo_id: str, question: str, max_attempts: int = 2) -> dict:
    """Helper for live API grounding tests to absorb transient Groq TPM rate limits gracefully."""
    for attempt in range(max_attempts):
        res = run(repo_id, question, job_id=repo_id)
        if not res.get("rate_limited") and not (res.get("gated") and "rate limit" in str(res.get("answer", "")).lower()):
            if res.get("gated") and ("groq api error" in str(res.get("answer", "")).lower() or "404" in str(res.get("answer", ""))):
                pytest.skip("Skipping live API test: Groq API key unavailable or invalid model access")
            return res
        if attempt + 1 < max_attempts:
            time.sleep(1.0)
    if res.get("gated") and ("groq api error" in str(res.get("answer", "")).lower() or "rate limit" in str(res.get("answer", "")).lower()):
        pytest.skip("Skipping live API test: Groq API rate-limited or key error")
    return res


@pytest.mark.live_api
class TestGroundingArchitecture(unittest.TestCase):
    """
    Test suite for the 4-Layer Grounding Architecture:
    1. Repo Scope Lock
    2. Lexical Grounding Check
    3. Semantic Similarity
    4. Confidence Scoring
    """
    
    @classmethod
    def setUpClass(cls):
        cls.repo_id = "5749924cb6a9850057686b664b4b980fc407af109104df6f0aec8ec8182a4338"
        
    def test_q1_authentication(self):
        res = _run_with_retry(self.repo_id, "How does authentication work in this app?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q2_hybrid_search(self):
        res = _run_with_retry(self.repo_id, "What calls the hybrid_search function, and what does it depend on?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q3_prompts_loading(self):
        res = _run_with_retry(self.repo_id, "How are the prompts loaded, and where do they come from?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q4_send_requests_gated(self):
        res = _run_with_retry(self.repo_id, "How does app/agent/llm_client.py send HTTP requests to the Groq API?")
        self.assertFalse(res.get("gated"))

    def test_q5_session_handling(self):
        res = _run_with_retry(self.repo_id, "How are session tokens created and decoded in app/auth/oidc.py?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q6_error_handling(self):
        res = _run_with_retry(self.repo_id, "How does this system handle errors and exceptions during a chat request?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q7_user_input_flow(self):
        res = _run_with_retry(self.repo_id, "Walk me through what happens from user input to final response, step by step.")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q8_caching_mechanism(self):
        res = _run_with_retry(self.repo_id, "What's the caching mechanism used here?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q9_httpproxyauth_gated(self):
        # Hallucination trap
        res = _run_with_retry(self.repo_id, "Is there any authentication class similar to HTTPProxyAuth in this app?")
        self.assertTrue(res.get("gated"))

    def test_q10_billing_stripe(self):
        # Stripe actually exists in the platform endpoints (app/api/billing_router.py)
        res = _run_with_retry(self.repo_id, "How is user billing and credit card processing implemented?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q11_gdpr_compliance(self):
        # GDPR compliance exists in platform_router.py
        res = _run_with_retry(self.repo_id, "How does the GDPR compliance module work?")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q12_oauth2_flow_gated(self):
        # OIDC/OAuth2 authentication exists in app/auth/oidc.py
        res = _run_with_retry(self.repo_id, "Show me the OAuth2 login flow implementation.")
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

if __name__ == "__main__":
    unittest.main()
