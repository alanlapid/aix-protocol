# Changelog

All notable changes to the `.aix` format and its reference implementation
are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning
follows the rules in `AIX-SPEC.md` Section 6 (semantic versioning of the
spec itself, independent of `substrate_version`).

## [0.3.0-draft] — October 2026

### Added

- `MCP-BINDING.md`: `.aix` over MCP, binding v0.1 — MCP is the pipe,
  `.aix` is the payload. Targets MCP revision 2026-07-28 (stateless),
  degrades to 2025-11-25. Defined in the AIX Protocol paper v1.1,
  Section 7 (DOI [10.5281/zenodo.23640824](https://doi.org/10.5281/zenodo.23640824))
- `aix_mcp_server.py`: reference MCP server (stdio, stdlib only) —
  `server/discover`, `tools/list`, `tools/call` (`aix_recall`),
  `resources/list`, `resources/templates/list`, `resources/read`, plus
  the legacy `initialize` handshake
- Unofficial MCP extension `com.thegeometrical/aix` (SEP-2133 naming)
- `signature.derived_from` (optional, proposed for spec v0.3): links a
  federated (derived) envelope to the root of the envelope it came from
- `tests/test_aix_mcp_server.py`: 26 tests covering conformance items
  C1–C8, including a stdio round-trip
- README: Papers section with Zenodo DOIs; MCP section

### Changed

- README stack diagram: transport is now the MCP binding

### Fixed

- `AIX-SPEC.md` §11.2 described `roles` as the *subject's* role, which
  contradicted §3.5 and `examples/soma_contract.aix` (where `roles` are
  roles of the receiving perimeter). §11.2 now matches §3.5. Wording
  only — no schema change

### Not changed

- `aix_version` stays `0.2`; existing files remain valid unchanged

## [0.2.0] — August 2026

### Added

- Nexus v0.1: permission and federation layer (`AIX-SPEC.md` §11)
- `federate` field: granular field-level permissions by role/perimeter
- `token_budget` field: context planning for agent consumers
- `signature` field: Merkle-SHA256 integrity verification
- `doc_type` field: content categorization (Self + Soma)
- `SOMA-USAGE.md`: enterprise usage guide with compliance notes
- `examples/soma_contract.aix`: enterprise example with federation
  (4th example file)
- `aix_delta.py`: semantic diff between `.aix` envelopes
  (`AIXDelta.compute()`/`.apply()`/`.from_history()`)
- `tests/test_aix_delta.py`: 7 tests for delta operations
- `AIXEnvelope.compute_merkle()`: Merkle root computation over `memories[]`
- `AIXEnvelope.sign()`: signature population
- `AIXEnvelope.set_token_budget()`: token budget declaration
- `AIXEnvelope.set_federate()`: Nexus permission rules
- `AIXMemory.set_doc_type()`: content type classification
- Token reduction documentation (35–78% benchmark, `AIX-SPEC.md` §3.6)
- Comparison table extended with PAM, Federation, and Token Reduction
  columns (`README.md` and `AIX-SPEC.md` §7, kept in sync)
- `README.md`: AIX Protocol stack diagram, Use Cases section

### Changed

- `aix_version` bumped to `0.2` — every new field is optional per the
  MINOR-version rule (`AIX-SPEC.md` §6); `v0.1` files remain valid
  unchanged (`examples/minimal.aix`, `full.aix`, `pii_protected.aix`
  are still literally tagged `0.1` and still pass `validate()`)
- CI: added `examples/soma_contract.aix` to the example-validation step

### Fixed

- `AIXEnvelope.to_dict()` now preserves the `aix_version` of a loaded
  file instead of overwriting it with the parser's current
  `AIX_VERSION` constant — a file loaded from disk no longer silently
  reports a different spec version than what it was actually written as
  (regression introduced by the version bump in this same release,
  caught before it ever shipped)

### Security

- IP grep expanded to catch additional patent-related terms; re-run
  against the full working tree and full git history before this
  release, 0 hits

## [0.1.0] — August 2026

### Added

- Initial specification (`AIX-SPEC.md`)
- `aix_envelope` with spatiotemporal trace
- 9-DIM identity snapshot (`aix_identity`)
- Memory record schema with 7 content fields (`text`, `entities`,
  `decisions`, `intentions`, `emotions`, `patterns`, `porques`)
- Permissions model (`PRIVATE`/`SHARED_SELF`/`SHARED_SOMA`/`PUBLIC`)
- PII transformation support (`pii_protected` field)
- Semantic versioning (`aix_version` + `substrate_version`)
- Reference parser in Python (stdlib only)
- Three example files (`minimal`, `full`, `pii_protected`)
- GitHub Actions CI (Python 3.10, 3.11, 3.12)
