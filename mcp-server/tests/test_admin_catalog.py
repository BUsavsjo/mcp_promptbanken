import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import admin_catalog


class _JsonResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class AdminCatalogTests(unittest.TestCase):
    def setUp(self):
        admin_catalog._recent_calls.clear()

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_create_prompt_calls_rpc_and_logs_success(self, post, get_token):
        post.side_effect = [
            _JsonResponse({"id": "prompt-1", "slug": "test-slug"}),
            _JsonResponse(None, status_code=204),
        ]

        result = admin_catalog.create_prompt("test-slug", "Title", "Summary", "Prompt text")

        self.assertEqual(result["id"], "prompt-1")
        self.assertEqual(post.call_count, 2)
        first_call_url = post.call_args_list[0].args[0]
        second_call_url = post.call_args_list[1].args[0]
        self.assertIn("/rpc/create_catalog_prompt", first_call_url)
        self.assertIn("/rpc/log_admin_write_attempt", second_call_url)
        second_call_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(second_call_payload["p_outcome"], "success")

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_create_prompt_logs_rejection_and_reraises(self, post, get_token):
        failure = RuntimeError("RPC rejected")
        post.side_effect = [failure, _JsonResponse(None, status_code=204)]

        with self.assertRaises(RuntimeError):
            admin_catalog.create_prompt("test-slug", "Title", "Summary", "Prompt text")

        self.assertEqual(post.call_count, 2)
        second_call_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(second_call_payload["p_outcome"], "rejected")

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_upsert_package_variant_calls_rpc(self, post, get_token):
        post.side_effect = [
            _JsonResponse({"package_id": "pkg-1", "context_key": "generell"}),
            _JsonResponse(None, status_code=204),
        ]

        result = admin_catalog.upsert_package_variant(
            "pkg-1", "generell", "Title", "Summary", problem_text="Problem"
        )

        self.assertEqual(result["package_id"], "pkg-1")
        first_call_url = post.call_args_list[0].args[0]
        self.assertIn("/rpc/upsert_catalog_package_variant", first_call_url)
        first_call_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(first_call_payload["p_problem_text"], "Problem")

    @patch("server.admin_catalog._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_catalog._ANON_KEY", "test-anon-key")
    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_upsert_package_metadata_calls_rpc(self, post, get_token):
        post.side_effect = [
            _JsonResponse({"id": "pkg-1", "area": "arbetsbank"}),
            _JsonResponse(None, status_code=204),
        ]

        result = admin_catalog.upsert_package_metadata("pkg-1", area="arbetsbank", tags=["a", "b"])

        self.assertEqual(result["area"], "arbetsbank")
        first_call_url = post.call_args_list[0].args[0]
        self.assertIn("/rpc/upsert_catalog_package_metadata", first_call_url)
        first_call_payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(first_call_payload["p_tags"], ["a", "b"])
        self.assertEqual(first_call_payload["p_is_indexable_provided"], False)

    def test_publish_prompt_requires_explicit_confirm(self):
        with self.assertRaises(ValueError):
            admin_catalog.publish_prompt("prompt-1", confirm=False)

    @patch("server.admin_catalog.admin_auth.get_access_token", return_value="at-1")
    @patch("server.admin_catalog.httpx.post")
    def test_rate_limit_blocks_after_max_calls(self, post, get_token):
        post.return_value = _JsonResponse(None, status_code=204)
        for _ in range(admin_catalog._RATE_LIMIT_MAX_CALLS):
            admin_catalog._check_rate_limit()

        with self.assertRaises(admin_catalog.AdminRateLimitExceeded):
            admin_catalog._check_rate_limit()


if __name__ == "__main__":
    unittest.main()
