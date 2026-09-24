# .aix vs. Open Knowledge Format and Portable Agent Memory

> Draft, 2026-09-24. Written after reading each specification (sources below).
> Decision per format: **compete**, **wrap**, or **export**.

## Sources read

- **OKF** — Google Cloud, *Open Knowledge Format*, spec v0.2:
  https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
  (canonical repo: https://github.com/GoogleCloudPlatform/open-knowledge-format)
- **PAM** — Ravindran, *Portable Agent Memory: A Protocol for
  Cryptographically-Verified Memory Transfer Across Heterogeneous AI Agents*,
  arXiv 2605.11032 (full HTML text).

## What each one is

| | OKF v0.2 | PAM (2605.11032) | .aix v0.3 draft |
|---|---|---|---|
| Unit | Bundle of Markdown files with YAML frontmatter, one concept per file | JSON (or CBOR) document with five components E/S/P/W/I | JSON-LD document of records |
| Required fields | `type` only | `id`, `parent_ids`, `created_at`, `version` per entry | `@id`, `@type`, `gm:recordedAt`, `prov:wasAttributedTo` per record |
| Shared vocabulary | Own conventions | None (inline Pydantic models) | schema.org + OWL-Time + PROV-O, `gm:` delta only |
| Memory types | Knowledge concepts (docs, metrics, runbooks) | Episodic, semantic, procedural, working, identity | Episodic (`InstantaneousEvent`, Actions), semantic (`gm:Fact`, entities), procedural (`HowTo`), plans (`PlanAction`), eras |
| Provenance | `sources`, `generated`, `verified` | Merkle-DAG over content-addressed entries (BLAKE3), Ed25519-signed root | `prov:wasDerivedFrom` / `prov:wasAttributedTo` per record; Merkle root (no signature yet) |
| Access control | Out of scope ("not prescribing") | Capability tokens: scope expressions, `read/write/derive/redact/export/rehydrate`, audience, `expires_at` | `gm:scope` + permissions in the document; authorization at serve time is the producer's (Nexus) |
| Revocation | — | Expiry; revoked tokens rejected in tests, no registry described | Revocation applied at serve time and to compiled-but-undelivered content |
| Time | ISO 8601 with offset | Timestamps; validity periods listed as **future work** | Honest precision, intervals with Allen relations over partial information, bi-temporal (`gm:recordedAt`) |
| Roles / reviewed claims | — | — | `Role` with dates; `ClaimReview` |
| Privacy | Out of scope | Redaction with typed tokens | `gm:sensitivity` (sensitive never leaves), `gm:piiProtected` |
| Injection resistance | — | Structural framing, escaping, content-type quarantine at rehydration | Delivery profile: data-not-instructions directive + role-marker escaping |
| Encoding | Markdown | JSON, optional CBOR (−31 %) | JSON; delivery profile −88 % vs. v0.2 envelope |

## Decisions

**OKF → export.** OKF is a knowledge wiki format with no access control or
privacy by design; .aix is a personal episodic memory with permissions.
They do not compete. Procedures (`HowTo`) and curated concepts map
naturally to OKF concept files (`type`, `title`, `description`, `sources`,
`generated`, `verified`). Action: an `.aix → OKF bundle` exporter for
procedural and concept records, never for personal or sensitive records.

**PAM → wrap.** PAM overlaps most with .aix and is stronger in transport
security: signed Merkle-DAG root, capability tokens with scope expressions,
injection-resistant rehydration. .aix is stronger in semantics: shared
vocabulary, honest time and validity intervals (future work in PAM), roles
with dates, reviewed claims, sensitivity that fails closed, and revocation
applied to compiled content. Competing on transport would duplicate a
working design. Actions:
1. A PAM ↔ .aix bridge: PAM semantic triples ↔ `gm:Fact`, episodic ↔
   `InstantaneousEvent`, procedural ↔ `HowTo`, working ↔ `PlanAction`.
2. Adopt a signed integrity root (Ed25519) as an optional `gm:integrity`
   field.
3. Keep the delivery-framing idea (already adopted in the delivery profile).

## Correction needed in the published v0.2

The comparison table in `AIX-SPEC.md` §7 and `README.md` (v0.2) marks PAM
with ✗ for PII layer and federation. Having read the paper, that is
inaccurate: PAM has capability-based scoped disclosure (a permission model
comparable to federation) and a redaction pipeline for personal
information. The same table claims "35–78 %" token reduction for .aix; the
source of that range is not documented in the repository and should be
sourced or replaced by the measured delivery figure (§8 of the v0.3
draft). Proposed fix: this draft branch updates both tables; publishing it
is the maintainer's decision.
