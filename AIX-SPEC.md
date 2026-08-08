# .aix — Agent-Native Episodic Memory Format

## Specification v0.1 — August 2026

**Status:** Draft | **Maintainer:** Geometrical

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
  "substrate_version": "string (e.g. 1.0)"
}
```

`permissions` values:

- `"self"` — only the origin `subject_id`.
- `"soma:{org_id}"` — a specific organization, via Nexus.
- `"public"` — anyone (non-PII metadata only).

#### 3.4 Memory Record (each item in `memories[]`)

```json
{
  "id": "uuid4",
  "timestamp": "ISO8601",
  "source": "string (apple_notes|keyboard|safari|...)",
  "role": "string (inferred principal role)",
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
> exists for implementations that choose to include it.

#### 3.5 `aix_identity` (9-DIM snapshot)

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

#### 3.6 `aix_trace` (provenance of the file)

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

| Format | Purpose | Identity Graph | Local-first | PII Layer |
|---|---|---|---|---|
| **.aix** (this) | Episodic identity | ✅ 9-DIM | ✅ | ✅ |
| PAM (arXiv:2605.11032) | Memory transfer | ✗ | ✗ | ✗ |
| MemGPT context | Session context | ✗ | ✗ | ✗ |
| JSON-LD | Linked data | ✗ | ✓ | ✗ |

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

---

### 10. Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

Geometrical maintains the spec through v0.x. Governance will open to the
community at v1.0.
