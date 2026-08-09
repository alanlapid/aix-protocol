# .aix in Enterprise Contexts (Soma)

## Overview

Soma is the institutional memory substrate — the same AIX Protocol
applied to organizations instead of individuals. A Soma instance
ingests organizational knowledge (contracts, emails, decisions,
communications) and serves it to agents operating within the
organization's perimeter.

## How Soma Uses `.aix`

Every piece of institutional memory is an `.aix` envelope. Soma adds
enterprise-specific fields (all defined in `AIX-SPEC.md`, not
Soma-specific extensions to the schema):

- `doc_type` — categorizes the source
  (`contract`|`email`|`meeting`|`policy`|`decision`).
- `token_budget` — enables agents to plan context usage.
- `federate` — controls what individual employees can access, and what
  crosses into partner perimeters.

## Token Reduction in Enterprise Contexts

`.aix` reduces token consumption for enterprise agents by 35–78% vs.
raw document injection, through:

1. **Knowledge Compiler**: deduplication + JSON distillation before
   packaging.
2. **Role-scoped retrieval**: agents receive only the fields their role
   permits (via `federate`).
3. **`token_budget` field**: agents can request compressed
   representations when budget is constrained.

For a 1,000-document corpus:

| Approach | Estimated tokens |
|---|---|
| Raw text injection | ~2.4M |
| `.aix` with Knowledge Compiler | ~520K–1.56M |
| Role-scoped `.aix` (employee view) | ~180K–400K |

## Compliance

`.aix` is designed for regulated industries:

- **GDPR Art. 4(5)**: pseudonymization via the PII layer (Patent
  Application P202631047, OEPM).
- **Data minimization**: `federate.fields[]` limits what crosses
  perimeters — a receiving org sees only the content fields it was
  explicitly granted, never the full memory record.
- **Right to erasure**: memory records are individual units — deletion
  is surgical, not bulk.
- **Audit trail**: `signature`/Merkle root (Section 11.3) enables
  tamper detection across the envelope's lifecycle.

## Example: Banking Use Case

A financial institution (Euro Exchange Bank pattern):

1. Soma ingests: contracts, client communications, internal decisions.
2. Each document becomes one or more `.aix` envelopes.
3. `federate` rules define:
   - Advisors see `decisions` + `skills`, but not `text`.
   - The compliance team sees all fields.
   - External agents see only metadata.
4. Agents query Soma via the Self Memory API.
5. PII never crosses the perimeter in raw form.

See [`examples/soma_contract.aix`](examples/soma_contract.aix) for a
concrete example.

## Relationship with Self and Nexus

Individual employees have Self instances. The organization has a Soma
instance. **Nexus** governs what flows between them.

A Self envelope from an employee can federate specific fields to Soma
(e.g., `skills`, `availability`) without exposing personal decisions or
communications — see `AIX-SPEC.md` Section 11 for the full protocol.
