"""Tests for aix_parser.py -- stdlib unittest, no third-party dependencies."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aix_parser import AIXEnvelope, AIXMemory, CONTENT_FIELDS


class TestAIXMemory(unittest.TestCase):
    def test_create_minimal(self):
        mem = AIXMemory(source="apple_notes", role="founder", content={"text": "Shipped v0.1."})
        self.assertEqual(mem.source, "apple_notes")
        self.assertEqual(mem.role, "founder")
        self.assertEqual(mem.content["text"], "Shipped v0.1.")
        self.assertTrue(mem.id)
        self.assertEqual(mem.tier, "stm")
        self.assertFalse(mem.pii_protected)
        self.assertIsNone(mem.epic_score)
        self.assertIsNone(mem.verification_score)
        # timestamp debe ser ISO8601 parseable
        datetime.fromisoformat(mem.timestamp)

    def test_set_trace(self):
        mem = AIXMemory(source="keyboard", role="creator", content={"text": "x"})
        mem.set_trace(lat=41.3874, lon=2.1686, location_name="Barcelona, Spain", device_type="laptop")
        self.assertEqual(mem.trace["latitude"], 41.3874)
        self.assertEqual(mem.trace["longitude"], 2.1686)
        self.assertEqual(mem.trace["location_name"], "Barcelona, Spain")
        self.assertEqual(mem.trace["device_type"], "laptop")
        with self.assertRaises(ValueError):
            mem.set_trace(lat=0, lon=0, location_name=None, device_type="toaster")

    def test_set_scores_valid(self):
        mem = AIXMemory(source="safari_history", role="researcher", content={"text": "x"})
        mem.set_scores(epic_score=0.65, verification_score=0.72)
        self.assertEqual(mem.epic_score, 0.65)
        self.assertEqual(mem.verification_score, 0.72)

    def test_to_dict_required_fields(self):
        mem = AIXMemory(source="apple_notes", role="founder", content={"text": "x"})
        d = mem.to_dict()
        for campo in (
            "id",
            "timestamp",
            "source",
            "role",
            "tier",
            "epic_score",
            "verification_score",
            "pii_protected",
            "content",
            "embeddings",
            "trace",
        ):
            self.assertIn(campo, d)
        for campo in CONTENT_FIELDS:
            self.assertIn(campo, d["content"])

    def test_from_dict_roundtrip(self):
        original = AIXMemory(
            source="apple_notes",
            role="founder",
            content={"text": "Closed pre-seed.", "decisions": ["close pre-seed"]},
        )
        original.set_tier("ltm")
        original.set_scores(epic_score=0.8, verification_score=0.9)
        original.set_trace(lat=1.0, lon=2.0, location_name="Somewhere", device_type="mobile")

        reconstructed = AIXMemory.from_dict(original.to_dict())
        self.assertEqual(reconstructed.to_dict(), original.to_dict())


class TestAIXEnvelope(unittest.TestCase):
    def test_create_empty(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        self.assertEqual(env.subject_id, "s1")
        self.assertEqual(env.device_id, "d1")
        self.assertEqual(env.session_id, "sess1")
        self.assertEqual(env.substrate_version, "1.0")
        self.assertEqual(env.memories, [])
        # 'memories es lista (puede ser vacía)' -- AIX-SPEC.md 3.2: un
        # envelope sin memorias sigue siendo estructuralmente válido.
        is_valid, errors = env.validate()
        self.assertTrue(is_valid, errors)

    def test_add_memory(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))
        self.assertEqual(len(env.memories), 1)
        self.assertEqual(env.to_dict()["aix_envelope"]["memory_count"], 1)

    def test_checksum_changes_with_memory(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        checksum_antes = env.compute_checksum()
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))
        checksum_despues = env.compute_checksum()
        self.assertNotEqual(checksum_antes, checksum_despues)

    def test_to_json_valid(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))
        parsed = json.loads(env.to_json())
        self.assertEqual(parsed, env.to_dict())

    def test_from_json_roundtrip(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))
        env.set_permissions(read=["self"], write=["self"], share=["soma:org_1"])

        reloaded = AIXEnvelope.from_json(env.to_json())
        self.assertEqual(reloaded.subject_id, env.subject_id)
        self.assertEqual(reloaded.device_id, env.device_id)
        self.assertEqual(len(reloaded.memories), len(env.memories))
        self.assertEqual(reloaded.permissions, env.permissions)
        # Un envelope recién cargado, sin mutar, debe validar exactamente
        # igual que el original (mismo checksum declarado == recalculado).
        self.assertEqual(reloaded.validate(), env.validate())

    def test_aix_version_preserved_on_load_not_current_constant(self):
        """Regresión: from_dict()/to_dict() deben preservar el aix_version
        TAL COMO ESTABA en el archivo cargado, no pisarlo con la constante
        AIX_VERSION vigente del parser -- un archivo v0.1 cargado por un
        parser que hoy emite v0.2 tiene que seguir reportándose v0.1."""
        d = {"aix_envelope": {"aix_version": "0.1", "subject_id": "s1", "device_id": "d1"}, "memories": []}
        cargado = AIXEnvelope.from_dict(d)
        self.assertEqual(cargado.to_dict()["aix_envelope"]["aix_version"], "0.1")

        # Un envelope NUEVO (no cargado) sí usa la versión actual del módulo.
        import aix_parser

        nuevo = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        self.assertEqual(nuevo.to_dict()["aix_envelope"]["aix_version"], aix_parser.AIX_VERSION)

    def test_to_file_and_from_file(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))

        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = str(Path(tmpdir) / "test.aix")
            env.to_file(ruta)
            self.assertTrue(Path(ruta).exists())

            reloaded = AIXEnvelope.from_file(ruta)
            self.assertEqual(reloaded.subject_id, env.subject_id)
            self.assertEqual(len(reloaded.memories), 1)
            is_valid, errors = reloaded.validate()
            self.assertTrue(is_valid, errors)

    def test_validate_passes_minimal(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="manual", role="user", content={"text": "minimal"}))
        is_valid, errors = env.validate()
        self.assertTrue(is_valid)
        self.assertEqual(errors, [])

    def test_validate_fails_missing_subject(self):
        env = AIXEnvelope(subject_id="", device_id="d1", session_id="sess1")
        is_valid, errors = env.validate()
        self.assertFalse(is_valid)
        self.assertTrue(any("subject_id" in e for e in errors))

    def test_validate_fails_bad_checksum(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        env.add_memory(AIXMemory(source="apple_notes", role="founder", content={"text": "x"}))

        d = env.to_dict()
        d["aix_envelope"]["checksum"] = "0" * 64  # checksum incorrecto a propósito
        tampered = AIXEnvelope.from_dict(d)

        is_valid, errors = tampered.validate()
        self.assertFalse(is_valid)
        self.assertTrue(any("checksum" in e for e in errors))

    def test_permissions_default(self):
        env = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
        self.assertEqual(env.permissions, {"read": ["self"], "write": ["self"], "share": []})


if __name__ == "__main__":
    unittest.main()
