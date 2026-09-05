"""Den OAuth-skyddade MCP-ytan för Promptbanken Connect."""

from collections.abc import Mapping
import json
from typing import Protocol
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, object]:
        """Returnerar verifierade claims eller kastar ValueError."""


class Library(Protocol):
    """RLS-skyddad åtkomst till den inloggade användarens Creator-bibliotek."""

    def list_library(self, *, access_token: str, kind: str, limit: int) -> list[Mapping[str, object]]: ...

    def get_library_prompt(self, *, access_token: str, prompt_id: str) -> Mapping[str, object] | None: ...

    def list_packages(self, *, access_token: str, limit: int) -> list[Mapping[str, object]]: ...

    def get_package(self, *, access_token: str, package_id: str) -> Mapping[str, object] | None: ...

    def list_shares(self, *, access_token: str, include_inactive: bool) -> list[Mapping[str, object]]: ...


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _unauthorized(resource_url: str) -> Response:
    return Response(status_code=401, headers={"WWW-Authenticate": f'Bearer resource="{resource_url}"'})


def _tool_result(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "structuredContent": payload,
    }


def _error(request_id: object, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _valid_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _arguments(params: object) -> Mapping[str, object] | None:
    if not isinstance(params, Mapping):
        return None
    arguments = params.get("arguments", {})
    return arguments if isinstance(arguments, Mapping) else None


def _limit(arguments: Mapping[str, object]) -> int | None:
    value = arguments.get("limit", 50)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        return None
    return value


def _tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "name": "get_connect_context",
            "description": "Bekräftar vem Connect är kopplad till.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "list_my_library",
            "description": "Listar dina Creator-prompter, sparade biblioteksposter och paket utan prompttext.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["all", "prompt", "package"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
        {
            "name": "get_my_library_prompt",
            "description": "Hämtar hela innehållet i en prompt du har i ditt eget bibliotek.",
            "inputSchema": {
                "type": "object",
                "properties": {"prompt_id": {"type": "string", "format": "uuid"}},
                "required": ["prompt_id"],
            },
        },
        {
            "name": "list_my_packages",
            "description": "Listar dina Creator-paket utan att läsa ut prompttexterna.",
            "inputSchema": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            },
        },
        {
            "name": "get_my_package",
            "description": "Hämtar ett eget paket och dess prompts i sparad ordning.",
            "inputSchema": {
                "type": "object",
                "properties": {"package_id": {"type": "string", "format": "uuid"}},
                "required": ["package_id"],
            },
        },
        {
            "name": "list_my_shares",
            "description": "Listar dina aktiva delningar, eller även avslutade när du ber om det.",
            "inputSchema": {
                "type": "object",
                "properties": {"include_inactive": {"type": "boolean", "default": False}},
            },
        },
    ]


def create_app(
    *,
    resource_url: str,
    authorization_server: str,
    token_verifier: TokenVerifier,
    library: Library,
) -> Starlette:
    """Skapar en fristående Connect-app med uttryckliga OAuth-beroenden."""

    async def protected_resource_metadata(_: Request) -> JSONResponse:
        return JSONResponse({"resource": resource_url, "authorization_servers": [authorization_server]})

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
        if not isinstance(subject, str) or not subject:
            return _unauthorized(resource_url)

        payload = await request.json()
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})

        if method == "initialize":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "promptbanken-connect", "version": "0.2.0"},
                    },
                }
            )

        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tool_definitions()}})

        if method != "tools/call" or not isinstance(params, Mapping):
            return _error(request_id, -32601, "MCP-metoden stöds inte ännu.")

        name = params.get("name")
        arguments = _arguments(params)
        if not isinstance(name, str) or arguments is None:
            return _error(request_id, -32602, "Ogiltiga verktygsargument.")

        if name == "get_connect_context":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"user_id": subject})})

        if name == "list_my_library":
            kind = arguments.get("kind", "all")
            limit = _limit(arguments)
            if not isinstance(kind, str) or kind not in {"all", "prompt", "package"} or limit is None:
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            items = library.list_library(access_token=token, kind=kind, limit=limit)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"items": items})})

        if name == "get_my_library_prompt":
            prompt_id = arguments.get("prompt_id")
            if not _valid_uuid(prompt_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            prompt = library.get_library_prompt(access_token=token, prompt_id=prompt_id)
            if prompt is None:
                return _error(request_id, -32004, "Objektet finns inte eller är inte tillgängligt.")
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"prompt": prompt})})

        if name == "list_my_packages":
            limit = _limit(arguments)
            if limit is None:
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            packages = library.list_packages(access_token=token, limit=limit)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"items": packages})})

        if name == "get_my_package":
            package_id = arguments.get("package_id")
            if not _valid_uuid(package_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            package = library.get_package(access_token=token, package_id=package_id)
            if package is None:
                return _error(request_id, -32004, "Objektet finns inte eller är inte tillgängligt.")
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"package": package})})

        if name == "list_my_shares":
            include_inactive = arguments.get("include_inactive", False)
            if not isinstance(include_inactive, bool):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            shares = library.list_shares(access_token=token, include_inactive=include_inactive)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"shares": shares})})

        return _error(request_id, -32601, "MCP-metoden stöds inte ännu.")

    return Starlette(
        routes=[
            Route("/healthz", health_check),
            Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
            Route("/mcp", mcp, methods=["POST"]),
        ]
    )