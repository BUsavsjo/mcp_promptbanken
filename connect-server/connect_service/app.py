"""Den OAuth-skyddade MCP-ytan för Promptbanken Connect."""

from collections.abc import Mapping
import json
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from connect_service.data import ConnectWriteError
from connect_service.personal import PersonalError
from connect_service.supports import SupportCatalog
from connect_service import work_layer as wl

SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
SERVER_VERSION = "0.3.0"


_WRITE_TOOL_NAMES = {
    "add_open_prompt_to_library",
    "add_open_package_to_library",
    "create_my_prompt",
    "update_my_prompt",
    "archive_my_prompt",
    "save_my_package",
    "set_package_prompts",
    "archive_my_package",
    "unfollow_open_prompt",
    "unfollow_open_package",
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


def _error(request_id: object, code: int, message: str, data: Mapping[str, object] | None = None) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}
    if data:
        error["data"] = dict(data)
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": error})


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


TOOL_PROFILES = ("core", "full")


def _tool_definitions(profile: str = "full") -> list[dict[str, object]]:
    """core = de sju verktygen för specialister och personliga arbetssätt.
    full = även Creator-biblioteket (prompter, paket, delningar)."""
    if profile == "core":
        return wl.tool_definitions()
    return [*wl.tool_definitions(), *_library_tool_definitions()]


def _library_tool_definitions() -> list[dict[str, object]]:
    return [
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
            "name": "unfollow_open_prompt",
            "description": "Tar bort en följd Open-prompt från ditt bibliotek efter uttrycklig bekräftelse.",
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
            "name": "unfollow_open_package",
            "description": "Tar bort ett följt Open-paket från ditt bibliotek efter uttrycklig bekräftelse.",
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
            "description": "Skapar en privat delningslänk för en egen prompt eller ett eget paket. Du skickar sedan länken till mottagaren.",
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
    work_layer: wl.WorkLayer | None = None,
    tool_profile: str = "full",
) -> Starlette:
    """Skapar en fristående Connect-app med uttryckliga OAuth-beroenden."""
    if tool_profile not in TOOL_PROFILES:
        raise ValueError(f"Okänd verktygsprofil: {tool_profile}")
    layer = work_layer or wl.WorkLayer(SupportCatalog(), library)  # type: ignore[arg-type]
    exposed_tools = _tool_definitions(tool_profile)
    exposed_names = {str(tool["name"]) for tool in exposed_tools}
    parsed_resource = urlparse(resource_url)
    app_host = parsed_resource.netloc.replace("connect-dev.", "dev.").replace("connect.", "app.")
    share_base_url = f"{parsed_resource.scheme}://{app_host}/delning/?s="

    async def protected_resource_metadata(_: Request) -> JSONResponse:
        return JSONResponse({"resource": resource_url, "authorization_servers": [authorization_server]})

    async def health_check(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "promptbanken-connect"})

    async def connect_write_error(request: Request, error: Exception) -> JSONResponse:
        message = str(error) or "Ändringen kunde inte genomföras. Kontrollera uppgifterna och försök igen."
        kind = getattr(error, "kind", "technical")
        return _error(getattr(request.state, "jsonrpc_id", None), -32020, message, {"kind": kind})

    async def work_layer_input_error(request: Request, error: Exception) -> JSONResponse:
        return _error(getattr(request.state, "jsonrpc_id", None), -32602, str(error) or "Ogiltiga verktygsargument.")

    async def work_layer_not_found(request: Request, _: Exception) -> JSONResponse:
        return _error(getattr(request.state, "jsonrpc_id", None), -32004, "Objektet finns inte eller är inte tillgängligt.")

    def prompt_list(token: str) -> list[dict[str, object]]:
        context = layer.context(token, "")
        entries = [*context["supports"], *[way for way in context["my_ways_of_working"] if way.get("active", True)]]
        return [
            {"name": entry["id"], "title": entry["name"], "description": entry["use_when"]}
            for entry in entries
        ]

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

        if isinstance(method, str) and method.startswith("notifications/"):
            return Response(status_code=202)

        if method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {}})

        if method == "initialize":
            requested = params.get("protocolVersion") if isinstance(params, Mapping) else None
            version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else "2025-06-18"
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": version,
                        "capabilities": {"tools": {}, "prompts": {}},
                        "serverInfo": {"name": "promptbanken-connect", "version": SERVER_VERSION},
                        "instructions": wl.SERVER_INSTRUCTIONS,
                    },
                }
            )

        if method == "tools/list":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": exposed_tools}})

        if method == "prompts/list":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"prompts": prompt_list(token)}})

        if method == "prompts/get":
            prompt_name = params.get("name") if isinstance(params, Mapping) else None
            if not isinstance(prompt_name, str):
                return _error(request_id, -32602, "Ogiltiga argument.")
            support = layer.support(token, prompt_name, None)
            text = (
                f"Arbeta enligt arbetssättet {support['name']}. Följ metoden nedan, användarens personliga regler "
                f"och prioriteringsordningen.\n\n{json.dumps(support, ensure_ascii=False)}"
            )
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "description": str(support["name"]),
                        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
                    },
                }
            )

        if method != "tools/call" or not isinstance(params, Mapping):
            return _error(request_id, -32601, "MCP-metoden stöds inte ännu.")

        name = params.get("name")
        arguments = _arguments(params)
        if not isinstance(name, str) or arguments is None:
            return _error(request_id, -32602, "Ogiltiga verktygsargument.")
        if name not in exposed_names:
            return _error(request_id, -32601, f"Verktyget {name} finns inte i den här Connect-anslutningen.")

        if name in _WRITE_TOOL_NAMES:
            if arguments.get("confirmed") is not True:
                return _error(request_id, -32010, "Bekräfta ändringen med confirmed: true.")
            if not _valid_uuid(arguments.get("request_id")):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")

        if name in wl.TOOL_NAMES:
            payload = _work_layer_call(layer, name, arguments, token, subject)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result(payload)})

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

        if name == "unfollow_open_prompt":
            prompt_id = arguments.get("prompt_id")
            if not _valid_uuid(prompt_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            prompt = library.archive_my_prompt(access_token=token, prompt_id=prompt_id, request_id=str(arguments["request_id"]))
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": _tool_result({"prompt": prompt})})

        if name == "update_my_prompt":
            prompt_id = arguments.get("prompt_id")
            title = arguments.get("title")
            content = arguments.get("content")
            summary = arguments.get("summary")
            category = arguments.get("category")
            if (not _valid_uuid(prompt_id) or not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip() or (summary is not None and not isinstance(summary, str)) or (category is not None and not isinstance(category, str))):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            if name == "update_my_prompt" and ("summary" not in arguments or "category" not in arguments):
                # Fält som inte skickas med ska behållas, inte tömmas.
                existing = library.get_library_prompt(access_token=token, prompt_id=prompt_id) or {}
                if "summary" not in arguments:
                    summary = existing.get("summary")
                if "category" not in arguments:
                    category = existing.get("category")
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

        if name in {"archive_my_package", "add_open_package_to_library", "unfollow_open_package"}:
            package_id = arguments.get("package_id")
            if not _valid_uuid(package_id):
                return _error(request_id, -32602, "Ogiltiga verktygsargument.")
            method_name = "archive_my_package" if name == "unfollow_open_package" else name
            package = getattr(library, method_name)(access_token=token, package_id=package_id, request_id=str(arguments["request_id"]))
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
            if isinstance(share.get("token"), str):
                share = {**share, "share_url": share_base_url + share["token"]}
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
        exception_handlers={
            ConnectWriteError: connect_write_error,
            PersonalError: work_layer_input_error,
            wl.ToolInputError: work_layer_input_error,
            wl.NotFound: work_layer_not_found,
        },
    )


def _work_layer_call(
    layer: wl.WorkLayer, name: str, arguments: Mapping[str, object], token: str, subject: str
) -> Mapping[str, object]:
    if name == "get_connect_context":
        return layer.context(token, subject)
    if name == "get_support":
        support_id = arguments.get("id")
        resource = arguments.get("resource")
        if not isinstance(support_id, str) or (resource is not None and not isinstance(resource, str)):
            raise wl.ToolInputError("Ange id som text.")
        return layer.support(token, support_id, resource)
    if name == "get_open_item":
        kind = arguments.get("kind")
        ref = arguments.get("ref")
        if kind not in {"prompt", "package"} or not isinstance(ref, str) or not ref.strip():
            raise wl.ToolInputError("Ange kind (prompt eller package) och ref.")
        return layer.open_item(token, str(kind), ref.strip())
    if name == "save_my_profile":
        return layer.save_profile(token, arguments)
    if name == "save_my_way_of_working":
        return layer.save_way(token, arguments)
    if name == "get_my_history":
        target = arguments.get("target")
        if not isinstance(target, str):
            raise wl.ToolInputError("Ange target.")
        return layer.history(token, target)
    if name == "restore_my_version":
        return layer.restore(token, arguments)
    raise wl.ToolInputError("Okänt verktyg.")
