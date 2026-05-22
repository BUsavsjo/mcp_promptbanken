from __future__ import annotations

import json
from typing import Any

from .skill_repository import SkillRepository


class HostedMetadataGuard:
    def __init__(self, repository: SkillRepository) -> None:
        self.repository = repository
        self.allowed_methods = {
            "initialize",
            "notifications/initialized",
            "notifications/cancelled",
            "ping",
            "resources/list",
            "tools/list",
            "tools/call",
            "list_skills",
            "list_skills_simple",
            "get_skill",
            "health_check",
            "get_client_routing_instructions",
        }
        self.allowed_tool_args = {
            "list_skills": set(),
            "list_skills_simple": set(),
            "health_check": set(),
            "get_client_routing_instructions": set(),
            "get_skill": {"skill_id", "include_prompt"},
        }

    def inspect_body(self, body: bytes) -> dict[str, Any] | None:
        if not body:
            return None
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"reason": "invalid_json"}

        messages = payload if isinstance(payload, list) else [payload]
        for message in messages:
            if not isinstance(message, dict):
                return {"reason": "invalid_message_shape"}
            warning = self.inspect_json_rpc_message(message)
            if warning is not None:
                return warning
        return None

    def inspect_json_rpc_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        if method is None:
            return None
        if method not in self.allowed_methods:
            return {"reason": "unexpected_method", "method": method, "id": request_id}
        if method in {"initialize", "notifications/initialized", "notifications/cancelled", "ping", "resources/list", "tools/list"}:
            return None
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, dict):
                return {"reason": "invalid_params", "method": method, "id": request_id}
            tool_name = params.get("name")
            if not isinstance(tool_name, str):
                return {"reason": "missing_tool_name", "method": method, "id": request_id}
            return self.inspect_tool_call(tool_name, params.get("arguments"), method, request_id)
        return self.inspect_direct_tool_call(method, message.get("params"), request_id)

    def inspect_direct_tool_call(self, tool_name: str, params: Any, request_id: Any) -> dict[str, Any] | None:
        if tool_name not in self.allowed_tool_args:
            return {"reason": "unexpected_tool", "method": tool_name, "tool": tool_name, "id": request_id}
        if params in (None, []):
            params = {}
        if not isinstance(params, dict):
            return {"reason": "invalid_tool_args", "method": tool_name, "tool": tool_name, "id": request_id}
        return self.inspect_tool_args(tool_name, params, tool_name, request_id)

    def inspect_tool_call(
        self,
        tool_name: str,
        arguments: Any,
        method: str,
        request_id: Any,
    ) -> dict[str, Any] | None:
        if tool_name not in self.allowed_tool_args:
            return {"reason": "unexpected_tool", "method": method, "tool": tool_name, "id": request_id}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {"reason": "invalid_tool_args", "method": method, "tool": tool_name, "id": request_id}
        return self.inspect_tool_args(tool_name, arguments, method, request_id)

    def inspect_tool_args(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        method: str,
        request_id: Any,
    ) -> dict[str, Any] | None:
        allowed_args = self.allowed_tool_args[tool_name]
        unexpected_args = set(arguments) - allowed_args
        if unexpected_args:
            return {"reason": "unexpected_arguments", "method": method, "tool": tool_name, "id": request_id}
        if tool_name != "get_skill" and arguments:
            return {"reason": "unexpected_arguments", "method": method, "tool": tool_name, "id": request_id}
        if tool_name == "get_skill":
            skill_id = arguments.get("skill_id")
            include_prompt = arguments.get("include_prompt")
            if not isinstance(skill_id, str) or not self.repository.is_valid_skill_id(skill_id):
                return {"reason": "invalid_skill_id", "method": method, "tool": tool_name, "id": request_id}
            if include_prompt is not None and not isinstance(include_prompt, bool):
                return {"reason": "invalid_include_prompt", "method": method, "tool": tool_name, "id": request_id}
        return None
