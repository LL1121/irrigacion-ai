"""Guards anti-flash: nunca aceptar skills meta 'Descargar Skill'."""

from __future__ import annotations

import unittest

from app.services.skill_marketplace import (
    conversation_context_text,
    has_actionable_remote_task,
    is_download_confirmation_only,
    is_result_challenge_or_correction,
    is_telemetria_request,
    looks_like_web_or_external_request,
    resolve_effective_remote_task,
    resolve_skill_decision,
)
from app.services.skill_remote import (
    generate_remote_skill,
    remote_skill_rejection_reason,
    validate_remote_skill,
)


class RemoteSkillGuardTests(unittest.TestCase):
    def test_download_confirmation_only_detection(self):
        self.assertTrue(is_download_confirmation_only("si, descargá la skill"))
        self.assertTrue(is_download_confirmation_only("sí, descargar la skill"))
        self.assertTrue(is_download_confirmation_only("Dale, descargá la skill."))
        self.assertFalse(
            is_download_confirmation_only(
                "Descargá una skill para consultar altura del punto 10009"
            )
        )
        self.assertFalse(
            is_download_confirmation_only(
                "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil"
            )
        )

    def test_resolve_effective_task_from_history(self):
        hist_text = conversation_context_text(
            "si, descargá la skill",
            [
                {
                    "role": "user",
                    "message": (
                        "altura y caudal punto 10009\n"
                        "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil"
                    ),
                }
            ],
        )
        effective = resolve_effective_remote_task("si, descargá la skill", hist_text)
        self.assertIn("10009", effective)
        self.assertIn("telemetria", effective.lower())
        self.assertTrue(has_actionable_remote_task(effective))

    def test_confirm_without_task_asks_clarify(self):
        d = resolve_skill_decision(
            "si, descargá la skill", context_text="si, descargá la skill"
        )
        self.assertEqual(d["action"], "clarify")
        self.assertEqual(d["reason"], "download_confirm_without_task")

    def test_confirm_with_history_downloads(self):
        ctx = (
            "necesito altura punto 10009\n"
            "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil\n\n"
            "si, descargá la skill"
        )
        d = resolve_skill_decision("si, descargá la skill", context_text=ctx)
        self.assertEqual(d["action"], "download")

    def test_reject_meta_download_skill_payload(self):
        reason = remote_skill_rejection_reason(
            skill_id="remote_descargar_skill",
            name="Descargar Skill",
            description="Descarga la skill solicitada",
            code=(
                "def run(input_data):\n"
                "    return {'ok': True, 'mensaje': 'Skill descargada con éxito'}\n"
            ),
            task="si, descargá la skill",
        )
        self.assertIsNotNone(reason)
        with self.assertRaises(RuntimeError):
            validate_remote_skill(
                {
                    "id": "remote_descargar_skill",
                    "name": "Descargar Skill",
                    "description": "Descarga la skill solicitada",
                    "code": (
                        "def run(input_data):\n"
                        "    return {'ok': True, 'mensaje': 'Skill descargada con éxito'}\n"
                    ),
                },
                "si, descargá la skill",
            )

    def test_generate_from_confirm_uses_telemetria_template(self):
        ctx = (
            "altura y caudal del punto 10009 "
            "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil"
        )
        skill = generate_remote_skill("si, descargá la skill", conversation_context=ctx)
        self.assertEqual(skill.get("template"), "telemetria_fullDto")
        self.assertNotIn("Descargar", skill["name"])
        self.assertIn("fetch_url", skill["code"])
        validate_remote_skill(skill, ctx)

    def test_generate_confirm_only_without_context_fails(self):
        with self.assertRaises(RuntimeError):
            generate_remote_skill(
                "si, descargá la skill",
                conversation_context="si, descargá la skill",
            )


    def test_challenge_does_not_restart_web_flow(self):
        msg = "De donde sacaste esa altura man? En la página dice 4cm"
        self.assertTrue(is_result_challenge_or_correction(msg))
        self.assertFalse(looks_like_web_or_external_request(msg))
        d = resolve_skill_decision(
            msg,
            context_text=(
                "altura punto 10009\n"
                "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil\n\n"
                + msg
            ),
        )
        self.assertEqual(d["action"], "none")
        self.assertEqual(d["reason"], "thread_challenge")

    def test_clarify_only_asks_missing_fields(self):
        from app.services.skill_marketplace import clarifying_question_for_unknown

        probe = (
            "necesito la altura del punto 10009 "
            # falta URL
        )
        reply = clarifying_question_for_unknown(probe, context_text=probe)
        self.assertIn("URL", reply)
        self.assertNotIn("Código de punto", reply)  # ya está el 10009

    def test_url_followup_continues_thread(self):
        ctx = (
            "necesito altura y caudal, codigo del punto 10009\n\n"
            "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil"
        )
        d = resolve_skill_decision(
            "https://serviciosweb.cloud.irrigacion.gov.ar/public/telemetriaMovil",
            context_text=ctx,
        )
        self.assertEqual(d["action"], "download")


    def test_crawl_url_no_es_telemetria(self):
        from app.services.skill_marketplace import (
            is_site_crawl_request,
            is_telemetria_request,
            find_local_skill,
            skill_missing_required_inputs,
        )

        msg = (
            "escanear todos los subenlaces válidos del sitio "
            "https://www.irrigacion.gov.ar/web/"
        )
        self.assertTrue(is_site_crawl_request(msg))
        self.assertFalse(is_telemetria_request(msg))
        self.assertFalse(looks_like_web_or_external_request(msg))
        found = find_local_skill(msg)
        self.assertTrue(found.get("found"), found)
        self.assertEqual(found.get("id"), "crawl_domain_links")
        d = resolve_skill_decision(msg)
        self.assertEqual(d["action"], "execute")
        self.assertEqual((d.get("skill") or {}).get("id"), "crawl_domain_links")
        reply = (d.get("reply") or "").lower()
        self.assertNotIn("estación", reply)
        self.assertNotIn("estacion", reply)
        self.assertNotIn("punto", reply)
        self.assertEqual(
            skill_missing_required_inputs(
                d["skill"],
                d["skill"].get("arguments") or {},
                user_message=msg,
            ),
            [],
        )

    def test_irrigacion_gov_sin_telemetria_no_pide_punto(self):
        from app.services.skill_marketplace import clarifying_question_for_unknown

        msg = "mirá este comunicado https://www.irrigacion.gov.ar/web/"
        self.assertFalse(is_telemetria_request(msg))
        reply = clarifying_question_for_unknown(msg, context_text=msg)
        self.assertNotIn("punto/estación", reply.lower())
        self.assertNotIn("código de punto", reply.lower())

    def test_telemetria_explicita_sigue_pidiendo_punto(self):
        from app.services.skill_marketplace import clarifying_question_for_unknown

        probe = "necesito la telemetría de la estación, altura del sensor"
        reply = clarifying_question_for_unknown(probe, context_text=probe)
        self.assertIn("punto", reply.lower())


if __name__ == "__main__":
    unittest.main()

