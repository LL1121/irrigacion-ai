"""Normalización de respuestas → texto humano para todos los tipos de skill."""

from __future__ import annotations

import unittest

from app.services.response_normalize import (
    classify_skill_payload,
    humanize_skill_payload,
    looks_raw_technical,
    normalize_assistant_reply,
)


class ResponseNormalizeTests(unittest.TestCase):
    def test_telemetria(self):
        data = {
            "ok": True,
            "punto": "10009",
            "nombre": "10009 - Canal Matriz Cañada Colorada - Dique",
            "fecha": "2026-08-12T21:00:00-03:00",
            "altura": {"valor": 4.08, "unidad": "cm"},
            "caudal": {"valor": 77.65, "unidad": "l/s"},
            "mediciones": [],
            "api_url": "https://x",
        }
        self.assertEqual(classify_skill_payload(data), "telemetria")
        text = humanize_skill_payload(
            user_message="cuanta altura hay en el punto 10009",
            skill_data=data,
        )
        assert text is not None
        self.assertIn("4.08", text)
        self.assertIn("cm", text)
        self.assertNotIn("api_url", text)
        self.assertFalse(looks_raw_technical(text))

    def test_caudal(self):
        data = {
            "area_m2": 2.5,
            "velocidad_ms": 0.8,
            "caudal_m3s": 2.0,
            "caudal_ls": 2000.0,
            "formula": "Q = A * v",
        }
        text = humanize_skill_payload(user_message="calculame el caudal", skill_data=data)
        assert text is not None
        self.assertIn("L/s", text)
        self.assertIn("2.5", text)

    def test_conversion(self):
        data = {
            "entrada": {"valor": 100, "unidad": "l/s"},
            "m3_s": 0.1,
            "l_s": 100,
            "m3_h": 360,
            "m3_dia": 8640,
        }
        text = humanize_skill_payload(user_message="convertí 100 l/s", skill_data=data)
        assert text is not None
        self.assertIn("L/s", text)
        self.assertIn("m³/día", text)

    def test_prorrateo(self):
        data = {
            "total": 100,
            "suma_pesos": 10,
            "asignaciones": [
                {"nombre": "A", "peso": 2, "proporcion": 0.2, "asignado": 20},
                {"nombre": "B", "peso": 8, "proporcion": 0.8, "asignado": 80},
            ],
        }
        text = humanize_skill_payload(user_message="prorrateá", skill_data=data)
        assert text is not None
        self.assertIn("A", text)
        self.assertIn("20", text)

    def test_lamina(self):
        data = {
            "volumen_m3": 1200,
            "superficie_ha": 2.5,
            "superficie_m2": 25000,
            "lamina_mm": 48.0,
        }
        text = humanize_skill_payload(user_message="lámina", skill_data=data)
        assert text is not None
        self.assertIn("48", text)
        self.assertIn("mm", text)

    def test_tiempo(self):
        data = {
            "volumen_m3": 100,
            "caudal_ls": 50,
            "tiempo_h": 0.5556,
            "tiempo_hm": {"horas": 0, "minutos": 33},
        }
        text = humanize_skill_payload(user_message="tiempo de riego", skill_data=data)
        assert text is not None
        self.assertIn("33", text)

    def test_normalize_strips_raw_json_reply(self):
        raw = (
            "Ejecuté 'Telemetría' para: x\n\nResultado:\n"
            '{"success": true, "result": {"ok": true, "punto": "10009", '
            '"altura": {"valor": 4.08, "unidad": "cm"}, "caudal": {"valor": 1, "unidad": "l/s"}, '
            '"mediciones": [], "api_url": "https://x"}}'
        )
        out = normalize_assistant_reply(
            raw,
            user_message="altura punto 10009",
            sanitized_payload={
                "success": True,
                "result": {
                    "ok": True,
                    "punto": "10009",
                    "altura": {"valor": 4.08, "unidad": "cm"},
                    "caudal": {"valor": 1, "unidad": "l/s"},
                    "mediciones": [],
                },
            },
        )
        self.assertNotIn("Ejecuté", out)
        self.assertNotIn("{", out)
        self.assertIn("4.08", out)


if __name__ == "__main__":
    unittest.main()
