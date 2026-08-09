# Examples

All four files below were generated with the reference parser
(`aix_parser.py`) and pass `AIXEnvelope.validate()`. To regenerate or
inspect them yourself:

```python
from aix_parser import AIXEnvelope
env = AIXEnvelope.from_file("examples/minimal.aix")
print(env.validate())
```

## `minimal.aix`

The smallest valid `.aix` file: only required fields, a single memory,
no identity snapshot, default `PRIVATE` permissions.

## `full.aix`

A complete example exercising every dimension of the format: 3 memories
across different sources and tiers (`stm`/`mtm`/`ltm`), a populated
`aix_identity` (roles, goals, intentions, graph stats), spatiotemporal
trace on one memory, and `SHARED_SELF`-style permissions
(`share: ["self"]` — see AIX-SPEC.md Section 4). `pii_protected: false`
throughout — all content is fictional/illustrative, not real personal
data.

## `pii_protected.aix`

Same shape as `full.aix`, but `pii_protected: true` at both the envelope
and memory level, and the memory's `content` uses bracketed placeholder
tokens (`[PERSONA_1]`, `[PROYECTO_1]`, `[EMAIL_1]`) instead of real
values — demonstrating that the format can carry already-transformed
content.

**These tokens are illustrative only.** They are not what
Geometrical's reference implementation actually produces. The real
transformation mechanism is implementation-defined per AIX-SPEC.md
Section 5; Geometrical's own mechanism is covered by Patent Application
P202631047 (OEPM) and is intentionally not described in this open-source
repository.

## `soma_contract.aix`

An enterprise example (v0.2) — a Soma instance ingesting a fragment of a
contract, exercising the fields introduced by `.aix` v0.2: `doc_type`
(all three memories tagged `"document"`), `token_budget`, a real
`signature`/Merkle root (computed via `AIXEnvelope.sign()`, not a
placeholder), and `federate` with two role-scoped grants to the same
organization — `legal_team` (all `content` fields) and `advisor` (only
`decisions` and `entities`, read-only, with an expiry date). See
`SOMA-USAGE.md` for the full enterprise usage guide this example
supports.

`pii_protected: true` throughout — the 3 memories' `content.text` use
bracketed placeholder tokens (`[PERSONA_1]`, `[PROYECTO_1]`, ...), same
illustrative-only caveat as `pii_protected.aix` above. All content
(contract clauses, party names, organization name) is fictional.

**Note on `federate` keys**: the format (Section 3.5/11.1) is one
`fields` grant per perimeter key, so two different access levels for
the *same* organization need two distinct keys —
`soma:acme_corp_legal` and `soma:acme_corp_advisory` — rather than
one `soma:acme_corp` entry repeated twice (JSON object keys must be
unique). Both still follow the `soma:{org_id}` shape.
