import unittest
from unittest.mock import patch

from server.supabase_repository import SupabaseRepository


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class SupabaseRepositoryTests(unittest.TestCase):
    @patch("server.supabase_repository._MCP_ROLE_JWT", "test-role-jwt")
    @patch("server.supabase_repository._ANON_KEY", "test-anon-key")
    @patch("server.supabase_repository._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.supabase_repository.httpx.post")
    def test_key_context_uses_dedicated_rpc(self, post):
        post.return_value = _Response(
            [{"workspace_id": "workspace-1", "plan": "pro", "workspace_type": "personal"}]
        )

        repository = SupabaseRepository("pb_mcp_test")

        self.assertTrue(repository.key_is_valid())
        self.assertEqual(repository.plan, "pro")
        self.assertEqual(
            post.call_args.args[0],
            "https://example.supabase.co/rest/v1/rpc/get_mcp_key_context",
        )

    @patch("server.supabase_repository._MCP_ROLE_JWT", "test-role-jwt")
    @patch("server.supabase_repository._ANON_KEY", "test-anon-key")
    @patch("server.supabase_repository._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.supabase_repository.httpx.post")
    def test_list_skills_uses_key_bound_prompt_rpc(self, post):
        post.side_effect = [
            _Response(
                [{"workspace_id": "workspace-1", "plan": "free", "workspace_type": "personal"}]
            ),
            _Response([]),
        ]

        SupabaseRepository("pb_mcp_test").list_skills()

        prompt_call = post.call_args_list[1]
        self.assertEqual(
            prompt_call.args[0],
            "https://example.supabase.co/rest/v1/rpc/get_workspace_prompts_for_key",
        )
        self.assertEqual(prompt_call.kwargs["json"]["p_scope"], "private")
        self.assertIsNone(prompt_call.kwargs["json"]["p_workspace_id"])


if __name__ == "__main__":
    unittest.main()
