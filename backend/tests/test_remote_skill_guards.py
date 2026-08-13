"""Guards anti-flash: nunca aceptar skills meta 'Descargar Skill'."""

from __future__ import annotations

import unittest

from app.services.skill_marketplace import (
    conversation_context_text,
    has_actionable_remote_task,
    is_download_confirmation_only,
    is_result_challenge_or_correction,
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


if __name__ == "__main__":
    unittest.main()

