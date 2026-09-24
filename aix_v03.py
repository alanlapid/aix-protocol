"""
aix_v03.py — Reference implementation of .aix v0.3 (DRAFT).

v0.3 speaks a vocabulary that language models and tools already know:
the document is JSON-LD over schema.org, W3C OWL-Time and W3C PROV-O, and
the `gm:` namespace defines ONLY what those vocabularies lack (memory
level, permission scope, delivery receipt, sensitivity, life-stage era,
record status). Nothing about any PII transformation mechanism is part of
the format: only the `gm:piiProtected` flag (see AIX-SPEC-v0.3-draft.md §7).

Design rules (AIX-SPEC-v0.3-draft.md):
  - Tolerant of partial records: like schema.org, almost everything is
    optional. Each record needs only `@id`, `@type`, `gm:recordedAt`
    (ISO 8601 with UTC offset: when the producer learned it) and
    `prov:wasAttributedTo` (who or what produced it: `human:<id>`,
    `agent:<id>`, `process:<id>`, the same actor convention as OKF).
  - Honest time: dates keep the precision of their source (`2017`,
    `2017-03`, `2017-03-14`); a date-time MUST carry an offset.
  - Never delete: a record is superseded (`gm:status: superseded` +
    `gm:supersededBy`), not removed. schema:supersededBy only applies to
    vocabulary terms, hence the `gm:` term for records.
  - Lossless round-trip: `dump(load(doc)) == canonical(doc)`.

Pure Python standard library, no third-party dependencies (the JSON
Schema in schema/ is provided for external validators).

Usage:
    from aix_v03 import Document, Record, load, dump, validate
    doc = Document(subject="gm:subject/abc", scope="self-only")
    doc.add(Record("gm:fact/1", "gm:Fact", "2026-09-24T10:00:00+00:00", "human:alan",
                   {"gm:subject": "gm:entity/alan", "gm:predicate": "worksFor", "gm:object": "gm:entity/kiwi"}))
    data = dump(doc)
    assert dump(load(data)) == data
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

VERSION = "0.3.0-draft"
CONTEXT: list[Any] = [
    "https://schema.org/",
    {"time": "http://www.w3.org/2006/time#", "prov": "http://www.w3.org/ns/prov#",
     "gm": "https://thegeometrical.com/ns/aix#"},
]
DELIVERY_PROFILE = "aix-compact/0.3-draft"

SCOPES = re.compile(r"^(self-only|agent:[\w.-]+|team:[\w.-]+|org:[\w.-]+)$")
ACTOR = re.compile(r"^(human|agent|process):[\w.@/-]+$")
MEMORY_LEVELS = ("stm", "mtm", "ltm", "archival")
SENSITIVITIES = ("public", "personal", "sensitive")
STATUSES = ("active", "proposed", "superseded", "discarded")
# ISO 8601 with honest precision: YYYY, YYYY-MM, YYYY-MM-DD, or a date-time WITH offset.
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}(:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:\d{2})$")
DATE_KEYS = ("startDate", "endDate", "startTime", "endTime", "timestamp", "dateCreated", "datePublished")

# gm: vocabulary with its governance status (pending → stable; never deleted, only superseded).
VOCABULARY: dict[str, dict[str, str]] = {
    "gm:AixDocument": {"status": "stable", "comment": "A .aix v0.3 document."},
    "gm:Fact": {"status": "stable", "comment": "A statement subject-predicate-object with provenance and validity."},
    "gm:Era": {"status": "pending", "comment": "A life stage: ordinal reference system (professional, personal)."},
    "gm:Receipt": {"status": "pending", "comment": "What an agent was served, why, and its integrity hash."},
    "gm:recordedAt": {"status": "stable", "comment": "When the producer learned the record (transaction time)."},
    "gm:memoryLevel": {"status": "stable", "comment": "stm | mtm | ltm | archival."},
    "gm:scope": {"status": "stable", "comment": "self-only | agent:<id> | team:<id> | org:<id>."},
    "gm:sensitivity": {"status": "stable", "comment": "public | personal | sensitive (sensitive never leaves its origin)."},
    "gm:status": {"status": "stable", "comment": "active | proposed | superseded | discarded."},
    "gm:supersededBy": {"status": "stable", "comment": "Record that replaces this one (schema:supersededBy is for terms)."},
    "gm:subject": {"status": "stable", "comment": "Subject of a gm:Fact."},
    "gm:predicate": {"status": "stable", "comment": "Predicate of a gm:Fact (a schema.org property or a producer term)."},
    "gm:object": {"status": "stable", "comment": "Object of a gm:Fact (a record @id or a literal)."},
    "gm:role": {"status": "stable", "comment": "schema:Role qualifying a gm:Fact (roleName, startDate, endDate)."},
    "gm:confidence": {"status": "stable", "comment": "Producer confidence in [0, 1]."},
    "gm:subtype": {"status": "pending", "comment": "Producer subtype refining @type (e.g. a startup Project)."},
    "gm:piiProtected": {"status": "stable", "comment": "Content was transformed before leaving its origin."},
    "gm:permissions": {"status": "stable", "comment": "read / share / expiresAt / readOnly for the document."},
    "gm:integrity": {"status": "stable", "comment": "Merkle-SHA256 root over the canonical records."},
    "gm:ordinal": {"status": "pending", "comment": "Position of a gm:Era within its system."},
    "gm:system": {"status": "pending", "comment": "Reference system of a gm:Era (professional | personal)."},
    "gm:servedTo": {"status": "pending", "comment": "Agent a gm:Receipt was delivered to."},
    "gm:purpose": {"status": "pending", "comment": "Declared purpose of an access (mandatory in Nexus)."},
    "gm:facts": {"status": "pending", "comment": "Records a gm:Receipt covers."},
    "gm:PublishAction": {"status": "pending", "comment": "Subclass of schema:CreateAction: making a work public."},
}


def _terminos_gm(obj: Any) -> set[str]:
    """gm: terms used as keys or types anywhere in a record."""
    usados: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("gm:"):
                usados.add(k)
            if k == "@type":
                usados |= {t for t in ([v] if isinstance(v, str) else v) if isinstance(t, str) and t.startswith("gm:")}
            usados |= _terminos_gm(v)
    elif isinstance(obj, list):
        for v in obj:
            usados |= _terminos_gm(v)
    return usados


@dataclass
class Record:
    id: str
    type: str | list[str]
    recorded_at: str
    attributed_to: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"@id": self.id, "@type": self.type, "gm:recordedAt": self.recorded_at,
                "prov:wasAttributedTo": self.attributed_to, **self.properties}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Record:
        reservadas = ("@id", "@type", "gm:recordedAt", "prov:wasAttributedTo")
        return Record(str(data["@id"]), data["@type"], str(data["gm:recordedAt"]), str(data["prov:wasAttributedTo"]),
                      {k: v for k, v in data.items() if k not in reservadas})


@dataclass
class Document:
    subject: str
    scope: str = "self-only"
    recorded_at: str = ""
    attributed_to: str = "process:aix"
    pii_protected: bool = False
    permissions: dict[str, Any] = field(default_factory=lambda: {"read": ["self"], "share": [], "readOnly": True})
    records: list[Record] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    # Producer prefixes (e.g. {"self": "https://thegeometrical.com/ns/self#"}):
    # producer-specific keys live under their own prefix, never under gm:.
    producer_context: dict[str, str] = field(default_factory=dict)

    def add(self, record: Record) -> None:
        self.records.append(record)


def _canonico(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def merkle_root(records: list[dict[str, Any]]) -> str:
    """Merkle-SHA256 over the canonical JSON of each record (same scheme as v0.2)."""
    nivel = [hashlib.sha256(_canonico(r).encode()).hexdigest() for r in records] or [hashlib.sha256(b"").hexdigest()]
    while len(nivel) > 1:
        if len(nivel) % 2:
            nivel = nivel + [nivel[-1]]
        nivel = [hashlib.sha256((nivel[i] + nivel[i + 1]).encode()).hexdigest() for i in range(0, len(nivel), 2)]
    return nivel[0]


def dump(doc: Document, integrity: bool = False) -> dict[str, Any]:
    """Document → canonical JSON-LD dict (records sorted by @id, keys sorted
    on serialization). With integrity=True adds the Merkle root."""
    records = [r.to_dict() for r in sorted(doc.records, key=lambda r: r.id)]
    out: dict[str, Any] = {
        "@context": CONTEXT + ([doc.producer_context] if doc.producer_context else []),
        "@type": "gm:AixDocument", "schemaVersion": VERSION,
        "about": {"@id": doc.subject}, "gm:scope": doc.scope, "gm:recordedAt": doc.recorded_at,
        "prov:wasAttributedTo": doc.attributed_to, "gm:piiProtected": doc.pii_protected,
        "gm:permissions": doc.permissions, "@graph": records, **doc.extra,
    }
    if integrity:
        out["gm:integrity"] = {"algorithm": "merkle-sha256", "root": merkle_root(records)}
    return json.loads(_canonico(out))  # canonical key order


def load(data: dict[str, Any]) -> Document:
    """Canonical dict → Document. Unknown top-level keys are preserved
    (extra) so producer extensions survive a round-trip."""
    conocidas = {"@context", "@type", "schemaVersion", "about", "gm:scope", "gm:recordedAt", "prov:wasAttributedTo",
                 "gm:piiProtected", "gm:permissions", "@graph", "gm:integrity"}
    contexto = data.get("@context", [])
    producer = dict(contexto[2]) if isinstance(contexto, list) and len(contexto) > 2 else {}
    return Document(
        producer_context=producer,
        subject=str(data["about"]["@id"]), scope=str(data.get("gm:scope", "self-only")),
        recorded_at=str(data.get("gm:recordedAt", "")), attributed_to=str(data.get("prov:wasAttributedTo", "process:aix")),
        pii_protected=bool(data.get("gm:piiProtected", False)),
        permissions=dict(data.get("gm:permissions", {})),
        records=[Record.from_dict(r) for r in data.get("@graph", [])],
        extra={k: v for k, v in data.items() if k not in conocidas},
    )


def verify(data: dict[str, Any]) -> bool:
    """True if the document carries gm:integrity and its records match it."""
    integ = data.get("gm:integrity")
    return bool(integ) and merkle_root(data.get("@graph", [])) == integ.get("root")


def _fechas(obj: Any, ruta: str, errores: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in DATE_KEYS and isinstance(v, str) and not (DATE.match(v) or DATETIME.match(v)):
                errores.append(f"{ruta}.{k}: '{v}' is not ISO 8601 with honest precision (a date-time needs an offset)")
            _fechas(v, f"{ruta}.{k}", errores)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _fechas(v, f"{ruta}[{i}]", errores)


def validate(data: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(errors, warnings). Errors break the format; warnings are tolerated
    (partial records, dangling references, pending terms)."""
    errores: list[str] = []
    avisos: list[str] = []
    if data.get("@type") != "gm:AixDocument":
        errores.append("@type must be gm:AixDocument")
    if not str(data.get("schemaVersion", "")).startswith("0.3"):
        errores.append("schemaVersion must be 0.3.x")
    if not isinstance(data.get("about"), dict) or "@id" not in data["about"]:
        errores.append("about.@id (the subject) is required")
    if not SCOPES.match(str(data.get("gm:scope", ""))):
        errores.append(f"gm:scope invalid: {data.get('gm:scope')!r}")
    if not DATETIME.match(str(data.get("gm:recordedAt", ""))):
        errores.append("gm:recordedAt must be a date-time with offset")
    ids: set[str] = set()
    for i, r in enumerate(data.get("@graph", [])):
        ruta = f"@graph[{i}]"
        for clave in ("@id", "@type", "gm:recordedAt", "prov:wasAttributedTo"):
            if clave not in r:
                errores.append(f"{ruta}: missing required {clave}")
        if r.get("@id") in ids:
            errores.append(f"{ruta}: duplicate @id {r.get('@id')}")
        ids.add(str(r.get("@id")))
        if "gm:recordedAt" in r and not DATETIME.match(str(r["gm:recordedAt"])):
            errores.append(f"{ruta}: gm:recordedAt must be a date-time with offset")
        if "prov:wasAttributedTo" in r and not ACTOR.match(str(r["prov:wasAttributedTo"])):
            errores.append(f"{ruta}: prov:wasAttributedTo must be human:|agent:|process:<id>")
        for clave, valores in (("gm:memoryLevel", MEMORY_LEVELS), ("gm:sensitivity", SENSITIVITIES), ("gm:status", STATUSES)):
            if clave in r and r[clave] not in valores:
                errores.append(f"{ruta}: {clave} must be one of {valores}")
        if r.get("gm:sensitivity") == "sensitive":
            errores.append(f"{ruta}: a sensitive record never leaves its origin")
        if r.get("gm:status") == "superseded" and "gm:supersededBy" not in r:
            errores.append(f"{ruta}: superseded without gm:supersededBy")
        if "gm:confidence" in r and not (isinstance(r["gm:confidence"], (int, float)) and 0 <= r["gm:confidence"] <= 1):
            errores.append(f"{ruta}: gm:confidence must be in [0, 1]")
        for t in sorted(_terminos_gm(r) - set(VOCABULARY)):
            avisos.append(f"{ruta}: undeclared gm: term {t} (propose it as pending)")
        tipos = [r.get("@type")] if isinstance(r.get("@type"), str) else list(r.get("@type") or [])
        if "gm:Fact" in tipos and not {"gm:subject", "gm:predicate"} <= set(r):
            avisos.append(f"{ruta}: partial gm:Fact (no subject or predicate)")
        for t in sorted(_terminos_gm(r)):
            if VOCABULARY.get(t, {}).get("status") == "pending":
                avisos.append(f"{ruta}: uses pending term {t}")
        _fechas(r, ruta, errores)
    for i, r in enumerate(data.get("@graph", [])):
        for clave in ("gm:subject", "gm:object", "gm:supersededBy"):
            v = r.get(clave)
            if isinstance(v, str) and v.startswith("gm:") and v not in ids:
                avisos.append(f"@graph[{i}]: {clave} points outside the document ({v})")
    if "gm:integrity" in data and not verify(data):
        errores.append("gm:integrity does not match the records")
    return errores, avisos


def from_v02(envelope: dict[str, Any], attributed_to: str = "process:aix-v02-import") -> Document:
    """v0.2 envelope → v0.3 document: each memory becomes an
    InstantaneousEvent (schema.org, pending: source/timestamp/data)."""
    env = envelope["aix_envelope"]
    doc = Document(subject=f"gm:subject/{env['subject_id']}", recorded_at=env.get("updated_at") or env["created_at"],
                   attributed_to=attributed_to, pii_protected=bool(env.get("pii_protected")),
                   permissions={"read": env.get("permissions", {}).get("read", ["self"]),
                                "share": env.get("permissions", {}).get("share", []), "readOnly": True})
    for m in envelope.get("memories", []):
        props: dict[str, Any] = {"source": m.get("source"), "timestamp": m["timestamp"], "data": m.get("content", {})}
        nivel = {"stm": "stm", "mtm": "mtm", "ltm": "ltm", "archive": "archival", "archival": "archival"}.get(m.get("tier", ""))
        if nivel:
            props["gm:memoryLevel"] = nivel
        if m.get("pii_protected"):
            props["gm:piiProtected"] = True
        doc.add(Record(f"gm:episode/{m['id']}", "InstantaneousEvent", m["timestamp"], attributed_to,
                       {k: v for k, v in props.items() if v is not None}))
    return doc
