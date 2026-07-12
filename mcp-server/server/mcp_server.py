from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path
from typing import Any
import logging

import anyio
import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .hosted_guard import HostedMetadataGuard
from .pro_templates import list_pro_templates as _fetch_pro_templates
from .pro_templates import list_private_prompts as _fetch_private_prompts
from .pro_templates import list_shared_prompts as _fetch_shared_prompts
from .pro_templates import list_shared_workspaces as _fetch_shared_workspaces
from .pro_templates import save_prompt as _save_prompt
from .pro_templates import log_write_attempt as _log_write_attempt
from .risk_checker import RiskChecker
from .skill_repository import InvalidSkillIdError, SkillRepository
from .skill_router import SkillRouter
from .supabase_repository import SupabaseRepository


repo_root = Path(__file__).resolve().parents[1]
repository = SkillRepository(repo_root=repo_root)
router = SkillRouter(repository=repository)
risk_checker = RiskChecker()

def _supabase_repo_for_key(mcp_key: str) -> SupabaseRepository | None:
    if not mcp_key:
        return None
    return SupabaseRepository(mcp_key)


def _resolve_all_skills(mcp_key: str = ""):
    """Returnerar (alla skills, workspace_status).

    workspace_status är None om ingen mcp_key skickades (rent publikt anrop),
    "ok" om nyckeln matchade ett aktivt workspace, annars "invalid_key" —
    vilket också täcker återkallade nycklar (RPC:n skiljer inte ut orsaken,
    se SupabaseRepository.key_is_valid).
    """
    static = repository.list_skills()
    repo = _supabase_repo_for_key(mcp_key)
    if repo is None:
        return static, None
    workspace_skills = repo.list_skills()
    workspace_status = "ok" if repo.key_is_valid() else "invalid_key"
    return static + workspace_skills, workspace_status


def _all_skills(mcp_key: str = ""):
    skills, _ = _resolve_all_skills(mcp_key)
    return skills


_WORKSPACE_STATUS_MESSAGES = {
    "invalid_key": "API-nyckeln är ogiltig eller återkallad. Endast publika mallar visas.",
}


def _add_workspace_status(payload: dict[str, Any], workspace_status: str | None) -> dict[str, Any]:
    if workspace_status is not None:
        payload["workspace_status"] = workspace_status
        message = _WORKSPACE_STATUS_MESSAGES.get(workspace_status)
        if message:
            payload["workspace_message"] = message
    return payload


def _get_skill_and_prompt(skill_id: str, include_prompt: bool, mcp_key: str = ""):
    """Hämtar skill + prompt från statisk repo eller Supabase-repo."""
    try:
        skill = repository.get_skill(skill_id)
        prompt = repository.get_prompt(skill_id) if include_prompt else None
        return skill, prompt
    except KeyError:
        pass
    repo = _supabase_repo_for_key(mcp_key)
    if repo is not None:
        ws_skills = repo.list_skills()
        match = next((s for s in ws_skills if s.id == skill_id), None)
        if match:
            prompt = repo.get_prompt(skill_id) if include_prompt else None
            return match, prompt
    raise KeyError("Skill not found")


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
HOSTED_GUARD_MODE = os.getenv("PROMPTBANKEN_MCP_HOSTED_GUARD", "warn").strip().lower()
logger.info("server_config mode=%s skill_count=%s", SERVER_MODE, len(repository.list_skills()))

mcp = FastMCP(
    "promptbanken-skill-router",
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    log_level=_log_level(),
)


def _mcp_key_from_request(request: Request) -> str:
    mcp_key = request.headers.get("x-mcp-key", "")
    if mcp_key:
        return mcp_key
    # Klienter som ChatGPT kan bara skicka en generisk Bearer-token, inte en egen
    # X-MCP-Key-header. Vi accepterar därför workspace-nyckeln även via Authorization.
    # OBS: om PROMPTBANKEN_MCP_API_KEY är satt agerar BearerAuthMiddleware som en
    # global spärr på just Authorization — då är per-användarnyckel via Authorization
    # ömsesidigt uteslutande med den globala nyckeln (se BearerAuthMiddleware och
    # startvarningen i run_sse_async). Den globala nyckeln tolkas aldrig som en
    # workspace-nyckel, så den skickas inte vidare som hash till Supabase.
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        global_key = _api_key()
        if global_key and hmac.compare_digest(token, global_key):
            return ""
        return token
    return ""


@mcp.tool()
def list_skills() -> list[dict[str, Any]]:
    """List all Promptbanken skills with metadata, excluding full prompt text."""
    logger.info("tool_call name=list_skills")
    return [skill.to_dict() for skill in _all_skills()]


@mcp.tool()
def check_input_risk(text: str) -> dict[str, object]:
    """Check text for common personal-data patterns (personnummer, e-post,
    telefonnummer, arendenummer) before saving it as a template. Never blocks,
    only warns -- the calling model/user decides whether to edit or proceed."""
    logger.info("tool_call name=check_input_risk")
    return risk_checker.check(text).to_dict()


def _pro_templates_payload(mcp_key: str = "") -> dict[str, Any]:
    templates = _fetch_pro_templates(mcp_key)
    return {
        "unlocked": bool(templates) and all(t.get("is_unlocked") for t in templates),
        "templates": templates,
    }


_WRITE_OUTCOME_PATTERNS = [
    ("Ogiltig eller aterkallad", "invalid_key"),
    ("inte aktiv eller saknar MCP-atkomst", "invalid_key"),
    ("kraver en Pro-nyckel", "not_pro"),
    ("For manga skrivforsok", "rate_limited"),
    ("Ogiltig indata", "invalid_input"),
    ("risk_check_passed maste vara true", "risk_check_not_passed"),
]


def _classify_write_error(detail: str) -> str:
    for needle, outcome in _WRITE_OUTCOME_PATTERNS:
        if needle in detail:
            return outcome
    return "limit_reached"


def _save_workspace_prompt_payload(
    mcp_key: str,
    title: str,
    content: str,
    category: str,
    source: str,
    risk_check_passed: bool,
    idempotency_key: str | None,
) -> dict[str, Any]:
    if not mcp_key:
        return {"status": "error", "message": "MCP-nyckel kravs (X-MCP-Key eller Authorization)."}
    try:
        row = _save_prompt(mcp_key, title, content, category, source, risk_check_passed, idempotency_key)
        return {"status": "success", "prompt": row}
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        logger.info("tool_call name=save_workspace_prompt status=error detail=%s", detail)
        _log_write_attempt(mcp_key, _classify_write_error(detail), risk_check_passed)
        return {"status": "error", "message": detail}
    except RuntimeError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.error("save_workspace_prompt_failed error=%s", exc)
        return {"status": "error", "message": "Kunde inte spara prompten."}


@mcp.tool()
def list_pro_templates() -> dict[str, Any]:
    """List Promptbanken Pro premium templates. Full prompt text is only
    included if the MCP key belongs to a workspace with an active Pro plan --
    otherwise a teaser (title/syfte/output only) is returned for each template."""
    logger.info("tool_call name=list_pro_templates")
    return _pro_templates_payload()


def _list_skills_simple_payload(mcp_key: str = "") -> dict[str, Any]:
    all_skills, workspace_status = _resolve_all_skills(mcp_key)
    categories: dict[str, list[dict[str, Any]]] = {}
    for skill in all_skills:
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
    payload: dict[str, Any] = {
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
    return _add_workspace_status(payload, workspace_status)


@mcp.tool()
def list_skills_simple() -> dict[str, Any]:
    """List Promptbanken skills grouped for a user-facing catalog view."""
    logger.info("tool_call name=list_skills_simple")
    return _list_skills_simple_payload()


_MY_PROMPTS_NO_KEY_MESSAGE = (
    "Ingen MCP-nyckel skickades. Autentisera med din personliga X-MCP-Key för att se dina sparade prompts."
)


def _my_prompts_payload(mcp_key: str = "") -> dict[str, Any]:
    """Listar bara den anropande nyckelns egna sparade prompts (source == 'workspace'),
    till skillnad från list_skills/list_skills_simple som blandar in dem bland de publika
    mallarna. Löser att MCP-klienter inte hittar "mina prompts" utan att känna till
    source-fältet eller workspace_-id-prefixet."""
    if not mcp_key:
        return {
            "workspace_status": "no_key",
            "workspace_message": _MY_PROMPTS_NO_KEY_MESSAGE,
            "prompts": [],
        }
    all_skills, workspace_status = _resolve_all_skills(mcp_key)
    my_skills = [skill for skill in all_skills if skill.source == "workspace"]
    payload: dict[str, Any] = {
        "prompts": [
            {
                "id": skill.id,
                "display_name": skill.display_name,
                "description": skill.description,
                "category": skill.category,
                "risk_level": skill.risk_level,
                "risk_message": skill.risk_message,
            }
            for skill in my_skills
        ],
    }
    return _add_workspace_status(payload, workspace_status)


@mcp.tool()
def list_my_prompts() -> dict[str, Any]:
    """List only the caller's own saved prompts from their Promptbanken workspace
    (not the public standard templates or Pro premium templates). Requires a valid
    MCP key; without one, or with an invalid/revoked key, returns an empty list and
    an explanatory workspace_status/workspace_message."""
    logger.info("tool_call name=list_my_prompts")
    return _my_prompts_payload()


_CONTEXT_MCP_NO_KEY_MESSAGE = (
    "Ingen MCP-nyckel skickades. Autentisera med din personliga X-MCP-Key för att se dina Pro-prompts."
)


def _my_private_prompts_payload(mcp_key: str = "") -> dict[str, Any]:
    """Nyckelns egna privata Pro-prompts (personlig yta), aldrig andra medlemmars
    privata prompts eller organisationsprompts. Se pro_templates.list_private_prompts."""
    if not mcp_key:
        return {
            "workspace_status": "no_key",
            "workspace_message": _CONTEXT_MCP_NO_KEY_MESSAGE,
            "prompts": [],
        }
    return {"prompts": _fetch_private_prompts(mcp_key)}


def _my_shared_workspaces_payload(mcp_key: str = "") -> dict[str, Any]:
    """Discovery: vilka delade arbetsytor nyckeln kan välja mellan (id + namn)."""
    if not mcp_key:
        return {
            "workspace_status": "no_key",
            "workspace_message": _CONTEXT_MCP_NO_KEY_MESSAGE,
            "workspaces": [],
        }
    return {"workspaces": _fetch_shared_workspaces(mcp_key)}


def _shared_workspace_prompts_payload(mcp_key: str, workspace_id: str) -> dict[str, Any]:
    """Delade prompts från EN delad arbetsyta där nyckelns ägare är medlem."""
    if not mcp_key:
        return {
            "workspace_status": "no_key",
            "workspace_message": _CONTEXT_MCP_NO_KEY_MESSAGE,
            "prompts": [],
        }
    return {"prompts": _fetch_shared_prompts(mcp_key, workspace_id)}


@mcp.tool()
def list_my_private_prompts() -> dict[str, Any]:
    """List the caller's own private Pro prompts (personal workspace). Requires
    a valid MCP key; never returns other members' private prompts or
    organization prompts."""
    logger.info("tool_call name=list_my_private_prompts")
    return _my_private_prompts_payload()


@mcp.tool()
def list_my_shared_workspaces() -> dict[str, Any]:
    """List the shared workspaces the caller's MCP key can access (id + name).
    Use a returned workspace_id with list_shared_workspace_prompts."""
    logger.info("tool_call name=list_my_shared_workspaces")
    return _my_shared_workspaces_payload()


@mcp.tool()
def list_shared_workspace_prompts(workspace_id: str) -> dict[str, Any]:
    """List shared prompts from ONE shared workspace the caller is a member of.
    Requires an explicit workspace_id (from list_my_shared_workspaces)."""
    logger.info("tool_call name=list_shared_workspace_prompts")
    return _shared_workspace_prompts_payload("", workspace_id)


def _error(code: str, message: str, safe_to_show_user: bool = True) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "safe_to_show_user": safe_to_show_user,
        }
    }


def _json_rpc_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }


@mcp.tool()
def get_skill(skill_id: str, include_prompt: bool = True) -> dict[str, Any]:
    """Get one skill by id, optionally including the full prompt text."""
    if not repository.is_valid_skill_id(skill_id):
        logger.info("tool_call name=get_skill result=invalid_skill_id include_prompt=%s", include_prompt)
        return _error("INVALID_SKILL_ID", "Skill id contains invalid characters")

    logger.info("tool_call name=get_skill skill_id=%s include_prompt=%s", skill_id, include_prompt)
    try:
        skill, prompt = _get_skill_and_prompt(skill_id, include_prompt)
    except KeyError:
        logger.info("tool_call name=get_skill skill_id=%s result=not_found", skill_id)
        return _error("SKILL_NOT_FOUND", "Skill not found")
    return skill.to_dict(include_prompt=include_prompt, prompt=prompt)


_HEALTH_CHECK_STATES = {
    "no_key": {
        "plan": "public",
        "catalog": "open",
        "message": (
            "Detta är den öppna katalogen. Autentisera med API/MCP-nyckel för "
            "användar- eller Pro-mallar på kommun.promptbanken.se."
        ),
    },
    "invalid_key": {
        "plan": "public",
        "catalog": "open",
        "message": _WORKSPACE_STATUS_MESSAGES["invalid_key"],
    },
    "free": {
        "plan": "free",
        "catalog": "workspace",
        "message": (
            "Inloggad med en free-nyckel. Publika mallar och dina egna sparade "
            "prompts är tillgängliga. Uppgradera till Pro för premium-mallar."
        ),
    },
    "pro": {
        "plan": "pro",
        "catalog": "pro",
        "message": (
            "Inloggad med en Pro-nyckel. Publika mallar, dina sparade prompts "
            "och premium-mallarna är tillgängliga."
        ),
    },
}


def _health_check_state(mcp_key: str) -> str:
    if not mcp_key:
        return "no_key"
    repo = _supabase_repo_for_key(mcp_key)
    if repo is None or not repo.key_is_valid():
        return "invalid_key"
    return "pro" if repo.plan == "pro" else "free"


def _health_check_payload(mcp_key: str = "") -> dict[str, Any]:
    state = _HEALTH_CHECK_STATES[_health_check_state(mcp_key)]
    return {
        "status": "ok",
        "service": "promptbanken-mcp",
        "version": SERVICE_VERSION,
        "mode": SERVER_MODE,
        "skills_count": len(repository.list_skills()),
        "catalog": state["catalog"],
        "plan": state["plan"],
        "message": state["message"],
    }


@mcp.tool()
def health_check() -> dict[str, Any]:
    """Return lightweight service status without loading prompt text."""
    logger.info("tool_call name=health_check")
    return _health_check_payload()


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
            "Vid lokal installation kan klienten dessutom använda route_skill och "
            "compile_skill_prompt, eftersom texten då behandlas på användarens egen maskin. "
            "check_input_risk är tillgängligt i både hosted och local läge (behövs som "
            "förarbetssteg innan save_workspace_prompt anropas i hosted läge)."
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
            skill, prompt = _get_skill_and_prompt(skill_id, include_prompt=True)
            if prompt is None:
                prompt = ""
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


def run_stdio() -> None:
    mcp.run(transport="stdio")


def _api_key() -> str | None:
    return os.getenv("PROMPTBANKEN_MCP_API_KEY") or os.getenv("MCP_API_KEY")


def _allowed_origins() -> set[str]:
    raw = os.getenv("PROMPTBANKEN_MCP_ALLOWED_ORIGINS", "")
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


async def _healthz(request: Request) -> JSONResponse:
    logger.info("http_request path=/healthz status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_health_check_payload(mcp_key))


def _not_found(message: str = "Not found") -> JSONResponse:
    return JSONResponse({"error": {"code": "NOT_FOUND", "message": message}}, status_code=404)


async def _api_list_skills(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/skills status=200")
    mcp_key = _mcp_key_from_request(request)
    skills, workspace_status = _resolve_all_skills(mcp_key)
    payload: dict[str, Any] = {"skills": [skill.to_dict() for skill in skills]}
    return JSONResponse(_add_workspace_status(payload, workspace_status))


async def _api_list_skills_simple(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/skills/simple status=200")
    return JSONResponse(_list_skills_simple_payload(_mcp_key_from_request(request)))


async def _api_get_skill(request: Request) -> JSONResponse:
    skill_id = request.path_params["skill_id"]
    include_prompt = request.query_params.get("include_prompt", "false").lower() == "true"
    mcp_key = _mcp_key_from_request(request)
    if not repository.is_valid_skill_id(skill_id):
        logger.info("http_request path=/api/v1/skills/%s status=400 result=invalid_skill_id", skill_id)
        return JSONResponse(_error("INVALID_SKILL_ID", "Skill id contains invalid characters"), status_code=400)
    try:
        skill, prompt = _get_skill_and_prompt(skill_id, include_prompt, mcp_key)
    except KeyError:
        logger.info("http_request path=/api/v1/skills/%s status=404", skill_id)
        return _not_found("Skill not found")
    logger.info("http_request path=/api/v1/skills/%s status=200 include_prompt=%s", skill_id, include_prompt)
    return JSONResponse(skill.to_dict(include_prompt=include_prompt, prompt=prompt))


async def _api_get_skill_prompt(request: Request) -> JSONResponse:
    skill_id = request.path_params["skill_id"]
    if not repository.is_valid_skill_id(skill_id):
        logger.info("http_request path=/api/v1/skills/%s/prompt status=400 result=invalid_skill_id", skill_id)
        return JSONResponse(_error("INVALID_SKILL_ID", "Skill id contains invalid characters"), status_code=400)
    try:
        _, prompt = _get_skill_and_prompt(skill_id, include_prompt=True)
        if prompt is None:
            prompt = ""
    except KeyError:
        logger.info("http_request path=/api/v1/skills/%s/prompt status=404", skill_id)
        return _not_found("Skill not found")
    logger.info("http_request path=/api/v1/skills/%s/prompt status=200", skill_id)
    return JSONResponse({"skill_id": skill_id, "prompt": prompt})


async def _api_routing_instructions(_: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/routing-instructions status=200")
    return JSONResponse(get_client_routing_instructions())


async def _api_pro_templates(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/pro-templates status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_pro_templates_payload(mcp_key))


async def _api_my_prompts(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/my-prompts status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_my_prompts_payload(mcp_key))


async def _api_my_private_prompts(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/my-private-prompts status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_my_private_prompts_payload(mcp_key))


async def _api_my_shared_workspaces(request: Request) -> JSONResponse:
    logger.info("http_request path=/api/v1/my-shared-workspaces status=200")
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_my_shared_workspaces_payload(mcp_key))


async def _api_shared_workspace_prompts(request: Request) -> JSONResponse:
    workspace_id = request.path_params["workspace_id"]
    logger.info("http_request path=/api/v1/shared-workspaces/%s/prompts status=200", workspace_id)
    mcp_key = _mcp_key_from_request(request)
    return JSONResponse(_shared_workspace_prompts_payload(mcp_key, workspace_id))


async def _api_save_workspace_prompt(request: Request) -> JSONResponse:
    mcp_key = _mcp_key_from_request(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_error("INVALID_JSON", "Request body must be JSON"), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error("INVALID_BODY", "Request body must be a JSON object"), status_code=400)
    title, content, category = body.get("title"), body.get("content"), body.get("category")
    if not all(isinstance(v, str) and v for v in (title, content, category)):
        return JSONResponse(
            _error("INVALID_ARGUMENTS", "title, content and category are required strings"), status_code=400
        )
    payload = _save_workspace_prompt_payload(
        mcp_key,
        title,
        content,
        category,
        body.get("source", "manual"),
        bool(body.get("risk_check_passed", False)),
        body.get("idempotency_key"),
    )
    status_code = 200 if payload.get("status") == "success" else 400
    logger.info("http_request path=/api/v1/my-prompts method=POST status=%s", status_code)
    return JSONResponse(payload, status_code=status_code)


def _openapi_schema() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Promptbanken Read-only API",
            "version": SERVICE_VERSION,
            "description": "Read-only API for Promptbanken skills and prompt templates.",
        },
        "paths": {
            "/healthz": {"get": {"summary": "Health check", "responses": {"200": {"description": "OK"}}}},
            "/api/v1/skills": {"get": {"summary": "List skills", "responses": {"200": {"description": "OK"}}}},
            "/api/v1/skills/simple": {
                "get": {"summary": "List skills grouped for UI", "responses": {"200": {"description": "OK"}}}
            },
            "/api/v1/skills/{skill_id}": {
                "get": {
                    "summary": "Get skill metadata",
                    "parameters": [
                        {"name": "skill_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "include_prompt", "in": "query", "required": False, "schema": {"type": "boolean"}},
                    ],
                    "responses": {"200": {"description": "OK"}, "404": {"description": "Skill not found"}},
                }
            },
            "/api/v1/skills/{skill_id}/prompt": {
                "get": {
                    "summary": "Get prompt template",
                    "parameters": [{"name": "skill_id", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {"200": {"description": "OK"}, "404": {"description": "Skill not found"}},
                }
            },
            "/api/v1/routing-instructions": {
                "get": {"summary": "Get client routing instructions", "responses": {"200": {"description": "OK"}}}
            },
            "/api/v1/pro-templates": {
                "get": {
                    "summary": "List Promptbanken Pro premium templates (teaser unless the MCP key has an active Pro plan)",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/v1/my-prompts": {
                "get": {
                    "summary": "List only the caller's own saved prompts (requires a valid MCP key)",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Save a new prompt into the caller's personal Pro workspace (requires a Pro MCP key)",
                    "responses": {"200": {"description": "Saved"}, "400": {"description": "Rejected"}},
                },
            },
            "/api/v1/my-private-prompts": {
                "get": {
                    "summary": "List the caller's own private Pro prompts (personal workspace)",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/v1/my-shared-workspaces": {
                "get": {
                    "summary": "List the shared workspaces the caller's MCP key can access",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/v1/shared-workspaces/{workspace_id}/prompts": {
                "get": {
                    "summary": "List shared prompts from one shared workspace the caller is a member of",
                    "parameters": [
                        {"name": "workspace_id", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/mcp": {
                "post": {"summary": "MCP Streamable HTTP endpoint", "responses": {"200": {"description": "JSON-RPC response"}}},
                "get": {"summary": "Optional MCP server stream", "responses": {"405": {"description": "No server stream"}}},
            },
        },
    }


async def _openapi(_: Request) -> JSONResponse:
    logger.info("http_request path=/openapi.json status=200")
    return JSONResponse(_openapi_schema())


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "list_skills",
            "description": "List all Promptbanken skills with metadata, excluding full prompt text.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "check_input_risk",
            "description": (
                "Check text for common personal-data patterns (personnummer, e-post, "
                "telefonnummer, arendenummer) before saving it as a template. Never blocks, "
                "only warns."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "list_skills_simple",
            "description": "List Promptbanken skills grouped for a user-facing catalog view.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_skill",
            "description": "Get one skill by id, optionally including the full prompt text.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "include_prompt": {"type": "boolean", "default": True},
                },
                "required": ["skill_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "health_check",
            "description": "Return lightweight service status without loading prompt text.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_client_routing_instructions",
            "description": "Return instructions for client-side skill routing without sending user text to the MCP server.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_pro_templates",
            "description": (
                "List Promptbanken Pro premium templates. Full prompt text is only included if the "
                "MCP key belongs to a workspace with an active Pro plan, otherwise a teaser is returned."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_my_prompts",
            "description": (
                "List only the caller's own saved prompts from their Promptbanken workspace "
                "(not the public standard templates or Pro premium templates). Requires a valid MCP key."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_my_private_prompts",
            "description": (
                "List the caller's own private Pro prompts (personal workspace). Requires a valid "
                "MCP key; never returns other members' private prompts or organization prompts."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_my_shared_workspaces",
            "description": (
                "List the shared workspaces the caller's MCP key can access (id + name). Use a "
                "returned workspace_id with list_shared_workspace_prompts."
            ),
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "list_shared_workspace_prompts",
            "description": (
                "List shared prompts from ONE shared workspace the caller is a member of. Requires "
                "an explicit workspace_id from list_my_shared_workspaces."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_id": {"type": "string"}},
                "required": ["workspace_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "save_workspace_prompt",
            "description": (
                "Save a generalised, already GDPR-checked template into the caller's "
                "personal Pro workspace. Requires a Pro key. See the tool description "
                "for the required approval + risk-check flow."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "category": {"type": "string"},
                    "source": {"type": "string", "default": "manual"},
                    "risk_check_passed": {"type": "boolean", "default": False},
                    "idempotency_key": {"type": "string"},
                },
                "required": ["title", "content", "category"],
                "additionalProperties": False,
            },
        },
    ]


def _json_rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _mcp_content_result(value: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False),
            }
        ],
        "isError": False,
    }


def _handle_mcp_message(message: dict[str, Any], mcp_key: str = "") -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}

    if method is None:
        return None
    if method == "initialize":
        return _json_rpc_result(
            request_id,
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "promptbanken-skill-router", "version": SERVICE_VERSION},
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _json_rpc_result(request_id, {})
    if method == "tools/list":
        return _json_rpc_result(request_id, {"tools": _tool_definitions()})
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        if tool_name == "list_skills":
            return _json_rpc_result(request_id, _mcp_content_result(
                [skill.to_dict() for skill in _all_skills(mcp_key)]
            ))
        if tool_name == "check_input_risk":
            text = arguments.get("text")
            if not isinstance(text, str):
                return _json_rpc_error(request_id, -32602, "Invalid check_input_risk arguments")
            return _json_rpc_result(request_id, _mcp_content_result(risk_checker.check(text).to_dict()))
        if tool_name == "list_skills_simple":
            return _json_rpc_result(request_id, _mcp_content_result(_list_skills_simple_payload(mcp_key)))
        if tool_name == "get_skill":
            skill_id = arguments.get("skill_id")
            include_prompt = arguments.get("include_prompt", True)
            if not isinstance(skill_id, str) or not isinstance(include_prompt, bool):
                return _json_rpc_error(request_id, -32602, "Invalid get_skill arguments")
            if not repository.is_valid_skill_id(skill_id):
                return _json_rpc_result(request_id, _mcp_content_result(
                    _error("INVALID_SKILL_ID", "Skill id contains invalid characters")
                ))
            try:
                skill, prompt = _get_skill_and_prompt(skill_id, include_prompt, mcp_key)
            except KeyError:
                return _json_rpc_result(request_id, _mcp_content_result(
                    _error("SKILL_NOT_FOUND", "Skill not found")
                ))
            return _json_rpc_result(request_id, _mcp_content_result(
                skill.to_dict(include_prompt=include_prompt, prompt=prompt)
            ))
        if tool_name == "health_check":
            return _json_rpc_result(request_id, _mcp_content_result(_health_check_payload(mcp_key)))
        if tool_name == "get_client_routing_instructions":
            return _json_rpc_result(request_id, _mcp_content_result(get_client_routing_instructions()))
        if tool_name == "list_pro_templates":
            return _json_rpc_result(request_id, _mcp_content_result(_pro_templates_payload(mcp_key)))
        if tool_name == "list_my_prompts":
            return _json_rpc_result(request_id, _mcp_content_result(_my_prompts_payload(mcp_key)))
        if tool_name == "list_my_private_prompts":
            return _json_rpc_result(request_id, _mcp_content_result(_my_private_prompts_payload(mcp_key)))
        if tool_name == "list_my_shared_workspaces":
            return _json_rpc_result(request_id, _mcp_content_result(_my_shared_workspaces_payload(mcp_key)))
        if tool_name == "list_shared_workspace_prompts":
            workspace_id = arguments.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                return _json_rpc_error(request_id, -32602, "Invalid list_shared_workspace_prompts arguments")
            return _json_rpc_result(
                request_id, _mcp_content_result(_shared_workspace_prompts_payload(mcp_key, workspace_id))
            )
        if tool_name == "save_workspace_prompt":
            title = arguments.get("title")
            content = arguments.get("content")
            category = arguments.get("category")
            source = arguments.get("source", "manual")
            risk_check_passed = arguments.get("risk_check_passed", False)
            idempotency_key = arguments.get("idempotency_key")
            if not all(isinstance(v, str) and v for v in (title, content, category)):
                return _json_rpc_error(request_id, -32602, "Invalid save_workspace_prompt arguments")
            if not isinstance(risk_check_passed, bool):
                return _json_rpc_error(request_id, -32602, "risk_check_passed must be a boolean")
            return _json_rpc_result(
                request_id,
                _mcp_content_result(
                    _save_workspace_prompt_payload(
                        mcp_key, title, content, category, source, risk_check_passed, idempotency_key
                    )
                ),
            )
        return _json_rpc_error(request_id, -32601, "Tool not found")
    return _json_rpc_error(request_id, -32601, "Method not found")


async def _mcp_streamable_http(request: Request) -> Response:
    if request.method == "GET":
        logger.info("http_request path=/mcp method=GET status=405")
        return Response(status_code=405, headers={"Allow": "POST"})
    if request.method == "DELETE":
        logger.info("http_request path=/mcp method=DELETE status=405")
        return Response(status_code=405, headers={"Allow": "POST"})

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        logger.info("http_request path=/mcp method=POST status=400 result=invalid_json")
        return JSONResponse(_json_rpc_error(None, -32700, "Parse error"), status_code=400)

    is_batch = isinstance(payload, list)
    messages = payload if is_batch else [payload]
    if not all(isinstance(message, dict) for message in messages):
        logger.info("http_request path=/mcp method=POST status=400 result=invalid_message_shape")
        return JSONResponse(_json_rpc_error(None, -32600, "Invalid Request"), status_code=400)

    mcp_key = _mcp_key_from_request(request)
    responses = [response for message in messages if (response := _handle_mcp_message(message, mcp_key)) is not None]
    logger.info("http_request path=/mcp method=POST status=%s batch=%s", 200 if responses else 202, is_batch)
    if not responses:
        return Response(status_code=202)
    return JSONResponse(responses if is_batch else responses[0])


class OriginValidationMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            headers = dict(scope.get("headers") or [])
            origin = headers.get(b"origin", b"").decode("utf-8")
            allowed_origins = _allowed_origins()
            if origin and allowed_origins and origin not in allowed_origins:
                logger.warning("origin_denied path=/mcp origin_present=true")
                response = JSONResponse({"detail": "Origin not allowed"}, status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class BearerAuthMiddleware:
    # Global på/av-spärr för hela servern via PROMPTBANKEN_MCP_API_KEY. När den är
    # satt krävs exakt "Bearer <global_nyckel>" på alla paths utom /healthz, vilket
    # gör servern helt privat. OBS: detta är ömsesidigt uteslutande med per-användares
    # workspace-nycklar som skickas via Authorization (se _mcp_key_from_request) —
    # sätt inte den globala nyckeln om workspace-nycklar via Authorization ska funka.
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        token = _api_key()
        if scope.get("type") == "http" and token and scope.get("path") != "/healthz":
            headers = dict(scope.get("headers") or [])
            authorization = headers.get(b"authorization", b"").decode("utf-8")
            if not hmac.compare_digest(authorization, f"Bearer {token}"):
                logger.warning("auth_denied path=%s", scope.get("path"))
                response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class HostedMetadataGuardMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.guard = HostedMetadataGuard(repository)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        guarded_path = scope.get("path")
        if SERVER_MODE != "hosted" or scope.get("type") != "http" or guarded_path not in {"/messages/", "/mcp"}:
            await self.app(scope, receive, send)
            return

        body_parts: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") != "http.request":
                continue
            body_parts.append(message.get("body", b""))
            more_body = bool(message.get("more_body", False))

        body = b"".join(body_parts)
        warning = self.guard.inspect_body(body)
        if warning is not None:
            logger.warning(
                "hosted_payload_warning path=%s reason=%s method=%s tool=%s",
                guarded_path,
                warning["reason"],
                warning.get("method", "unknown"),
                warning.get("tool", "unknown"),
            )
            if HOSTED_GUARD_MODE == "block":
                response = JSONResponse(
                    _json_rpc_error(
                        warning.get("id"),
                        -32602,
                        "Hosted MCP only accepts metadata requests. Do not send user text.",
                        {
                            "code": "HOSTED_METADATA_ONLY",
                            "safe_to_show_user": True,
                        },
                    ),
                    status_code=200,
                )
                await response(scope, receive, send)
                return

        async def replay_receive() -> dict[str, Any]:
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        await self.app(scope, replay_receive, send)

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
            Route("/openapi.json", endpoint=_openapi),
            Route("/api/v1/skills", endpoint=_api_list_skills),
            Route("/api/v1/skills/simple", endpoint=_api_list_skills_simple),
            Route("/api/v1/skills/{skill_id}", endpoint=_api_get_skill),
            Route("/api/v1/skills/{skill_id}/prompt", endpoint=_api_get_skill_prompt),
            Route("/api/v1/routing-instructions", endpoint=_api_routing_instructions),
            Route("/api/v1/pro-templates", endpoint=_api_pro_templates),
            Route("/api/v1/my-prompts", endpoint=_api_my_prompts, methods=["GET"]),
            Route("/api/v1/my-prompts", endpoint=_api_save_workspace_prompt, methods=["POST"]),
            Route("/api/v1/my-private-prompts", endpoint=_api_my_private_prompts),
            Route("/api/v1/my-shared-workspaces", endpoint=_api_my_shared_workspaces),
            Route("/api/v1/shared-workspaces/{workspace_id}/prompts", endpoint=_api_shared_workspace_prompts),
            Route("/mcp", endpoint=_mcp_streamable_http, methods=["GET", "POST", "DELETE"]),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )
    app = OriginValidationMiddleware(BearerAuthMiddleware(HostedMetadataGuardMiddleware(app)))
    logger.info(
        "http_server_start host=%s port=%s mode=%s hosted_guard=%s",
        mcp.settings.host,
        mcp.settings.port,
        SERVER_MODE,
        HOSTED_GUARD_MODE,
    )
    if _api_key():
        logger.warning(
            "global_bearer_enabled PROMPTBANKEN_MCP_API_KEY ar satt: hela servern kraver "
            "Bearer <global_nyckel> (utom /healthz). Per-anvandares workspace-nycklar via "
            "Authorization slutar da fungera (se BearerAuthMiddleware). Lamna tom for oppet lage."
        )

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


@mcp.tool()
def save_workspace_prompt(
    title: str,
    content: str,
    category: str,
    source: str = "manual",
    risk_check_passed: bool = False,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Save a generalised, already GDPR-checked template into the caller's
    personal Pro workspace. IMPORTANT for the calling model: generalise the
    content (remove names/personal numbers/org-specific details) and run
    check_input_risk on the generated template BEFORE calling this tool. Show
    the proposal to the user and wait for explicit approval before calling.
    Set risk_check_passed=true only after the approved check -- calls with
    risk_check_passed=false are rejected. Generate your own idempotency_key
    (UUID) per approval so a retry after a timeout never creates a duplicate.
    Suggested categories (optional, not enforced): kommunikation,
    forandringsledning, processer, beslutsberedning, visuellt, ledarskap,
    arbetsbank. Requires a Pro key (X-MCP-Key/Authorization); free keys are
    rejected."""
    logger.info("tool_call name=save_workspace_prompt")
    return _save_workspace_prompt_payload(
        "", title, content, category, source, risk_check_passed, idempotency_key
    )


if __name__ == "__main__":
    run_stdio()
