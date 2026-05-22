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


@mcp.tool()
def list_skills_simple() -> dict[str, Any]:
    """List Promptbanken skills grouped for a user-facing catalog view."""
    logger.info("tool_call name=list_skills_simple")
    categories: dict[str, list[dict[str, Any]]] = {}
    for skill in repository.list_skills():
        categories.setdefault(skill.category, []).append(
            {
                "id": skill.id,
                "display_name": skill.display_name,
                "description": skill.description,
                "risk_level": skill.risk_level,
                "risk_message": skill.risk_message,
                "example_phrases": skill.example_phrases,
            }
        )
    return {
        "title": "Vad vill du göra?",
        "categories": [
            {
                "name": category,
                "skills": sorted(skills, key=lambda item: item["display_name"]),
            }
            for category, skills in sorted(categories.items())
        ],
        "fallback_prompt": {
            "title": "Jag vet inte vilken mall jag ska använda",
            "options": [
                {"skill_id": "klarsprak", "label": "Göra texten enklare"},
                {"skill_id": "mejl", "label": "Skriva ett svar"},
                {"skill_id": "informationsutskick", "label": "Skapa ett informationsutskick"},
            ],
        },
    }


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
            "I hosted-läge ska MCP-klienten inte skicka användarens uppgift, indata, dokumenttext, "
            "personuppgifter eller sekretessbelagd information till Promptbanken MCP. Gör routing, "
            "riskkontroll och promptkompilering på klientsidan. Anropa bara list_skills, "
            "list_skills_simple och get_skill för att hämta metadata och promptmallar."
        ),
        "client_flow": [
            "Hämta användarvänlig katalog med list_skills_simple eller komplett metadata med list_skills.",
            "Matcha användarens uppgift lokalt mot id, display_name, description, example_phrases, intents, roles och audiences.",
            "Visa topp 2-3 föreslagna mallar om användaren inte valt explicit.",
            "Validera skill_id mot listan från list_skills innan get_skill anropas.",
            "Hämta vald promptmall med get_skill(skill_id, include_prompt=True).",
            "Använd skillens output_schema som stöd för förväntad svarsstruktur.",
            "Visa risk_message och anonymization_level för användaren vid behov.",
            "Kontrollera och anonymisera användarens text lokalt innan den används.",
            "Sätt ihop promptmall, uppgift och eventuell indata lokalt i MCP-klienten.",
            "Skicka inte användarens rådata till hosted MCP-tools.",
        ],
        "routing_algorithm": {
            "normalize": "Gör text gemen, trimma whitespace och vik svenska tecken till a/o vid jämförelse.",
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
                "Ge 30 poäng om skill-id förekommer i användarens uppgift, till exempel informationsutskick.",
                "Ge 20 poäng om hela eller stor del av skillens display_name eller name förekommer som fras i uppgiften.",
                "Ge 14 poäng per träff i example_phrases.",
                "Ge 12 poäng per exakt intent-träff eller svensk intent-synonym, till exempel information_notice/informationsutskick.",
                "Ge 6 poäng per träff i skillens name eller display_name.",
                "Ge 4 poäng per träff i skillens description.",
                "Ge 2 poäng per träff i övriga metadatafält.",
                "Ge 3 poäng om användarens roll matchar skill.roles.",
                "Ge 2 poäng om målgrupp matchar skill.audiences.",
                "Vid lika score, välj den skill som har flest träffar i id, display_name, name, example_phrases och intents före description och audiences.",
                "Välj högst poäng och visa upp till tre alternativ.",
                "Om ingen tydlig match hittas, föreslå klarspråk, sammanfattning och mejl som fallback.",
            ],
        },
        "local_mode_note": (
            "Vid lokal installation kan klienten använda route_skill, compile_skill_prompt och "
            "check_input_risk, eftersom texten då behandlas på användarens egen maskin."
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
