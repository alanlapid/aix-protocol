"""Tests for aix_delta.py -- stdlib unittest, no third-party dependencies."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aix_delta import AIXDelta
from aix_parser import AIXEnvelope, AIXMemory


def _envelope(subject_id: str = "s1") -> AIXEnvelope:
    return AIXEnvelope(subject_id=subject_id, device_id="d1", session_id="sess1")


def _memory(text: str, entities: list[str] | None = None) -> AIXMemory:
    return AIXMemory(source="apple_notes", role="founder", content={"text": text, "entities": entities or []})


def _identity(role: str, density: float = 0.0) -> dict:
    return {
        "roles": [{"role": role, "frequency": 1, "last_seen": ""}],
        "goals": [],
        "intentions": [],
        "graph_stats": {
            "entities": 0,
            "semantic_relations": 0,
            "causal_edges": 0,
            "graph_density": density,
            "life_events": 0,
        },
    }


class TestAIXDelta(unittest.TestCase):
    def test_delta_empty_envelopes(self):
        env_a = _envelope()
        env_b = _envelope()

        changes = AIXDelta(env_a, env_b).compute()

        self.assertEqual(changes["memories_added"], [])
        self.assertEqual(changes["memories_removed"], [])
        self.assertEqual(changes["roles_changed"], {"added": [], "removed": []})
        self.assertEqual(changes["entities_changed"], {"added": [], "removed": []})
        self.assertEqual(changes["verification_delta"], 0.0)
        self.assertEqual(changes["graph_density_delta"], 0.0)
        self.assertEqual(changes["summary"], "no changes")

    def test_delta_memory_added(self):
        env_a = _envelope()
        env_b = _envelope()
        nueva = _memory("A new memory in B.")
        env_b.add_memory(nueva)

        changes = AIXDelta(env_a, env_b).compute()

        self.assertEqual(changes["memories_added"], [nueva.id])
        self.assertEqual(changes["memories_removed"], [])

    def test_delta_memory_removed(self):
        env_a = _envelope()
        vieja = _memory("A memory only in A.")
        env_a.add_memory(vieja)
        env_b = _envelope()

        changes = AIXDelta(env_a, env_b).compute()

        self.assertEqual(changes["memories_removed"], [vieja.id])
        self.assertEqual(changes["memories_added"], [])

    def test_delta_roles_changed(self):
        env_a = _envelope()
        env_a.set_identity(**_identity("researcher"))
        env_b = _envelope()
        env_b.set_identity(**_identity("creator"))

        changes = AIXDelta(env_a, env_b).compute()

        self.assertEqual(changes["roles_changed"], {"added": ["creator"], "removed": ["researcher"]})

    def test_apply_delta(self):
        env_a = _envelope()
        mem_quedar = _memory("Stays in both.")
        mem_quitar = _memory("Removed in B.")
        env_a.add_memory(mem_quedar)
        env_a.add_memory(mem_quitar)
        env_a.set_identity(**_identity("researcher"))

        env_b = _envelope()
        # from_dict(to_dict()) para tener una copia INDEPENDIENTE del mismo
        # id, no la misma instancia -- simula que "sigue siendo la misma
        # memoria" entre dos snapshots, no que sea literalmente el mismo
        # objeto Python.
        env_b.add_memory(AIXMemory.from_dict(mem_quedar.to_dict()))
        mem_nueva = _memory("Added in B.")
        env_b.add_memory(mem_nueva)
        env_b.set_identity(**_identity("creator"))

        delta = AIXDelta(env_a, env_b)
        resultado = delta.apply(env_a)

        ids_resultado = {m.id for m in resultado.memories}
        self.assertEqual(ids_resultado, {mem_quedar.id, mem_nueva.id})
        self.assertNotIn(mem_quitar.id, ids_resultado)
        self.assertEqual([r["role"] for r in resultado.identity["active_roles"]], ["creator"])

        # apply() no muta 'base' -- env_a sigue con sus 2 memorias originales.
        self.assertEqual(len(env_a.memories), 2)

        is_valid, errors = resultado.validate()
        self.assertTrue(is_valid, errors)

    def test_from_history_three_versions(self):
        v0 = _envelope()
        v0.add_memory(_memory("v0 memory."))
        v0.set_identity(**_identity("researcher", density=0.1))

        v1 = _envelope()
        v1.add_memory(AIXMemory.from_dict(v0.memories[0].to_dict()))
        v1.add_memory(_memory("v1 new memory."))
        v1.set_identity(**_identity("creator", density=0.4))

        v2 = _envelope()
        v2.add_memory(AIXMemory.from_dict(v1.memories[1].to_dict()))
        v2.set_identity(**_identity("creator", density=0.9))

        deltas = AIXDelta.from_history([v0, v1, v2])

        self.assertEqual(len(deltas), 2)

        cambios_0_1 = deltas[0].compute()
        self.assertEqual(cambios_0_1["memories_added"], [v1.memories[1].id])
        self.assertEqual(cambios_0_1["roles_changed"], {"added": ["creator"], "removed": ["researcher"]})

        cambios_1_2 = deltas[1].compute()
        self.assertEqual(cambios_1_2["memories_removed"], [v1.memories[0].id])
        self.assertAlmostEqual(cambios_1_2["graph_density_delta"], 0.5, places=4)

    def test_from_history_fewer_than_two_returns_empty(self):
        self.assertEqual(AIXDelta.from_history([_envelope()]), [])
        self.assertEqual(AIXDelta.from_history([]), [])


if __name__ == "__main__":
    unittest.main()
