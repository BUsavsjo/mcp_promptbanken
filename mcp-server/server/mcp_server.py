from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import anyio
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .risk_checker import RiskChecker
from .skill_repository import SkillRepository
from .skill_router import SkillRouter


repo_root = Path(__file__).resolve().parents[1]
repository = SkillRepository(repo_root=repo_root)
router = SkillRouter(repository=repository)
risk_checker = RiskChecker()

mcp = FastMCP(
    "promptbanken-skill-router",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    log_level=os.getenv("MCP_LOG_LEVEL", "INFO"),
)


@mcp.tool()
def list_skills() -> list[dict[str, Any]]:
    """List all Promptbanken skills with metadata, excluding full prompt text."""
    return [skill.to_dict() for skill in repository.list_skills()]


@mcp.tool()
def get_skill(skill_id: str, include_prompt: bool = True) -> dict[str, Any]:
    """Get one skill by id, optionally including the full prompt text."""
    skill = repository.get_skill(skill_id)
    prompt = repository.get_prompt(skill_id) if include_prompt else None
    return skill.to_dict(include_prompt=include_prompt, prompt=prompt)


@mcp.tool()
def route_skill(task: str, role: str | None = None, audience: str | None = None) -> dict[str, Any]:
    """Route a user task to the most relevant Promptbanken skill."""
    matches = router.route(task=task, role=role, audience=audience)
    return {
        "recommended": matches[0].to_dict() if matches else None,
        "alternatives": [match.to_dict() for match in matches[1:]],
    }


@mcp.tool()
def compile_skill_prompt(skill_id: str, user_task: str = "", user_input: str = "") -> dict[str, Any]:
    """Return a ready-to-use prompt assembled from a skill and optional user context."""
    skill = repository.get_skill(skill_id)
    prompt = repository.get_prompt(skill_id)
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
    return risk_checker.check(text).to_dict()


def run_stdio() -> None:
    mcp.run(transport="stdio")


def _api_key() -> str | None:
    return os.getenv("PROMPTBANKEN_MCP_API_KEY") or os.getenv("MCP_API_KEY")


async def _healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "promptbanken-mcp"})


class BearerAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        token = _api_key()
        if scope.get("type") == "http" and token and scope.get("path") != "/healthz":
            headers = dict(scope.get("headers") or [])
            authorization = headers.get(b"authorization", b"").decode("utf-8")
            if authorization != f"Bearer {token}":
                response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


async def run_sse_async() -> None:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(  # noqa: SLF001 - FastMCP 1.2 exposes no public ASGI app hook.
                streams[0],
                streams[1],
                mcp._mcp_server.create_initialization_options(),  # noqa: SLF001
            )

    app = Starlette(
        debug=mcp.settings.debug,
        routes=[
            Route("/healthz", endpoint=_healthz),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    app = BearerAuthMiddleware(app)

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
