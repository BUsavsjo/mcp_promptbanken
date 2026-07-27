import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.catalog_renderer import render_template_variant


class CatalogRendererTests(unittest.TestCase):
    """catalog_renderer.py is kept as a standalone, unused-for-now reference
    module (spec 2026-07-27 v2, Beslut 1) -- it is decoupled from the catalog
    payload path but not deleted, because it is the only place with working
    tone-inflection logic (ton_neutrum). These tests exercise the module's
    pure functions directly and remain valid."""

    def test_renders_tone_with_the_grammatical_form_required_by_the_sentence(self) -> None:
        variant = {
            "prompt_text": "Skriv ett {{ton}} svar med en {{ton}} stil.",
            "parameter_schema": {
                "fields": [{"key": "ton", "source": "global"}],
            },
            "default_bindings": {"ton": "tydlig och vänlig"},
        }

        self.assertEqual(
            render_template_variant(variant),
            "Skriv ett tydligt och vänligt svar med en tydlig och vänlig stil.",
        )
        self.assertEqual(
            render_template_variant(variant, {"ton": "formellt"}),
            "Skriv ett formellt svar med en formell stil.",
        )

    def test_recomputes_tone_form_after_a_context_override(self) -> None:
        variant = {
            "prompt_text": "Skriv ett {{ton}} svar.",
            "parameter_schema": {
                "fields": [
                    {"key": "kontext", "source": "global"},
                    {"key": "ton", "source": "global"},
                ],
            },
            "default_bindings": {"ton": "tydlig och vänlig"},
            "binding_overrides": [
                {"when": {"kontext": "skola"}, "set": {"ton": "pedagogisk"}}
            ],
        }

        self.assertEqual(
            render_template_variant(variant, {"kontext": "skola"}),
            "Skriv ett pedagogiskt svar.",
        )

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


if __name__ == "__main__":
    unittest.main()
