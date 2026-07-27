import unittest
from unittest.mock import patch

from server import vault


class _NoContentResponse:
    status_code = 204

    def raise_for_status(self):
        return None

    def json(self):
        raise ValueError("204 responses have no JSON body")


class VaultTests(unittest.TestCase):
    @patch("server.vault._ANON_KEY", "test-anon-key")
    @patch("server.vault._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.vault.httpx.post", return_value=_NoContentResponse())
    def test_package_mutations_accept_no_content_response(self, post):
        vault.activate_package("pb_mcp_test", "kommunikation")
        vault.deactivate_package("pb_mcp_test", "kommunikation")

        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
