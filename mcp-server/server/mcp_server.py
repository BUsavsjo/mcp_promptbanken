from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
import logging

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .risk_checker import RiskChecker
from .skill_repository import InvalidSkillIdError, SkillRepository
from .skill_router import SkillRouter


repo_root = Path(__file__).resolve().parents[1]
repository = SkillRepository(repo_root=repo_root)
router = SkillRouter(repository=repository)
risk_checker = RiskChecker()


def _log_level() -> str:
    return os.getenv("MCP_LOG_LEVEL", "INFO").upper()


logging.basicConfig(
    level=getattr(logging, _log_level(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("promptbanken_mcp")


def _server_mode() -> str:
    mode = os.getenv("PROMPTBANKEN_MCP_MODE", "hosted").strip().lower()
    if mode not in {"hosted", "local"}:
        return "hosted"
    return mode


SERVER_MODE = _server_mode()
SERVICE_VERSION = os.getenv("PROMPTBANKEN_MCP_VERSION", "1.1.0")
logger.info("server_config mode=%s skill_count=%s", SERVER_MODE, len(repository.list_skills()))

mcp = FastMCP(
    "promptbanken-skill-router",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    log_level=_log_level(),
)


@mcp.tool()
def list_skills() -> list[dict[str, Any]]:
    """List all Promptbanken skills with metadata, excluding full prompt text."""
    logger.info("tool_call name=list_skills")
    return [skill.to_dict() for skill in repository.list_skills()]


def _error(code: str, message: str, safe_to_show_user: bool = True) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "safe_to_show_user": safe_to_show_user,
        }
    }


@mcp.tool()
def get_skill(skill_id: str, include_prompt: bool = True) -> dict[str, Any]:
    """Get one skill by id, optionally including the full prompt text."""
    if not repository.is_valid_skill_id(skill_id):
        logger.info("tool_call name=get_skill result=invalid_skill_id include_prompt=%s", include_prompt)
        return _error("INVALID_SKILL_ID", "Skill id contains invalid characters")

    logger.info("tool_call name=get_skill skill_id=%s include_prompt=%s", skill_id, include_prompt)
    try:
        skill = repository.get_skill(skill_id)
        prompt = repository.get_prompt(skill_id) if include_prompt else None
    except KeyError:
        logger.info("tool_call name=get_skill skill_id=%s result=not_found", skill_id)
        return _error("SKILL_NOT_FOUND", "Skill not found")
    return skill.to_dict(include_prompt=include_prompt, prompt=prompt)


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Return lightweight service status without loading prompt text."""
    logger.info("tool_call name=health_check")
    return {
        "status": "ok",
        "service": "promptbanken-mcp",
        "version": SERVICE_VERSION,
        "mode": SERVER_MODE,
        "skills_count": len(repository.list_skills()),
    }


@mcp.tool()
def get_client_routing_instructions() -> dict[str, Any]:
    """Return instructions for client-side skill routing without sending user text to the MCP server."""
    logger.info("tool_call name=get_client_routing_instructions")
    return {
        "mode": SERVER_MODE,
        "privacy_instruction": (
            "I hosted lage ska MCP-klienten inte skicka anvandarens uppgift, indata, dokumenttext, "
            "personuppgifter eller sekretessbelagd information till Promptbanken MCP. Gor routing, "
            "riskkontroll och promptkompilering pa klientsidan. Anropa bara list_skills och get_skill "
            "for att hamta metadata och promptmallar."
        ),
        "client_flow": [
            "Hamta skill-metadata med list_skills.",
            "Matcha anvandarens uppgift lokalt mot name, description, intents, roles och audiences.",
            "Hamta vald promptmall med get_skill(skill_id, include_prompt=True).",
            "Anvand skillens output_schema som stod for forvantad svarsstruktur.",
            "Kontrollera och anonymisera anvandarens text lokalt innan den anvands.",
            "Satt ihop promptmall, uppgift och eventuell indata lokalt i MCP-klienten.",
            "Skicka inte anvandarens radata till hosted MCP-tools.",
        ],
        "routing_algorithm": {
            "normalize": "Gor text gemen, trimma whitespace och vik svenska tecken till a/o vid jamforelse.",
            "stopwords": [
                "att",
                "av",
                "de",
                "den",
                "det",
                "du",
                "en",
                "ett",
                "for",
                "fran",
                "gor",
                "har",
                "hur",
                "i",
                "jag",
                "kan",
                "med",
                "och",
                "om",
                "pa",
                "ska",
                "skriv",
                "skriva",
                "som",
                "till",
                "var",
                "vara",
                "vi",
            ],
            "score": [
                "Ta bort stopwords och ord kortare an tre tecken innan scoring.",
                "Ge 30 poang om skill-id forekommer i anvandarens uppgift, till exempel informationsutskick.",
                "Ge 20 poang om hela eller stor del av skillens name forekommer som fras i uppgiften.",
                "Ge 12 poang per exakt intent-traff eller svensk intent-synonym, till exempel information_notice/informationsutskick.",
                "Ge 6 poang per traff i skillens name.",
                "Ge 4 poang per traff i skillens description.",
                "Ge 2 poang per traff i ovriga metadatafalt.",
                "Ge 3 poang om anvandarens roll matchar skill.roles.",
                "Ge 2 poang om malgrupp matchar skill.audiences.",
                "Vid lika score, valj den skill som har flest traffar i id, name och intents fore description och audiences.",
                "Valj hogst poang och visa upp till tva alternativ.",
                "Om ingen tydlig match hittas, foresla klarsprak, sammanfattning och mejl som fallback.",
            ],
        },
        "local_mode_note": (
            "Vid lokal installation kan klienten anvanda route_skill, compile_skill_prompt och "
            "check_input_risk, eftersom texten da behandlas pa anvandarens egen maskin."
        ),
        "skills": [skill.to_dict() for skill in repository.list_skills()],
    }


if SERVER_MODE == "local":

    @mcp.tool()
    def route_skill(task: str, role: str | None = None, audience: str | None = None) -> dict[str, Any]:
        """Route a user task to the most relevant Promptbanken skill."""
        logger.info("tool_call name=route_skill mode=local has_role=%s has_audience=%s", bool(role), bool(audience))
        matches = router.route(task=task, role=role, audience=audience)
        return {
            "recommended": matches[0].to_dict() if matches else None,
            "alternatives": [match.to_dict() for match in matches[1:]],
        }

    @mcp.tool()
    def compile_skill_prompt(skill_id: str, user_task: str = "", user_input: str = "") -> dict[str, Any]:
        """Return a ready-to-use prompt assembled from a skill and optional user context."""
        logger.info(
            "tool_call name=compile_skill_prompt mode=local skill_id=%s has_user_task=%s has_user_input=%s",
            skill_id,
            bool(user_task),
            bool(user_input),
        )
        try:
            skill = repository.get_skill(skill_id)
            prompt = repository.get_prompt(skill_id)
        except InvalidSkillIdError:
            return _error("INVALID_SKILL_ID", "Skill id contains invalid characters")
        except KeyError:
            return _error("SKILL_NOT_FOUND", "Skill not found")
        risk = risk_checker.check(user_input or user_task)
        compiled = prompt
        if user_task:
            compiled += f"\n\nUppgift:\n{user_task.strip()}"
        if user_input:
            compiled += f"\n\nIndata:\n{user_input.strip()}"
        return {
            "skill": skill.to_dict(),
            "compiled_prompt": compiled,
            "risk_check": risk.to_dict(),
        }

    @mcp.tool()
    def check_input_risk(text: str) -> dict[str, object]:
        """Check text for common personal-data patterns before using a prompt."""
        logger.info("tool_call name=check_input_risk mode=local has_text=%s", bool(text))
        return risk_checker.check(text).to_dict()


def run_stdio() -> None:
    mcp.run(transport="stdio")


def _api_key() -> str | None:
    return os.getenv("PROMPTBANKEN_MCP_API_KEY") or os.getenv("MCP_API_KEY")


async def _healthz(_: Request) -> JSONResponse:
    logger.info("http_request path=/healthz status=200")
    return JSONResponse(
        {
            "status": "ok",
            "service": "promptbanken-mcp",
            "version": SERVICE_VERSION,
            "mode": SERVER_MODE,
            "skills_count": len(repository.list_skills()),
        }
    )


class BearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        token = _api_key()
        if scope.get("type") == "http" and token and scope.get("path") != "/healthz":
            headers = dict(scope.get("headers") or [])
            authorization = headers.get(b"authorization", b"").decode("utf-8")
            if authorization != f"Bearer {token}":
                logger.warning("auth_denied path=%s", scope.get("path"))
                response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


async def run_sse_async() -> None:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        logger.info("sse_connect path=/sse")
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            started_at = time.monotonic()
            try:
                await mcp._mcp_server.run(  # noqa: SLF001 - FastMCP 1.2 exposes no public ASGI app hook.
                    streams[0],
                    streams[1],
                    mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
                )
            finally:
                duration_ms = int((time.monotonic() - started_at) * 1000)
                logger.info("sse_disconnect path=/sse duration_ms=%s", duration_ms)

    app = Starlette(
        debug=mcp.settings.debug,
        routes=[
            Route("/healthz", endpoint=_healthz),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    app = BearerAuthMiddleware(app)
    logger.info("http_server_start host=%s port=%s mode=%s", mcp.settings.host, mcp.settings.port, SERVER_MODE)

    config = uvicorn.Config(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


def run_sse() -> None:
    anyio.run(run_sse_async)


if __name__ == "__main__":
    run_stdio()
