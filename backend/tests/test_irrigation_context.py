"""Memoria base institucional y pipeline de ingesta oficial."""

from __future__ import annotations

import unittest

from app.core.irrigation_context import CORE_IRRIGATION_KNOWLEDGE

try:
    from app.services.official_ingest import clean_html, document_name_for_official

    _HAS_OFFICIAL_INGEST = True
except ImportError:
    _HAS_OFFICIAL_INGEST = False


class IrrigationContextTests(unittest.TestCase):
    def test_core_knowledge_includes_institution_and_glossary(self):
        blob = CORE_IRRIGATION_KNOWLEDGE.lower()
        self.assertIn("jefatura de zona de riego", blob)
        self.assertIn("dotación", blob)
        self.assertIn("lámina de riego", blob)
        self.assertIn("prorrateo", blob)
        self.assertIn("honorable tribunal", blob)
        self.assertIn("ley general de aguas", blob)
        self.assertIn("inseparabilidad", blob)

    def test_core_mentions_ingest_tool(self):
        self.assertIn("ingest_official_url", CORE_IRRIGATION_KNOWLEDGE)


@unittest.skipUnless(_HAS_OFFICIAL_INGEST, "dependencias de ingesta oficial no instaladas")
class OfficialIngestHtmlTests(unittest.TestCase):
    def test_clean_html_strips_nav_and_scripts(self):
        html = """
        <html><head><script>alert(1)</script></head><body>
        <nav>Menú</nav>
        <main><h1>Resolución 1</h1><p>Texto normativo útil.</p></main>
        <footer>Pie</footer>
        </body></html>
        """
        text = clean_html(html)
        self.assertIn("Resolución 1", text)
        self.assertIn("Texto normativo", text)
        self.assertNotIn("Menú", text)
        self.assertNotIn("alert", text)

    def test_document_name_slug(self):
        name = document_name_for_official("Resolución 123/2024 — Turno Verano")
        self.assertTrue(name.startswith("oficial:normativa:"))
        self.assertNotIn(" ", name)


if __name__ == "__main__":
    unittest.main()
