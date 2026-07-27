import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.catalog_renderer import render_template_variant
from server.mcp_server import _catalog_prompt_to_template


class CatalogRendererTests(unittest.TestCase):
    # TODO(spec 2026-07-27 v2, Beslut 1): server-side rendering is being
    # removed entirely (open AND authenticated) -- render_template_variant()
    # is being decoupled from _catalog_prompt_to_template/_catalog_package_to_payload,
    # though catalog_renderer.py itself is not deleted this round. Invert/
    # remove this test (and the other 3 below) once that lands. See
    # test_open_catalog_read_only_contract.py::ReadOnlyCatalogPayloadContractTests.
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

    # TODO(spec 2026-07-27 v2, Beslut 1): see TODO above; this call chain is
    # being decoupled from the catalog payload functions. Invert/remove once
    # rendering is removed.
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

    # TODO(spec 2026-07-27 v2, Beslut 1): see TODO above; this call chain is
    # being decoupled from the catalog payload functions. Invert/remove once
    # rendering is removed.
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

    # TODO(spec 2026-07-27 v2, Beslut 1): this test directly asserts the
    # rendered_prompt_text field on the catalog payload -- the field being
    # removed. Invert/remove once _catalog_prompt_to_template stops calling
    # render_template_variant. See
    # test_open_catalog_read_only_contract.py::ReadOnlyCatalogPayloadContractTests
    # for the red test that already asserts rendered_prompt_text is ABSENT.
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
