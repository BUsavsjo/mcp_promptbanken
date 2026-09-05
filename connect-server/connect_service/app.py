"""Den OAuth-skyddade MCP-ytan för Promptbanken Connect."""

from collections.abc import Mapping
import json
from typing import Protocol

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, object]:
        """Returnerar verifierade claims eller kastar ValueError."""


class Library(Protocol):
    """RLS-skyddad åtkomst till användarens Connect-innehåll."""

    def list_library(self, *, access_token: str, user_id: str) -> list[Mapping[str, object]]:
        """Listar privata Valvet-poster för användaren."""

    def list_shared_items(self, *, access_token: str) -> list[Mapping[str, object]]:
        """Listar synliga delade workspace-poster."""

    def get_item(self, *, access_token: str, item_id: str) -> Mapping[str, object] | None:
        """Hämtar en enda RLS-synlig post."""


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _unauthorized(resource_url: str) -> Response:
    return Response(
        status_code=401,
        headers={"WWW-Authenticate": f'Bearer resource="{resource_url}"'},
    )


def _tool_result(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }


def create_app(
    *,
    resource_url: str,
    authorization_server: str,
    token_verifier: TokenVerifier,
    library: Library,
) -> Starlette:
    """Skapar en fristående Connect-app med uttryckliga OAuth-beroenden."""

    async def protected_resource_metadata(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "resource": resource_url,
                "authorization_servers": [authorization_server],
            }
        )

    async def health_check(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "promptbanken-connect"})

    async def mcp(request: Request) -> Response:
        token = _bearer_token(request)
        if token is None:
            return _unauthorized(resource_url)

        try:
            claims = token_verifier.verify(token)
        except ValueError:
            return _unauthorized(resource_url)

        subject = claims.get("sub")
        if not subject:
            return _unauthorized(resource_url)

        payload = await request.json()
        request_id = payload.get("id")
        params = payload.get("params", {})
        if payload.get("method") == "initialize":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "promptbanken-connect", "version": "0.1.0"},
                    },
                }
            )

        if payload.get("method") == "tools/list":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "get_connect_context",
                                "description": "Bekräftar vem Connect är kopplad till.",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "list_my_library",
                                "description": "Listar dina egna aktiva prompts i Valvet.",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "list_shared_workspace_prompts",
                                "description": "Listar prompts i arbetsytor du är medlem i.",
                                "inputSchema": {"type": "object", "properties": {}},
                            },
                            {
                                "name": "get_connect_item",
                                "description": "Hämtar en prompt du har behörighet att läsa.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"item_id": {"type": "string"}},
                                    "required": ["item_id"],
                                },
                            },
                        ]
                    },
                }
            )

        if (
            payload.get("method") == "tools/call"
            and params.get("name") == "get_connect_context"
        ):
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"user_id": subject})})

        if payload.get("method") == "tools/call" and params.get("name") == "list_my_library":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result({"items": library.list_library(access_token=token, user_id=str(subject))}),
                }
            )

        if payload.get("method") == "tools/call" and params.get("name") == "list_shared_workspace_prompts":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result({"items": library.list_shared_items(access_token=token)}),
                }
            )

        if payload.get("method") == "tools/call" and params.get("name") == "get_connect_item":
            arguments = params.get("arguments", {})
            item_id = arguments.get("item_id") if isinstance(arguments, Mapping) else None
            if not isinstance(item_id, str):
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "item_id måste anges."}}
                )
            item = library.get_item(access_token=token, item_id=item_id)
            if item is None:
                return JSONResponse(
                    {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32004, "message": "Prompten finns inte eller är inte tillgänglig."}}
                )
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"item": item})})

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "MCP-metoden stöds inte ännu."},
            }
        )

    return Starlette(
        routes=[
            Route("/healthz", health_check),
            Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
            Route("/mcp", mcp, methods=["POST"]),
        ]
    )
