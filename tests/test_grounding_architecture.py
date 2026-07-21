import unittest
import os
import sys

from app.agent.loop import run

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
        res = run(self.repo_id, "How does authentication work in this app?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q2_hybrid_search(self):
        res = run(self.repo_id, "What calls the hybrid_search function, and what does it depend on?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q3_prompts_loading(self):
        res = run(self.repo_id, "How are the prompts loaded, and where do they come from?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q4_send_requests_gated(self):
        # Abstention due to lacking codebase evidence
        res = run(self.repo_id, "How does this app send requests?", job_id=self.repo_id)
        self.assertTrue(res.get("gated"))

    def test_q5_session_handling(self):
        res = run(self.repo_id, "Explain the session handling in this codebase.", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q6_error_handling(self):
        res = run(self.repo_id, "How does this system handle errors and exceptions during a chat request?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q7_user_input_flow(self):
        res = run(self.repo_id, "Walk me through what happens from user input to final response, step by step.", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q8_caching_mechanism(self):
        res = run(self.repo_id, "What's the caching mechanism used here?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q9_httpproxyauth_gated(self):
        # Hallucination trap
        res = run(self.repo_id, "Is there any authentication class similar to HTTPProxyAuth in this app?", job_id=self.repo_id)
        self.assertTrue(res.get("gated"))

    def test_q10_billing_stripe(self):
        # Stripe actually exists in the platform endpoints
        res = run(self.repo_id, "How is user billing and credit card processing implemented?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q11_gdpr_compliance(self):
        # GDPR compliance exists in platform_router.py
        res = run(self.repo_id, "How does the GDPR compliance module work?", job_id=self.repo_id)
        self.assertFalse(res.get("gated"))
        self.assertGreater(len(res.get("sources", [])), 0)

    def test_q12_oauth2_flow_gated(self):
        # Hallucination trap (we have OIDC/SAML, no direct OAuth2 symbol match)
        res = run(self.repo_id, "Show me the OAuth2 login flow implementation.", job_id=self.repo_id)
        self.assertTrue(res.get("gated"))

if __name__ == "__main__":
    unittest.main()
