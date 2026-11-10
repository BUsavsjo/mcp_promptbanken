"""Analytics opt-out for our own test and verification traffic.

Contract checks, parity runs and live checks against /mcp used to land in
library_usage_events as if they were real users (the week of 2026-09-14
showed ~4x normal volume, and 29 of 44 "not found" lookups came from it).
A client can now send ``X-Promptbanken-Analytics: off`` to skip the
anonymous statistics event for that request. No secret is involved on
purpose: opting out of anonymous statistics is harmless, and a secret token
in a header would end up in the reverse proxy's access log.
"""

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import usage_events
from server.mcp_server import _mcp_streamable_http


def _mcp_request(body: dict, headers: list[tuple[bytes, bytes]]):
    from starlette.requests import Request as StarletteRequest

    raw = json.dumps(body).encode("utf-8")
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    return StarletteRequest(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"content-type", b"application/json"), *headers],
        },
        receive,
    )


_SEARCH_CALL = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "search_templates", "arguments": {"query": "mejl"}},
}


class AnalyticsOptOutHeaderTests(unittest.TestCase):
    def test_header_value_off_requests_opt_out(self) -> None:
        self.assertTrue(usage_events.analytics_opt_out_requested("off"))
        self.assertTrue(usage_events.analytics_opt_out_requested(" OFF "))

    def test_missing_or_other_header_value_does_not_opt_out(self) -> None:
        self.assertFalse(usage_events.analytics_opt_out_requested(None))
        self.assertFalse(usage_events.analytics_opt_out_requested(""))
        self.assertFalse(usage_events.analytics_opt_out_requested("on"))
        self.assertFalse(usage_events.analytics_opt_out_requested("0"))


class TrackUsageEventSuppressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.url_patch = patch.object(usage_events, "SUPABASE_URL", "https://example.test")
        self.key_patch = patch.object(usage_events, "SUPABASE_KEY", "anon-key")
        self.url_patch.start()
        self.key_patch.start()
        self.addCleanup(self.url_patch.stop)
        self.addCleanup(self.key_patch.stop)

    def test_event_is_sent_without_suppression(self) -> None:
        with patch.object(usage_events.httpx, "Client") as mocked_client:
            usage_events.track_usage_event(event_type="search")

        mocked_client.return_value.__enter__.return_value.post.assert_called_once()

    def test_event_is_not_sent_inside_suppression(self) -> None:
        with patch.object(usage_events.httpx, "Client") as mocked_client:
            with usage_events.suppress_usage_tracking():
                usage_events.track_usage_event(event_type="search")

        mocked_client.assert_not_called()

    def test_suppression_ends_when_context_exits(self) -> None:
        with patch.object(usage_events.httpx, "Client") as mocked_client:
            with usage_events.suppress_usage_tracking():
                pass
            usage_events.track_usage_event(event_type="search")

        mocked_client.return_value.__enter__.return_value.post.assert_called_once()


class McpRouteOptOutTests(unittest.TestCase):
    def _call(self, headers: list[tuple[bytes, bytes]]) -> MagicMock:
        captured = MagicMock()

        def fake_search(*args, **kwargs):
            usage_events.track_usage_event(event_type="search")
            return {"status": "success", "templates": []}

        with (
            patch.object(usage_events, "SUPABASE_URL", "https://example.test"),
            patch.object(usage_events, "SUPABASE_KEY", "anon-key"),
            patch.object(usage_events.httpx, "Client", captured),
            patch("server.mcp_server._search_templates_with_usage", side_effect=fake_search),
        ):
            response = asyncio.run(_mcp_streamable_http(_mcp_request(_SEARCH_CALL, headers)))

        self.assertEqual(response.status_code, 200)
        return captured

    def test_mcp_call_without_header_records_usage(self) -> None:
        captured = self._call([])
        captured.return_value.__enter__.return_value.post.assert_called_once()

    def test_mcp_call_with_opt_out_header_records_nothing(self) -> None:
        captured = self._call([(b"x-promptbanken-analytics", b"off")])
        captured.assert_not_called()


if __name__ == "__main__":
    unittest.main()
