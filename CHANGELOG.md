# Changelog

All notable changes to the `.aix` format and its reference implementation
are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning
follows the rules in `AIX-SPEC.md` Section 6 (semantic versioning of the
spec itself, independent of `substrate_version`).

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
