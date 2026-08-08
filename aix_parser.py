"""
aix_parser.py — Reference implementation of the .aix format (spec v0.1).

Pure Python standard library, no third-party dependencies. See
AIX-SPEC.md in this repository for the full format specification.

This module implements the STRUCTURE of the format only: envelope,
identity snapshot, memory records, and the PII-transformation contract
(the `pii_protected` flag). It does NOT implement any specific PII
transformation mechanism — per AIX-SPEC.md Section 5, that mechanism is
implementation-defined. Geometrical's own implementation (used by Self)
is covered by Patent Application P202631047 and lives outside this
open-source reference parser.

Usage:
    from aix_parser import AIXEnvelope, AIXMemory

    env = AIXEnvelope(subject_id="u1", device_id="d1", session_id="s1")
    env.add_memory(AIXMemory(source="apple_notes", role="founder",
                              content={"text": "Shipped v0.1 of the spec."}))
    env.to_file("memory.aix")
    env2 = AIXEnvelope.from_file("memory.aix")
"""

from __future__ import annotations

import hashlib
import json
import platform
import uuid
from datetime import datetime, timezone
from typing import Any

AIX_VERSION = "0.1"

ALLOWED_TIERS = ("stm", "mtm", "ltm", "archival")
ALLOWED_DEVICE_TYPES = ("mobile", "laptop", "desktop", "wearable", "unknown")
CONTENT_FIELDS = (
    "text",
    "entities",
    "decisions",
    "intentions",
    "emotions",
    "patterns",
    "porques",
)

_PLATFORM_MAP = {
    "darwin": "macos",
    "linux": "linux",
    "windows": "windows",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_time_and_offset() -> tuple[str, str]:
    """Local wall-clock time (ISO8601, with UTC offset) and the offset
    alone (e.g. "+02:00") as a separate string -- aix_trace keeps them as
    two fields (local_time / timezone) rather than relying on the caller
    to parse one out of the other."""
    ahora = datetime.now().astimezone()
    return ahora.isoformat(), ahora.strftime("%z")[:3] + ":" + ahora.strftime("%z")[3:]


def _sha256_of(obj: Any) -> str:
    """Deterministic sha256 of any JSON-serializable object (sort_keys=True
    so the same logical content always hashes the same, regardless of
    dict insertion order)."""
    serializado = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


class AIXMemory:
    """A single Memory Record (AIX-SPEC.md Section 3.4)."""

    def __init__(self, source: str, role: str, content: dict[str, Any]):
        self.id = str(uuid.uuid4())
        self.timestamp = _now_iso()
        self.source = source
        self.role = role
        self.content = self._normalize_content(content)
        self.tier = "stm"
        self.epic_score: float | None = None
        self.verification_score: float | None = None
        self.pii_protected = False
        self.embeddings: dict[str, Any] = {"model": None, "vector": None}

        local_time, tz_offset = _local_time_and_offset()
        self.trace: dict[str, Any] = {
            "latitude": None,
            "longitude": None,
            "location_name": None,
            "local_time": local_time,
            "timezone": tz_offset,
            "device_type": "unknown",
        }

    @staticmethod
    def _normalize_content(content: dict[str, Any]) -> dict[str, Any]:
        """Fills in the 6 optional content fields with [] and 'text' with
        "" when the caller only supplied a subset -- to_dict() always
        emits the full 7-field shape from AIX-SPEC.md Section 3.4."""
        normalizado: dict[str, Any] = {"text": content.get("text", "")}
        for campo in CONTENT_FIELDS[1:]:
            normalizado[campo] = list(content.get(campo, []))
        return normalizado

    def set_trace(
        self,
        lat: float | None,
        lon: float | None,
        location_name: str | None,
        device_type: str,
    ) -> None:
        if device_type not in ALLOWED_DEVICE_TYPES:
            raise ValueError(
                f"device_type debe ser uno de {ALLOWED_DEVICE_TYPES}, recibido: {device_type!r}"
            )
        local_time, tz_offset = _local_time_and_offset()
        self.trace.update(
            {
                "latitude": lat,
                "longitude": lon,
                "location_name": location_name,
                "local_time": local_time,
                "timezone": tz_offset,
                "device_type": device_type,
            }
        )

    def set_scores(self, epic_score: float, verification_score: float) -> None:
        self.epic_score = epic_score
        self.verification_score = verification_score

    def set_tier(self, tier: str) -> None:
        if tier not in ALLOWED_TIERS:
            raise ValueError(f"tier debe ser uno de {ALLOWED_TIERS}, recibido: {tier!r}")
        self.tier = tier

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source,
            "role": self.role,
            "tier": self.tier,
            "epic_score": self.epic_score,
            "verification_score": self.verification_score,
            "pii_protected": self.pii_protected,
            "content": dict(self.content),
            "embeddings": dict(self.embeddings),
            "trace": dict(self.trace),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AIXMemory":
        """Reconstructs an AIXMemory with EXACTLY the fields in 'd' (id,
        timestamp, etc. included) -- bypasses __init__'s auto-generation
        of id/timestamp/trace so round-tripping a loaded file doesn't
        silently mutate it."""
        memoria = cls.__new__(cls)
        memoria.id = d["id"]
        memoria.timestamp = d["timestamp"]
        memoria.source = d["source"]
        memoria.role = d["role"]
        memoria.tier = d.get("tier", "stm")
        memoria.epic_score = d.get("epic_score")
        memoria.verification_score = d.get("verification_score")
        memoria.pii_protected = d.get("pii_protected", False)
        memoria.content = cls._normalize_content(d.get("content", {}))
        memoria.embeddings = dict(d.get("embeddings") or {"model": None, "vector": None})
        memoria.trace = dict(
            d.get("trace")
            or {
                "latitude": None,
                "longitude": None,
                "location_name": None,
                "local_time": None,
                "timezone": None,
                "device_type": "unknown",
            }
        )
        return memoria


class AIXEnvelope:
    """A full .aix file: envelope + identity snapshot + memories + trace
    (AIX-SPEC.md Section 3.2)."""

    def __init__(
        self,
        subject_id: str,
        device_id: str,
        session_id: str,
        substrate_version: str = "1.0",
    ):
        self.subject_id = subject_id
        self.device_id = device_id
        self.session_id = session_id
        self.substrate_version = substrate_version

        self.created_at = _now_iso()
        self.updated_at = self.created_at

        self.memories: list[AIXMemory] = []
        self.permissions: dict[str, list[str]] = {"read": ["self"], "write": ["self"], "share": []}
        self.identity: dict[str, Any] = self._empty_identity()

        # None = "compute fresh at to_dict() time" (el estado normal de un
        # envelope armado en memoria). from_dict()/from_json() los pisan
        # con el valor EXACTO leído del archivo, para que validate() pueda
        # detectar un checksum manipulado en vez de que to_dict() lo
        # "arregle" solo -- ver compute_checksum()/_generate_trace().
        self._loaded_checksum: str | None = None
        self._loaded_trace: dict[str, Any] | None = None

    @staticmethod
    def _empty_identity() -> dict[str, Any]:
        return {
            "active_roles": [],
            "goals": [],
            "intentions": [],
            "graph_stats": {
                "entities": 0,
                "semantic_relations": 0,
                "causal_edges": 0,
                "graph_density": 0.0,
                "life_events": 0,
            },
            "verification_mean": 0.0,
            "last_consolidated": None,
        }

    def add_memory(self, memory: AIXMemory) -> None:
        self.memories.append(memory)
        self.updated_at = _now_iso()
        # Un envelope cargado desde archivo que se muta deja de tener un
        # checksum/trace "congelados" válidos para esos datos -- vuelve a
        # modo "compute fresh", igual que uno armado en memoria desde cero.
        self._loaded_checksum = None
        self._loaded_trace = None

    def set_identity(
        self,
        roles: list[dict[str, Any]],
        goals: list[dict[str, Any]],
        intentions: list[dict[str, Any]],
        graph_stats: dict[str, Any],
    ) -> None:
        self.identity = {
            "active_roles": roles,
            "goals": goals,
            "intentions": intentions,
            "graph_stats": graph_stats,
            # verification_mean se recalcula en to_dict() sobre las
            # memorias vigentes -- ver _verification_mean(). Acá solo se
            # deja el placeholder; last_consolidated sí es "ahora" porque
            # representa el momento de ESTA llamada, no un agregado.
            "verification_mean": 0.0,
            "last_consolidated": _now_iso(),
        }
        self.updated_at = _now_iso()

    def set_permissions(self, read: list[str], write: list[str], share: list[str]) -> None:
        self.permissions = {"read": list(read), "write": list(write), "share": list(share)}
        self.updated_at = _now_iso()

    def compute_checksum(self) -> str:
        """sha256 del array 'memories' TAL COMO ESTÁ AHORA -- siempre en
        vivo, nunca cachea. validate() la usa para detectar si el checksum
        declarado en un archivo cargado no coincide con su propio
        contenido."""
        return _sha256_of([m.to_dict() for m in self.memories])

    def _verification_mean(self) -> float:
        scores = [m.verification_score for m in self.memories if m.verification_score is not None]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _generate_trace(self) -> dict[str, Any]:
        plataforma = _PLATFORM_MAP.get(platform.system().lower(), "linux")
        integridad = _sha256_of(
            {
                "subject_id": self.subject_id,
                "device_id": self.device_id,
                "memories": [m.to_dict() for m in self.memories],
                "identity": self.identity,
            }
        )
        return {
            "origin_device": self.device_id,
            "origin_platform": plataforma,
            "export_timestamp": _now_iso(),
            "exporter": f"aix_parser.py-v{AIX_VERSION}",
            "integrity_hash": integridad,
        }

    def to_dict(self) -> dict[str, Any]:
        identidad = dict(self.identity)
        identidad["verification_mean"] = self._verification_mean()

        checksum = self._loaded_checksum if self._loaded_checksum is not None else self.compute_checksum()

        # A diferencia del checksum (función pura de self.memories, siempre
        # da el mismo resultado sin mutación de por medio), _generate_trace()
        # incluye un timestamp -- sin cachear, dos llamadas a to_dict()
        # seguidas sin mutar el envelope devolverían dicts distintos, lo que
        # rompe cualquier comparación de igualdad (to_json() dos veces,
        # tests, etc.). Se genera una sola vez y se cachea hasta la próxima
        # mutación (add_memory()/set_identity()/set_permissions() resetean
        # _loaded_trace a None), igual que ya hacía para un trace cargado
        # desde archivo.
        if self._loaded_trace is None:
            self._loaded_trace = self._generate_trace()
        trace = self._loaded_trace

        return {
            "aix_envelope": {
                "aix_version": AIX_VERSION,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "subject_id": self.subject_id,
                "device_id": self.device_id,
                "session_id": self.session_id,
                "memory_count": len(self.memories),
                "checksum": checksum,
                "permissions": dict(self.permissions),
                "pii_protected": any(m.pii_protected for m in self.memories),
                "substrate_version": self.substrate_version,
            },
            "aix_identity": identidad,
            "memories": [m.to_dict() for m in self.memories],
            "aix_trace": trace,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AIXEnvelope":
        envelope_data = d.get("aix_envelope", {})

        env = cls.__new__(cls)
        env.subject_id = envelope_data.get("subject_id", "")
        env.device_id = envelope_data.get("device_id", "")
        env.session_id = envelope_data.get("session_id", "")
        env.substrate_version = envelope_data.get("substrate_version", "1.0")
        env.created_at = envelope_data.get("created_at", _now_iso())
        env.updated_at = envelope_data.get("updated_at", env.created_at)
        env.permissions = dict(
            envelope_data.get("permissions") or {"read": ["self"], "write": ["self"], "share": []}
        )
        env.identity = dict(d.get("aix_identity") or cls._empty_identity())
        env.memories = [AIXMemory.from_dict(m) for m in d.get("memories", [])]

        # Congela lo que YA estaba en el archivo -- ver comentario en
        # __init__ sobre por qué to_dict() no debe "corregir" esto solo.
        env._loaded_checksum = envelope_data.get("checksum")
        env._loaded_trace = d.get("aix_trace")

        return env

    @classmethod
    def from_json(cls, json_str: str) -> "AIXEnvelope":
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_file(cls, path: str) -> "AIXEnvelope":
        with open(path, encoding="utf-8") as f:
            return cls.from_json(f.read())

    def validate(self) -> tuple[bool, list[str]]:
        """Structural validation against AIX-SPEC.md. Returns
        (is_valid, list_of_errors) -- an empty error list means valid."""
        errores: list[str] = []
        datos = self.to_dict()
        envelope = datos["aix_envelope"]

        version = envelope.get("aix_version", "")
        partes = version.split(".")
        if not (2 <= len(partes) <= 3 and all(p.isdigit() for p in partes)):
            errores.append(f"aix_version inválido o ausente (semver esperado, ej. '0.1'): {version!r}")

        if not envelope.get("subject_id"):
            errores.append("subject_id vacío o ausente.")
        if not envelope.get("device_id"):
            errores.append("device_id vacío o ausente.")

        if not isinstance(self.memories, list):
            errores.append("memories no es una lista.")

        checksum_declarado = envelope.get("checksum")
        checksum_real = self.compute_checksum()
        if checksum_declarado != checksum_real:
            errores.append(
                f"checksum no coincide: declarado {checksum_declarado!r}, "
                f"calculado {checksum_real!r} -- el archivo pudo haber sido "
                "modificado sin recalcular el checksum."
            )

        for i, memoria in enumerate(self.memories):
            if not getattr(memoria, "source", None):
                errores.append(f"memories[{i}]: 'source' vacío o ausente.")
            if not getattr(memoria, "role", None):
                errores.append(f"memories[{i}]: 'role' vacío o ausente.")
            if not memoria.content.get("text"):
                errores.append(f"memories[{i}]: 'content.text' vacío o ausente.")

        return (len(errores) == 0, errores)


if __name__ == "__main__":
    print(f"aix_parser.py — reference implementation, spec v{AIX_VERSION}\n")

    env = AIXEnvelope(subject_id="demo_subject_hash", device_id="demo_device_hash", session_id="demo_session_001")

    mem1 = AIXMemory(
        source="apple_notes",
        role="founder",
        content={
            "text": "Decided to close pre-seed before Q4.",
            "decisions": ["close pre-seed before Q4"],
            "entities": ["Geometrical", "pre-seed"],
        },
    )
    mem1.set_tier("mtm")
    mem1.set_scores(epic_score=0.82, verification_score=0.91)
    mem1.set_trace(lat=41.3874, lon=2.1686, location_name="Barcelona, Spain", device_type="laptop")
    env.add_memory(mem1)

    env.set_identity(
        roles=[{"role": "founder", "frequency": 12, "last_seen": _now_iso()}],
        goals=[{"goal": "Close pre-seed round", "domain": "financial", "confidence": 0.8}],
        intentions=[{"intention": "Ship .aix spec v0.1", "horizon": "week", "confidence": 0.95}],
        graph_stats={
            "entities": 276,
            "semantic_relations": 1612,
            "causal_edges": 1213,
            "graph_density": 5.84,
            "life_events": 8,
        },
    )

    print("--- to_json() ---")
    print(env.to_json())

    is_valid, errors = env.validate()
    print(f"\n--- validate() ---\nvalid: {is_valid}, errors: {errors}")

    print("\n--- round-trip via to_file()/from_file() ---")
    env.to_file("/tmp/aix_parser_demo.aix")
    env2 = AIXEnvelope.from_file("/tmp/aix_parser_demo.aix")
    is_valid2, errors2 = env2.validate()
    print(f"reloaded envelope valid: {is_valid2}, errors: {errors2}")
    print(f"memory_count preserved: {len(env2.memories)}")
