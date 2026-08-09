# .aix — Agent-Native Episodic Memory Format

## Specification v0.2 — August 2026

**Status:** Draft | **Maintainer:** Geometrical

`v0.1` files remain fully valid under `v0.2` — every field added in this
revision (`token_budget`, `signature`, `federate`, `doc_type`) is
optional, per the MINOR-version rule in Section 6. `examples/minimal.aix`,
`full.aix`, and `pii_protected.aix` are still literally tagged
`aix_version: "0.1"` and still pass `validate()` unchanged, as a live
demonstration of that guarantee — only `examples/soma_contract.aix` uses
the new v0.2 fields.

---

### 1. Overview

**The problem:** AI agents accumulate rich episodic context — events,
decisions, roles, intentions — but that context is trapped in vendor
silos. There is no standard format for transporting, storing, and
sharing episodic memory between agents, devices, and sessions.

**The solution:** `.aix` is a portable envelope for episodic memory with:

- Spatiotemporal provenance (when and where something happened)
- A 9-dimension identity model
- Granular permission control (`PRIVATE`/`SHARED`/`PUBLIC`)
- Native support for PII transformation before transmission
- Semantic versioning of the episodic substrate

---

### 2. Design Principles

1. **Agent-native**: an M2M format, not compressed human text.
2. **Local-first**: works without cloud, without an external API.
3. **Privacy-preserving**: PII transformation before transmission.
4. **Portable**: iOS, Android, macOS, Linux, wearables.
5. **Versioned**: backward compatibility guaranteed.

---

### 3. File Format

#### 3.1 Extension and MIME Type

- Extension: `.aix`
- MIME type: `application/x-aix-memory`
- Encoding: UTF-8 JSON (compressible with gzip)

#### 3.2 Top-Level Structure

```json
{
  "aix_envelope": { },
  "aix_identity": { },
  "memories": [ ],
  "aix_trace": { }
}
```

| Field | Type | Description |
|---|---|---|
| `aix_envelope` | object | File metadata: version, identity, permissions, checksum. |
| `aix_identity` | object | 9-DIM identity snapshot at export time. |
| `memories` | array | Array of Memory Records (Section 3.4). |
| `aix_trace` | object | Spatiotemporal provenance of the file itself. |

#### 3.3 `aix_envelope` (required)

```json
{
  "aix_version": "0.1",
  "created_at": "ISO8601",
  "updated_at": "ISO8601",
  "subject_id": "string (opaque, no PII)",
  "device_id": "string (opaque, no PII)",
  "session_id": "string",
  "memory_count": 0,
  "checksum": "sha256 of the memories array",
  "permissions": {
    "read": ["self"],
    "write": ["self"],
    "share": []
  },
  "pii_protected": false,
  "substrate_version": "string (e.g. 1.0)",
  "token_budget": {
    "max_tokens": 0,
    "used_tokens": 0,
    "compression": "none|gzip|lz4"
  },
  "signature": {
    "algorithm": "merkle-sha256",
    "root": "string (hex)",
    "signed_at": "ISO8601"
  },
  "federate": { }
}
```

`permissions` values:

- `"self"` — only the origin `subject_id`.
- `"soma:{org_id}"` — a specific organization, via Nexus.
- `"public"` — anyone (non-PII metadata only).

`token_budget`, `signature`, and `federate` are **optional** (new in
v0.2) — an envelope without them is still fully valid v0.1-shaped data;
these fields exist for consumers that need context planning, tamper
detection, or cross-perimeter sharing respectively:

| Field | Description |
|---|---|
| `token_budget` | Estimated token cost of the envelope, so a receiving agent can plan context usage before loading it. See Section 3.6 (Token Reduction). |
| `signature` | Merkle-SHA256 integrity proof over `memories[]` — absent means the envelope carries no tamper-evidence. See Section 11.3 (Integrity). |
| `federate` | Granular, Nexus-governed permissions by perimeter/role/field — a superset of `permissions` for cross-perimeter sharing. Absent means `permissions` alone governs access (`PRIVATE` by default). See Section 3.5 and Section 11 (Nexus Protocol). |

#### 3.4 Memory Record (each item in `memories[]`)

```json
{
  "id": "uuid4",
  "timestamp": "ISO8601",
  "source": "string (apple_notes|keyboard|safari|...)",
  "role": "string (inferred principal role)",
  "doc_type": "note|email|message|document|audio|photo|action|web",
  "tier": "stm|mtm|ltm|archival",
  "epic_score": 0.0,
  "verification_score": 0.0,
  "pii_protected": false,
  "content": {
    "text": "string",
    "entities": ["string"],
    "decisions": ["string"],
    "intentions": ["string"],
    "emotions": ["string"],
    "patterns": ["string"],
    "porques": ["string"]
  },
  "embeddings": {
    "model": "string (e.g. nomic-embed-text)",
    "vector": null
  },
  "trace": {
    "latitude": null,
    "longitude": null,
    "location_name": null,
    "local_time": "ISO8601",
    "timezone": "string",
    "device_type": "mobile|laptop|desktop|wearable|unknown"
  }
}
```

> **Note:** `embeddings.vector` may be omitted for privacy. The field
> exists for implementations that choose to include it. `doc_type` is
> **optional** (new in v0.2) — content-type categorization. `source`
> alone (which app/pipeline produced the memory) doesn't distinguish
> document kind; `doc_type` does. Most relevant for Soma enterprise
> ingestion, where a single organization ingests contracts, emails, and
> meeting notes side by side — see `SOMA-USAGE.md`.

#### 3.5 `federate` (Nexus Permissions — optional)

The `federate` field (inside `aix_envelope`) implements **Nexus v0.1** —
the permission and federation protocol of the AIX Protocol stack. Full
protocol description in Section 11; this subsection covers the schema.

```json
{
  "federate": {
    "soma:{org_id}": {
      "roles": ["string"],
      "fields": ["string"],
      "expires_at": "ISO8601 | null",
      "read_only": true
    },
    "self:{device_id}": {
      "roles": ["*"],
      "fields": ["*"],
      "expires_at": null,
      "read_only": false
    }
  }
}
```

- **When `federate` is absent**: `PRIVATE` permissions apply (Section 4
  default) — only `permissions.read`/`write`/`share` govern access.
- **When `federate` is present**: Nexus governs access for the
  perimeters listed as keys. Each entry scopes access by `roles` (which
  roles of the receiving perimeter qualify), `fields` (which
  `content.*` fields are visible — anything not listed, including
  `text`, stays invisible), `expires_at` (or `null` for no expiry), and
  `read_only`.

Nexus Protocol in full — perimeters, integrity, what v0.1 does *not* yet
define — is documented in Section 11 of this spec. It will move to its
own `NEXUS-SPEC.md` (and eventually its own repository) once it outgrows
being a subsection here.

#### 3.6 Token Reduction

`.aix` reduces context token consumption when transporting memory in
M2M format instead of compressed human text.

Benchmarks from the reference implementation (Self v1.1):

- **Typical reduction**: 35–78% vs. equivalent plain text.
- **Mechanism**: Knowledge Compiler (LSH deduplication + JSON
  distillation) runs before packaging into `.aix`.
- The `token_budget` field on the envelope (Section 3.3) lets receiving
  agents plan context usage without parsing `memories[]` first.

These numbers describe Geometrical's reference implementation, not a
requirement of the format — `token_budget` is a plain estimate the
exporter fills in; the spec does not mandate how it's computed.

#### 3.7 `aix_identity` (9-DIM snapshot)

```json
{
  "active_roles": [
    { "role": "string", "frequency": 0, "last_seen": "ISO8601" }
  ],
  "goals": [
    { "goal": "string", "domain": "string", "confidence": 0.0 }
  ],
  "intentions": [
    { "intention": "string", "horizon": "string", "confidence": 0.0 }
  ],
  "graph_stats": {
    "entities": 0,
    "semantic_relations": 0,
    "causal_edges": 0,
    "graph_density": 0.0,
    "life_events": 0
  },
  "verification_mean": 0.0,
  "last_consolidated": "ISO8601"
}
```

#### 3.8 `aix_trace` (provenance of the file)

```json
{
  "origin_device": "string",
  "origin_platform": "macos|ios|android|linux|windows",
  "export_timestamp": "ISO8601",
  "exporter": "string (e.g. self-v1.1)",
  "integrity_hash": "sha256 of the full envelope"
}
```

---

### 4. Permissions Model

`.aix` uses a declarative permissions model in the envelope:

**`PRIVATE` (default)**
Only the origin device and `subject_id` can read. Never leaves the local
perimeter without transformation.

**`SHARED_SELF`**
Devices belonging to the same user can synchronize. Requires
authentication via recovery phrase or device trust. Implemented by the
Nexus protocol.

**`SHARED_SOMA`**
An organization can read identity dimensions relevant to its role
policy. The `subject_id` remains opaque to the organization. Implemented
by the Nexus protocol.

**`PUBLIC`**
Only non-PII metadata from `aix_envelope`. Never the contents of
`memories[]`.

---

### 5. Privacy Layer

`.aix` supports PII transformation before transmission. When
`pii_protected: true`, PII entities in the content have been replaced
with synthetic tokens before the file was written or transmitted.

The specific transformation mechanism is **implementation-defined**. The
format only requires:

1. `pii_protected: true` in the envelope and in each memory.
2. That the receiver knows the content has been transformed.
3. That restoration happens locally, with the subject's own key.

Geometrical's reference implementation uses a mechanism under
**Patent Application P202631047 (OEPM, filed July 19, 2026)**. Other
implementations may use their own mechanism compatible with this
contract — the format does not mandate a specific transformation
algorithm, only the presence of the flag and the restoration guarantee
above.

---

### 6. Versioning

`aix_version` in the envelope follows semantic versioning:

- **MAJOR** — incompatible schema changes.
- **MINOR** — new optional fields.
- **PATCH** — spec corrections without schema changes.

`substrate_version` is independent — it versions the subject's episodic
substrate, not the file format.

**Backward compatibility:** a v0.2 parser must be able to read v0.1
files.

---

### 7. Comparison with Related Formats

| Format | Purpose | Identity Graph | Local-first | PII Layer | Federation | Token Reduction |
|---|---|---|---|---|---|---|
| **.aix** (this) | Episodic identity | ✅ 9-DIM | ✅ | ✅ patent | ✅ Nexus | ✅ 35–78% |
| PAM (MS, 2605.11032) | Memory transfer | ✗ | ✗ | ✗ | ✗ | ✗ |
| MemGPT context | Session context | ✗ | ✗ | ✗ | ✗ | ✗ |
| JSON-LD | Linked data | ✗ | ✓ | ✗ | ✗ | ✗ |

Same table (minus the `Purpose` column) lives in `README.md`, kept in
sync with this one.

---

### 8. Reference Implementation

See [`aix_parser.py`](aix_parser.py) in this repository.

- **Implemented by:** Self v1.1 (Geometrical)
- **Website:** [geometrical.ai](https://geometrical.ai)

---

### 9. Examples

See the [`examples/`](examples/) directory:

- [`minimal.aix`](examples/minimal.aix) — valid minimal file.
- [`full.aix`](examples/full.aix) — complete example with all dimensions.
- [`pii_protected.aix`](examples/pii_protected.aix) — example with PII
  transformation.
- [`soma_contract.aix`](examples/soma_contract.aix) — enterprise example
  (v0.2) with `doc_type`, `token_budget`, `signature`, and `federate`
  (Nexus). See `SOMA-USAGE.md`.

---

### 10. Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

Geometrical maintains the spec through v0.x. Governance will open to the
community at v1.0.

---

### 11. Nexus Protocol v0.1

Nexus is the permission and federation layer of the AIX Protocol stack.
It governs what memory dimensions are shared between which perimeters,
and under what conditions.

#### 11.1 Perimeters

A **perimeter** is an identity boundary within which `.aix` memory flows
freely. Between perimeters, Nexus governs what crosses.

Four perimeter types:

- `self:{subject_id}` — the individual (Self substrate).
- `soma:{org_id}` — an organization (Soma substrate).
- `axis:{agent_id}` — an autonomous agent (Axis substrate).
- `public` — no perimeter (only non-PII metadata).

#### 11.2 Federation Rules

The `federate` field in the `aix_envelope` (Section 3.5) declares Nexus
permissions at export time:

```json
{
  "federate": {
    "soma:bank_001": {
      "roles": ["employee", "advisor"],
      "fields": ["decisions", "skills"],
      "expires_at": "2026-12-31T00:00:00Z",
      "read_only": true
    }
  }
}
```

This declares: the organization `soma:bank_001` may read the
`decisions` and `skills` fields of memories where the subject's role
matches `employee` or `advisor`, until 2026-12-31, read-only.

Fields not listed in `fields[]` are invisible to the receiving
perimeter — including `text` if not listed.

#### 11.3 Integrity

`.aix` envelopes include a Merkle signature over `memories[]`:

```json
{
  "signature": {
    "algorithm": "merkle-sha256",
    "root": "hex string",
    "signed_at": "ISO8601"
  }
}
```

Any modification to any memory record changes the Merkle root, making
tampering detectable.

#### 11.4 What Nexus Does NOT Define (yet)

Nexus v0.1 defines the permission schema only. The following are
planned for Nexus v0.2:

- Transport protocol (how `.aix` envelopes move between perimeters over
  the network).
- Key exchange and authentication between perimeters.
- Revocation of `federate` permissions.
- Audit log format for cross-perimeter access.

These will be documented in `NEXUS-SPEC.md` when Nexus gets its own
repository.
