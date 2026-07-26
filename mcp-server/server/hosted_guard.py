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
            "list_templates",
            "search_templates",
            "get_template",
            "list_packages",
            "get_package",
            "list_package_prompts",
            "list_my_prompts",
            "list_my_private_prompts",
            "list_my_shared_workspaces",
            "list_shared_workspace_prompts",
            "check_input_risk",
            "save_workspace_prompt",
            "list_my_items",
            "search_my_items",
            "get_my_item",
            "save_my_item",
            "update_my_item",
            "archive_my_item",
            "list_active_packages",
            "activate_package",
            "deactivate_package",
            "copy_template_to_valvet",
            "recommend_packages",
        }
        self.allowed_tool_args = {
            "list_skills": set(),
            "list_skills_simple": set(),
            "health_check": set(),
            "get_client_routing_instructions": set(),
            "list_templates": {"context_keys"},
            "search_templates": {"query", "role", "area", "risk_level", "limit", "context_keys"},
            "get_template": {"template_id", "context_keys", "role", "audience", "tone", "input_text"},
            "list_packages": {"context_keys", "package_type"},
            "get_package": {"package_slug", "context_keys", "role", "audience", "tone", "input_text"},
            "list_package_prompts": {"package_slug", "context_keys", "role", "audience", "tone", "input_text"},
            "list_my_prompts": set(),
            "list_my_private_prompts": set(),
            "list_my_shared_workspaces": set(),
            "list_shared_workspace_prompts": {"workspace_id"},
            "get_skill": {"skill_id", "include_prompt"},
            "check_input_risk": {"text"},
            "save_workspace_prompt": {
                "title", "content", "category", "source", "risk_check_passed", "idempotency_key"
            },
            "list_my_items": {"type", "category", "status"},
            "search_my_items": {"query", "type", "category"},
            "get_my_item": {"id"},
            "save_my_item": {"idempotency_key", "type", "title", "content", "category"},
            "update_my_item": {"id", "expected_updated_at", "title", "content", "category"},
            "archive_my_item": {"id", "confirm", "restore"},
            "list_active_packages": set(),
            "activate_package": {"area"},
            "deactivate_package": {"area"},
            "copy_template_to_valvet": {"template_id", "confirm"},
            "recommend_packages": {"role"},
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
        if tool_name == "get_skill":
            skill_id = arguments.get("skill_id")
            include_prompt = arguments.get("include_prompt")
            if not isinstance(skill_id, str) or not self.repository.is_valid_skill_id(skill_id):
                return {"reason": "invalid_skill_id", "method": method, "tool": tool_name, "id": request_id}
            if include_prompt is not None and not isinstance(include_prompt, bool):
                return {"reason": "invalid_include_prompt", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "list_shared_workspace_prompts":
            workspace_id = arguments.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id:
                return {"reason": "invalid_workspace_id", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "check_input_risk":
            text = arguments.get("text")
            if not isinstance(text, str):
                return {"reason": "invalid_text", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "save_workspace_prompt":
            title = arguments.get("title")
            content = arguments.get("content")
            category = arguments.get("category")
            if not all(isinstance(v, str) and v for v in (title, content, category)):
                return {"reason": "invalid_save_arguments", "method": method, "tool": tool_name, "id": request_id}
            risk_check_passed = arguments.get("risk_check_passed")
            if risk_check_passed is not None and not isinstance(risk_check_passed, bool):
                return {"reason": "invalid_risk_check_passed", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "list_my_items":
            pass
        elif tool_name == "search_my_items":
            query = arguments.get("query")
            if not isinstance(query, str) or not query:
                return {"reason": "invalid_query", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "get_my_item":
            item_id = arguments.get("id")
            if not isinstance(item_id, str) or not item_id:
                return {"reason": "invalid_item_id", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "save_my_item":
            idempotency_key = arguments.get("idempotency_key")
            item_type = arguments.get("type")
            title = arguments.get("title")
            content = arguments.get("content")
            if not all(isinstance(v, str) and v for v in (idempotency_key, item_type, title, content)):
                return {"reason": "invalid_save_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
            category = arguments.get("category")
            if category is not None and not isinstance(category, str):
                return {"reason": "invalid_save_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "update_my_item":
            item_id = arguments.get("id")
            expected_updated_at = arguments.get("expected_updated_at")
            if not all(isinstance(v, str) and v for v in (item_id, expected_updated_at)):
                return {"reason": "invalid_update_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
            optional_values = (arguments.get("title"), arguments.get("content"), arguments.get("category"))
            if not all(value is None or isinstance(value, str) for value in optional_values):
                return {"reason": "invalid_update_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "archive_my_item":
            item_id = arguments.get("id")
            confirm = arguments.get("confirm")
            restore = arguments.get("restore", False)
            if not isinstance(item_id, str) or not item_id or not isinstance(confirm, bool):
                return {"reason": "invalid_archive_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
            if not isinstance(restore, bool):
                return {"reason": "invalid_archive_my_item_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "list_active_packages":
            pass
        elif tool_name in ("activate_package", "deactivate_package"):
            area = arguments.get("area")
            if not isinstance(area, str) or not area:
                return {"reason": "invalid_area", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "copy_template_to_valvet":
            template_id = arguments.get("template_id")
            confirm = arguments.get("confirm")
            if not isinstance(template_id, str) or not template_id or not isinstance(confirm, bool):
                return {"reason": "invalid_copy_template_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "recommend_packages":
            role = arguments.get("role")
            if not isinstance(role, str) or not role:
                return {"reason": "invalid_role", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "search_templates":
            for key in ("query", "role", "area", "risk_level"):
                value = arguments.get(key)
                if value is not None and not isinstance(value, str):
                    return {"reason": "invalid_search_templates_arguments", "method": method, "tool": tool_name, "id": request_id}
            limit = arguments.get("limit")
            if limit is not None and not isinstance(limit, int):
                return {"reason": "invalid_search_templates_arguments", "method": method, "tool": tool_name, "id": request_id}
            context_keys = arguments.get("context_keys")
            if context_keys is not None and (
                not isinstance(context_keys, list)
                or not all(isinstance(item, str) for item in context_keys)
            ):
                return {"reason": "invalid_search_templates_arguments", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "get_template":
            template_id = arguments.get("template_id")
            if not isinstance(template_id, str) or not template_id:
                return {"reason": "invalid_template_id", "method": method, "tool": tool_name, "id": request_id}
            for key in ("role", "audience", "tone", "input_text"):
                value = arguments.get(key)
                if value is not None and not isinstance(value, str):
                    return {"reason": "invalid_template_render_arguments", "method": method, "tool": tool_name, "id": request_id}
            context_keys = arguments.get("context_keys")
            if context_keys is not None and (
                not isinstance(context_keys, list)
                or not all(isinstance(item, str) for item in context_keys)
            ):
                return {"reason": "invalid_template_id", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "list_templates":
            context_keys = arguments.get("context_keys")
            if context_keys is not None and (
                not isinstance(context_keys, list)
                or not all(isinstance(item, str) for item in context_keys)
            ):
                return {"reason": "invalid_context_keys", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name == "list_packages":
            package_type = arguments.get("package_type")
            if package_type is not None and not isinstance(package_type, str):
                return {"reason": "invalid_package_type", "method": method, "tool": tool_name, "id": request_id}
            context_keys = arguments.get("context_keys")
            if context_keys is not None and (
                not isinstance(context_keys, list)
                or not all(isinstance(item, str) for item in context_keys)
            ):
                return {"reason": "invalid_context_keys", "method": method, "tool": tool_name, "id": request_id}
        elif tool_name in ("get_package", "list_package_prompts"):
            package_slug = arguments.get("package_slug")
            if not isinstance(package_slug, str) or not package_slug:
                return {"reason": "invalid_package_slug", "method": method, "tool": tool_name, "id": request_id}
            for key in ("role", "audience", "tone", "input_text"):
                value = arguments.get(key)
                if value is not None and not isinstance(value, str):
                    return {"reason": "invalid_package_render_arguments", "method": method, "tool": tool_name, "id": request_id}
            context_keys = arguments.get("context_keys")
            if context_keys is not None and (
                not isinstance(context_keys, list)
                or not all(isinstance(item, str) for item in context_keys)
            ):
                return {"reason": "invalid_context_keys", "method": method, "tool": tool_name, "id": request_id}
        elif arguments:
            return {"reason": "unexpected_arguments", "method": method, "tool": tool_name, "id": request_id}
        return None
