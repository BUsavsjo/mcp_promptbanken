import sys
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import admin_auth


class _TokenResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class AdminAuthTests(unittest.TestCase):
    def setUp(self):
        admin_auth._cached_access_token = None
        admin_auth._cached_expires_at = 0.0
        admin_auth._cached_refresh_token = None

    @patch("server.admin_auth._ANON_KEY", "test-anon-key")
    @patch("server.admin_auth._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_auth._REFRESH_TOKEN", "seed-refresh-token")
    @patch("server.admin_auth._persist_refresh_token")
    @patch("server.admin_auth.httpx.post")
    def test_get_access_token_exchanges_and_caches(self, post, persist):
        post.return_value = _TokenResponse(
            {"access_token": "at-1", "expires_in": 3600, "refresh_token": "rt-2"}
        )

        token = admin_auth.get_access_token()

        self.assertEqual(token, "at-1")
        self.assertEqual(post.call_count, 1)
        persist.assert_called_once_with("rt-2")

        # Second call within the cache window must NOT re-exchange.
        token_again = admin_auth.get_access_token()
        self.assertEqual(token_again, "at-1")
        self.assertEqual(post.call_count, 1)

    @patch("server.admin_auth._ANON_KEY", "test-anon-key")
    @patch("server.admin_auth._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_auth._REFRESH_TOKEN", "seed-refresh-token")
    @patch("server.admin_auth._persist_refresh_token")
    @patch("server.admin_auth.httpx.post")
    def test_get_access_token_refreshes_after_expiry_buffer(self, post, persist):
        post.side_effect = [
            _TokenResponse({"access_token": "at-1", "expires_in": 61, "refresh_token": "rt-2"}),
            _TokenResponse({"access_token": "at-2", "expires_in": 3600, "refresh_token": "rt-3"}),
        ]

        first = admin_auth.get_access_token()
        # Simulate time passing past the 60s expiry buffer without sleeping.
        admin_auth._cached_expires_at = time.monotonic() - 1
        second = admin_auth.get_access_token()

        self.assertEqual(first, "at-1")
        self.assertEqual(second, "at-2")
        self.assertEqual(post.call_count, 2)

    @patch("server.admin_auth._ANON_KEY", "")
    @patch("server.admin_auth._SUPABASE_URL", "")
    @patch("server.admin_auth._REFRESH_TOKEN", "")
    def test_get_access_token_raises_when_not_configured(self):
        with self.assertRaises(admin_auth.AdminAuthNotConfigured):
            admin_auth.get_access_token()

    @patch("server.admin_auth._REFRESH_TOKEN", "seed-from-env")
    def test_load_refresh_token_prefers_disk_over_env(self):
        # Create a temporary state file with a different token.
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as tmp:
            json.dump({"refresh_token": "disk-token"}, tmp)
            tmp_path = tmp.name

        try:
            with patch("server.admin_auth._STATE_PATH", Path(tmp_path)):
                token = admin_auth._load_refresh_token()
                self.assertEqual(token, "disk-token")
        finally:
            Path(tmp_path).unlink()

    @patch("server.admin_auth._ANON_KEY", "test-anon-key")
    @patch("server.admin_auth._SUPABASE_URL", "https://example.supabase.co")
    @patch("server.admin_auth._REFRESH_TOKEN", "seed-refresh-token")
    @patch("server.admin_auth._persist_refresh_token")
    @patch("server.admin_auth.httpx.post")
    def test_get_access_token_propagates_httpx_error(self, post, persist):
        # Simulate httpx.post raising an error (e.g. connection failure).
        post.side_effect = OSError("Connection failed")

        with self.assertRaises(OSError) as ctx:
            admin_auth.get_access_token()

        self.assertEqual(str(ctx.exception), "Connection failed")
        persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
