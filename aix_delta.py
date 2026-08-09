"""
aix_delta.py — semantic diff between two .aix envelopes.

Not a text diff. A diff of EPISODIC IDENTITY: which memories were added
or removed, which roles/entities appeared or disappeared, and how the
identity snapshot's aggregate signals (verification, graph density)
moved between two points in time.

Pure Python standard library, depends only on aix_parser.py from this
repository.

Usage:
    from aix_parser import AIXEnvelope
    from aix_delta import AIXDelta

    delta = AIXDelta(envelope_a, envelope_b)
    changes = delta.compute()
    print(changes["summary"])

    # Reconstruct what envelope_b looked like, starting from envelope_a:
    reconstructed = delta.apply(envelope_a)
"""

from __future__ import annotations

from typing import Any

from aix_parser import AIXEnvelope, AIXMemory


class AIXDelta:
    """Computes and applies the semantic diff between 'envelope_a' (older)
    and 'envelope_b' (newer). Nothing is mutated on either envelope --
    compute() and apply() both read, never write, envelope_a/envelope_b."""

    def __init__(self, envelope_a: AIXEnvelope, envelope_b: AIXEnvelope):
        self.envelope_a = envelope_a
        self.envelope_b = envelope_b

    @staticmethod
    def _ids(envelope: AIXEnvelope) -> set[str]:
        return {m.id for m in envelope.memories}

    @staticmethod
    def _roles(envelope: AIXEnvelope) -> set[str]:
        return {
            r.get("role")
            for r in envelope.identity.get("active_roles", [])
            if r.get("role")
        }

    @staticmethod
    def _entities(envelope: AIXEnvelope) -> set[str]:
        """Union of content.entities across every memory -- 'which
        entities does this identity touch', not per-memory detail."""
        entidades: set[str] = set()
        for memoria in envelope.memories:
            entidades.update(memoria.content.get("entities", []))
        return entidades

    def _ids_added(self) -> set[str]:
        return self._ids(self.envelope_b) - self._ids(self.envelope_a)

    def _ids_removed(self) -> set[str]:
        return self._ids(self.envelope_a) - self._ids(self.envelope_b)

    def compute(self) -> dict[str, Any]:
        """Returns the diff dict described in the module docstring.
        Read-only: does not mutate envelope_a/envelope_b."""
        roles_a, roles_b = self._roles(self.envelope_a), self._roles(self.envelope_b)
        entities_a, entities_b = self._entities(self.envelope_a), self._entities(self.envelope_b)

        densidad_a = self.envelope_a.identity.get("graph_stats", {}).get("graph_density", 0.0)
        densidad_b = self.envelope_b.identity.get("graph_stats", {}).get("graph_density", 0.0)

        resultado: dict[str, Any] = {
            "memories_added": sorted(self._ids_added()),
            "memories_removed": sorted(self._ids_removed()),
            "roles_changed": {
                "added": sorted(roles_b - roles_a),
                "removed": sorted(roles_a - roles_b),
            },
            "entities_changed": {
                "added": sorted(entities_b - entities_a),
                "removed": sorted(entities_a - entities_b),
            },
            "verification_delta": round(
                self.envelope_b.to_dict()["aix_identity"]["verification_mean"]
                - self.envelope_a.to_dict()["aix_identity"]["verification_mean"],
                4,
            ),
            "graph_density_delta": round(densidad_b - densidad_a, 4),
        }
        resultado["summary"] = self._build_summary(resultado)
        return resultado

    @staticmethod
    def _build_summary(d: dict[str, Any]) -> str:
        """Short, human-readable one-liner built from an already-computed
        diff dict (same shape compute() returns)."""
        partes: list[str] = []

        if d["memories_added"]:
            partes.append(f"+{len(d['memories_added'])} memories")
        if d["memories_removed"]:
            partes.append(f"-{len(d['memories_removed'])} memories")
        if d["roles_changed"]["added"]:
            partes.append("roles +" + ", +".join(d["roles_changed"]["added"]))
        if d["roles_changed"]["removed"]:
            partes.append("roles -" + ", -".join(d["roles_changed"]["removed"]))
        if d["entities_changed"]["added"]:
            partes.append(f"+{len(d['entities_changed']['added'])} entities")
        if d["entities_changed"]["removed"]:
            partes.append(f"-{len(d['entities_changed']['removed'])} entities")
        if d["verification_delta"]:
            partes.append(f"verification {d['verification_delta']:+.4f}")
        if d["graph_density_delta"]:
            partes.append(f"density {d['graph_density_delta']:+.4f}")

        return ", ".join(partes) if partes else "no changes"

    def apply(self, base: AIXEnvelope) -> AIXEnvelope:
        """Applies this delta to 'base', returning a NEW AIXEnvelope --
        'base' and envelope_a/envelope_b are never mutated.

        Assumes 'base' is memory-compatible with envelope_a (typically
        IS envelope_a, or a copy of it) -- same assumption any patch/diff
        tool makes about applying a diff to the base it was computed
        against. Memories are deep-copied (via to_dict()/from_dict()),
        never shared by reference, so mutating the result never affects
        'base' or envelope_b.
        """
        ids_quitar = self._ids_removed()
        ids_agregar = self._ids_added()
        nuevas_por_id = {m.id: m for m in self.envelope_b.memories if m.id in ids_agregar}

        resultado = AIXEnvelope(
            subject_id=base.subject_id,
            device_id=base.device_id,
            session_id=base.session_id,
            substrate_version=base.substrate_version,
        )

        for memoria in base.memories:
            if memoria.id not in ids_quitar:
                resultado.add_memory(AIXMemory.from_dict(memoria.to_dict()))

        for id_nueva in sorted(ids_agregar):
            resultado.add_memory(AIXMemory.from_dict(nuevas_por_id[id_nueva].to_dict()))

        resultado.set_identity(
            roles=list(self.envelope_b.identity.get("active_roles", [])),
            goals=list(self.envelope_b.identity.get("goals", [])),
            intentions=list(self.envelope_b.identity.get("intentions", [])),
            graph_stats=dict(self.envelope_b.identity.get("graph_stats", {})),
        )
        resultado.set_permissions(
            read=list(base.permissions.get("read", [])),
            write=list(base.permissions.get("write", [])),
            share=list(base.permissions.get("share", [])),
        )
        return resultado

    @classmethod
    def from_history(cls, envelopes: list[AIXEnvelope]) -> list["AIXDelta"]:
        """Consecutive-pair deltas over N envelopes (oldest to newest) --
        N-1 deltas, delta[i] = diff(envelopes[i], envelopes[i+1]). Empty
        list if fewer than 2 envelopes (nothing to diff)."""
        if len(envelopes) < 2:
            return []
        return [cls(envelopes[i], envelopes[i + 1]) for i in range(len(envelopes) - 1)]


if __name__ == "__main__":
    env_a = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
    env_a.add_memory(AIXMemory(source="apple_notes", role="researcher", content={"text": "Reading about deltas."}))
    env_a.set_identity(
        roles=[{"role": "researcher", "frequency": 1, "last_seen": ""}],
        goals=[],
        intentions=[],
        graph_stats={"entities": 1, "semantic_relations": 0, "causal_edges": 0, "graph_density": 0.0, "life_events": 0},
    )

    env_b = AIXEnvelope(subject_id="s1", device_id="d1", session_id="sess1")
    env_b.add_memory(AIXMemory(source="apple_notes", role="creator", content={"text": "Shipped aix_delta.py.", "entities": ["aix_delta"]}))
    env_b.set_identity(
        roles=[{"role": "creator", "frequency": 1, "last_seen": ""}],
        goals=[],
        intentions=[],
        graph_stats={"entities": 2, "semantic_relations": 1, "causal_edges": 0, "graph_density": 0.5, "life_events": 0},
    )

    delta = AIXDelta(env_a, env_b)
    changes = delta.compute()
    print("--- compute() ---")
    for clave, valor in changes.items():
        print(f"{clave}: {valor}")

    reconstruido = delta.apply(env_a)
    print("\n--- apply() ---")
    print(f"memory_count after apply: {len(reconstruido.memories)}")
    print(f"roles after apply: {[r['role'] for r in reconstruido.identity['active_roles']]}")
