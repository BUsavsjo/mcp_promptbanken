import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.catalog_renderer import render_template_variant
from server.mcp_server import _catalog_prompt_to_template


class CatalogRendererTests(unittest.TestCase):
    def test_renders_global_bindings_and_context_override(self) -> None:
        variant = {
            "prompt_text": "Skriv ett {{ton}} svar till {{malgrupp}}. Du är {{roll}} i {{kontext}}.",
            "parameter_schema": {
                "fields": [
                    {"key": "kontext", "source": "global"},
                    {"key": "roll", "source": "global"},
                    {"key": "malgrupp", "source": "global"},
                    {"key": "ton", "source": "global"},
                ]
            },
            "default_bindings": {
                "roll": "handläggare",
                "malgrupp": "invånare",
                "ton": "tydligt och vänligt",
            },
            "binding_overrides": [
                {"when": {"kontext": "företag"}, "set": {"malgrupp": "företagare"}}
            ],
        }

        rendered = render_template_variant(
            variant,
            {
                "kontext": "företag",
                "roll": "handläggare",
                "malgrupp": "invånare",
                "ton": "formellt",
            },
        )

        self.assertEqual(
            rendered,
            "Skriv ett formellt svar till företagare. Du är handläggare i företag.",
        )

    def test_catalog_prompt_payload_includes_rendered_prompt_text(self) -> None:
        payload = _catalog_prompt_to_template(
            {
                "id": "123",
                "slug": "mejl",
                "title": "Svar på medborgarmejl",
                "summary": "Skriv svar.",
                "prompt_text": "Skriv ett {{ton}} svar till {{malgrupp}}.",
                "context_key": "generell",
                "parameter_schema": {
                    "fields": [
                        {"key": "kontext", "source": "global"},
                        {"key": "malgrupp", "source": "global"},
                        {"key": "ton", "source": "global"},
                    ]
                },
                "default_bindings": {"malgrupp": "invånare", "ton": "formellt"},
                "binding_overrides": [
                    {"when": {"kontext": "företag"}, "set": {"malgrupp": "företagare"}}
                ],
            },
            {"kontext": "företag", "ton": "formellt"},
        )

        self.assertEqual(payload["rendered_prompt_text"], "Skriv ett formellt svar till företagare.")


if __name__ == "__main__":
    unittest.main()
