"""Den OAuth-skyddade MCP-ytan för Promptbanken Connect."""

from collections.abc import Mapping
import json
from typing import Protocol
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from connect_service.data import ConnectWriteError


_WRITE_TOOL_NAMES = {
    "add_open_prompt_to_library",
    "add_open_package_to_library",
    "create_my_prompt",
    "update_my_prompt",
    "archive_my_prompt",
    "save_my_package",
    "set_package_prompts",
    "archive_my_package",
    "create_my_share",
    "revoke_my_share",
    "extend_my_share",
}


class TokenVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, object]:
        """Returnerar verifierade claims eller kastar ValueError."""


class Library(Protocol):
    """RLS-skyddad åtkomst till den inloggade användarens Creator-bibliotek."""

    def list_library(self, *, access_token: str, kind: str, limit: int) -> list[Mapping[str, object]]: ...

    def search_open_catalog(
        self, *, access_token: str, query: str, kind: str, category: str | None, limit: int, cursor: int
    ) -> Mapping[str, object]: ...

    def get_library_prompt(self, *, access_token: str, prompt_id: str) -> Mapping[str, object] | None: ...

    def list_packages(self, *, access_token: str, limit: int) -> list[Mapping[str, object]]: ...

    def get_package(self, *, access_token: str, package_id: str) -> Mapping[str, object] | None: ...

    def list_shares(self, *, access_token: str, include_inactive: bool) -> list[Mapping[str, object]]: ...

    def create_my_prompt(
        self,
        *,
        access_token: str,
        title: str,
        content: str,
        summary: str | None,
        category: str | None,
        request_id: str,
    ) -> Mapping[str, object]: ...

    def archive_my_prompt(
        self, *, access_token: str, prompt_id: str, request_id: str
    ) -> Mapping[str, object]: ...


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
            "name": "search_open_catalog",
            "description": "Söker bland publicerade Open-prompter och paket utan att läsa ut prompttexter.",
            "inputSchema": {"type": "object", "properties": {"query": {"type": "string", "default": ""}, "kind": {"type": "string", "enum": ["all", "prompt", "package"], "default": "all"}, "category": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}, "cursor": {"type": "string"}}},
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
        {
            "name": "create_my_prompt",
            "description": "Skapar ett nytt privat promptutkast i ditt Creator-bibliotek efter uttrycklig bekräftelse.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "content": {"type": "string", "minLength": 1, "maxLength": 20000},
                    "summary": {"type": "string", "maxLength": 500},
                    "category": {"type": "string"},
                    "confirmed": {"type": "boolean", "description": "Måste vara true för att skapa utkastet."},
                    "request_id": {"type": "string", "format": "uuid"},
                },
                "required": ["title", "content", "confirmed", "request_id"],
            },
        },
        {
            "name": "update_my_prompt",
            "description": "Uppdaterar ett eget promptutkast efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"prompt_id": {"type": "string", "format": "uuid"}, "title": {"type": "string", "minLength": 1, "maxLength": 200}, "content": {"type": "string", "minLength": 1, "maxLength": 20000}, "summary": {"type": "string", "maxLength": 500}, "category": {"type": "string"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["prompt_id", "title", "content", "confirmed", "request_id"]},
        },
        {
            "name": "archive_my_prompt",
            "description": "Arkiverar ett eget promptutkast eller slutar följa en Open-prompt efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"prompt_id": {"type": "string", "format": "uuid"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["prompt_id", "confirmed", "request_id"]},
        },
        {
            "name": "save_my_package",
            "description": "Skapar eller uppdaterar ett eget paketutkast efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"package_id": {"type": "string", "format": "uuid"}, "title": {"type": "string", "minLength": 1}, "summary": {"type": "string"}, "package_type": {"type": "string", "enum": ["collection", "workflow"]}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["title", "package_type", "confirmed", "request_id"]},
        },
        {
            "name": "set_package_prompts",
            "description": "Ersätter ett utkastpakets prompts i angiven ordning efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"package_id": {"type": "string", "format": "uuid"}, "prompt_ids": {"type": "array", "items": {"type": "string", "format": "uuid"}, "maxItems": 8}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["package_id", "prompt_ids", "confirmed", "request_id"]},
        },
        {
            "name": "archive_my_package",
            "description": "Arkiverar ett eget paketutkast eller slutar följa ett Open-paket efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"package_id": {"type": "string", "format": "uuid"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["package_id", "confirmed", "request_id"]},
        },
        {
            "name": "add_open_prompt_to_library",
            "description": "Sparar en publicerad Open-prompt som en levande referens i ditt bibliotek efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"prompt_id": {"type": "string", "format": "uuid"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["prompt_id", "confirmed", "request_id"]},
        },
        {
            "name": "add_open_package_to_library",
            "description": "Sparar ett publicerat Open-paket som en levande referens i ditt bibliotek efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"package_id": {"type": "string", "format": "uuid"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["package_id", "confirmed", "request_id"]},
        },
        {
            "name": "create_my_share",
            "description": "Skapar en delning av en egen prompt eller ett eget paket efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"subject_type": {"type": "string", "enum": ["prompt", "package"]}, "subject_id": {"type": "string", "format": "uuid"}, "pin_version": {"type": "boolean", "default": False}, "expires_at": {"type": "string", "format": "date-time"}, "label": {"type": "string"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["subject_type", "subject_id", "confirmed", "request_id"]},
        },
        {
            "name": "revoke_my_share",
            "description": "Avslutar en egen delning efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"share_id": {"type": "string", "format": "uuid"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["share_id", "confirmed", "request_id"]},
        },
        {
            "name": "extend_my_share",
            "description": "Ändrar sluttiden för en egen aktiv delning efter uttrycklig bekräftelse.",
            "inputSchema": {"type": "object", "properties": {"share_id": {"type": "string", "format": "uuid"}, "expires_at": {"type": "string", "format": "date-time"}, "confirmed": {"type": "boolean"}, "request_id": {"type": "string", "format": "uuid"}}, "required": ["share_id", "expires_at", "confirmed", "request_id"]},
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

    async def connect_write_error(request: Request, error: Exception) -> JSONResponse:
        message = str(error) or "Ändringen kunde inte genomföras. Kontrollera uppgifterna och försök igen."
        return _error(getattr(request.state, "jsonrpc_id", None), -32020, message)

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
        request.state.jsonrpc_id = request_id
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

        if name in _WRITE_TOOL_NAMES:
            if arguments.get("confirmed") is not True:
                return _error(request_id, -32010, "Bekräfta ändringen med confirmed: true.")
            if not _valid_uuid(arguments.get("request_id")):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")

        if name == "get_connect_context":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"user_id": subject})})

        if name == "search_open_catalog":
            query = arguments.get("query", "")
            kind = arguments.get("kind", "all")
            category = arguments.get("category")
            limit = _limit(arguments)
            cursor_value = arguments.get("cursor", "0")
            if (
                not isinstance(query, str)
                or kind not in {"all", "prompt", "package"}
                or (category is not None and not isinstance(category, str))
                or limit is None
                or not isinstance(cursor_value, str)
                or not cursor_value.isdigit()
            ):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            result = library.search_open_catalog(
                access_token=token,
                query=query,
                kind=kind,
                category=category,
                limit=limit,
                cursor=int(cursor_value),
            )
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result(result)})

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

        if name == "create_my_prompt":
            title = arguments.get("title")
            content = arguments.get("content")
            summary = arguments.get("summary")
            category = arguments.get("category")
            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(content, str)
                or not content.strip()
                or (summary is not None and not isinstance(summary, str))
                or (category is not None and not isinstance(category, str))
            ):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            prompt = library.create_my_prompt(
                access_token=token,
                title=title,
                content=content,
                summary=summary,
                category=category,
                request_id=str(arguments["request_id"]),
            )
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"prompt": prompt})})

        if name == "archive_my_prompt":
            prompt_id = arguments.get("prompt_id")
            if not _valid_uuid(prompt_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            prompt = library.archive_my_prompt(
                access_token=token,
                prompt_id=prompt_id,
                request_id=str(arguments["request_id"]),
            )
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"prompt": prompt})})

        if name == "update_my_prompt":
            prompt_id = arguments.get("prompt_id")
            title = arguments.get("title")
            content = arguments.get("content")
            summary = arguments.get("summary")
            category = arguments.get("category")
            if (not _valid_uuid(prompt_id) or not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip() or (summary is not None and not isinstance(summary, str)) or (category is not None and not isinstance(category, str))):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            prompt = getattr(library, name)(access_token=token, prompt_id=prompt_id, title=title, content=content, summary=summary, category=category, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"prompt": prompt})})

        if name == "save_my_package":
            package_id = arguments.get("package_id")
            title = arguments.get("title")
            summary = arguments.get("summary")
            package_type = arguments.get("package_type")
            if ((package_id is not None and not _valid_uuid(package_id)) or not isinstance(title, str) or not title.strip() or (summary is not None and not isinstance(summary, str)) or package_type not in {"collection", "workflow"}):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            package = getattr(library, name)(access_token=token, package_id=package_id, title=title, summary=summary, package_type=package_type, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"package": package})})

        if name == "set_package_prompts":
            package_id = arguments.get("package_id")
            prompt_ids = arguments.get("prompt_ids")
            if (not _valid_uuid(package_id) or not isinstance(prompt_ids, list) or len(prompt_ids) > 8 or len(set(prompt_ids)) != len(prompt_ids) or not all(_valid_uuid(item) for item in prompt_ids)):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            package = getattr(library, name)(access_token=token, package_id=package_id, prompt_ids=prompt_ids, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"package": package})})

        if name in {"archive_my_package", "add_open_package_to_library"}:
            package_id = arguments.get("package_id")
            if not _valid_uuid(package_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            package = getattr(library, name)(access_token=token, package_id=package_id, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"package": package})})

        if name == "add_open_prompt_to_library":
            prompt_id = arguments.get("prompt_id")
            if not _valid_uuid(prompt_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            item = getattr(library, name)(access_token=token, prompt_id=prompt_id, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"library_item": item})})

        if name == "create_my_share":
            subject_type = arguments.get("subject_type")
            subject_id = arguments.get("subject_id")
            pin_version = arguments.get("pin_version", False)
            expires_at = arguments.get("expires_at")
            label = arguments.get("label")
            if (subject_type not in {"prompt", "package"} or not _valid_uuid(subject_id) or not isinstance(pin_version, bool) or (expires_at is not None and not isinstance(expires_at, str)) or (label is not None and not isinstance(label, str))):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            share = getattr(library, name)(access_token=token, subject_type=subject_type, subject_id=subject_id, pin_version=pin_version, expires_at=expires_at, label=label, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"share": share})})

        if name == "revoke_my_share":
            share_id = arguments.get("share_id")
            if not _valid_uuid(share_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            share = getattr(library, name)(access_token=token, share_id=share_id, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"share": share})})

        if name == "extend_my_share":
            share_id = arguments.get("share_id")
            expires_at = arguments.get("expires_at")
            if not _valid_uuid(share_id) or not isinstance(expires_at, str) or not expires_at.strip():
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            share = getattr(library, name)(access_token=token, share_id=share_id, expires_at=expires_at, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"share": share})})

        return _error(request_id, -32601, "MCP-metoden stöds inte ännu.")

    return Starlette(
        routes=[
            Route("/healthz", health_check),
            Route("/.well-known/oauth-protected-resource/mcp", protected_resource_metadata),
            Route("/mcp", mcp, methods=["POST"]),
        ],
        exception_handlers={ConnectWriteError: connect_write_error},
    )
