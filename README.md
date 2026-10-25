# aix-protocol

> The open format for portable episodic identity memory.

[![Spec Version](https://img.shields.io/badge/spec-v0.2-orange)](AIX-SPEC.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-draft-yellow)](https://github.com/alanlapid/aix-protocol)
[![Tests](https://github.com/alanlapid/aix-protocol/actions/workflows/test.yml/badge.svg)](https://github.com/alanlapid/aix-protocol/actions/workflows/test.yml)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.23640824-blue)](https://doi.org/10.5281/zenodo.23640824)

## The Problem

AI agents accumulate rich episodic context — events, decisions, roles,
intentions — but that context is trapped in vendor silos. There is no
standard format for transporting, storing, and sharing episodic memory
across agents, devices, and sessions.

When you switch agents, you start from zero.
When you switch devices, you start from zero.
When the vendor changes their memory policy, you lose everything.

## The Solution

`.aix` is an open, agent-native envelope for portable episodic identity
memory.

It carries not just what happened, but who you are: active roles,
intentions, goals, causal decision chains, and how much to trust each
stored belief.

Key properties:

- **Local-first**: works without cloud, without external API
- **Agent-native**: M2M format, not compressed human text
- **Privacy-preserving**: PII transformation before transmission
- **Portable**: iOS, Android, macOS, Linux, wearables
- **Versioned**: semantic versioning of the episodic substrate

## AIX Protocol Stack

```
AIX Protocol
├── .aix format     — the memory envelope (this spec)
├── Nexus v0.1      — permission and federation layer
│   ├── federate    — granular field-level permissions
│   ├── perimeters  — self / soma / axis / public
│   └── integrity   — Merkle signature
└── Transport       — MCP binding (MCP-BINDING.md)

Used by:
├── Self    — personal episodic memory substrate
├── Soma    — institutional memory substrate
└── Axis    — autonomous agent memory substrate
```

Nexus v0.1 ships inside this repo (`AIX-SPEC.md` Section 11) — it'll
move to its own repository once it outgrows being a subsection here.

## `.aix` over MCP

MCP is the pipe. `.aix` is the payload.

MCP standardises how agents reach servers; it does not standardise what
a memory looks like. [`MCP-BINDING.md`](MCP-BINDING.md) carries `.aix`
envelopes inside ordinary MCP resources and tool results, with Nexus
permissions applied before anything is serialised. No change to MCP
core. Targets the stateless MCP revision 2026-07-28.

Run the reference server (stdlib only, stdio):

```bash
python aix_mcp_server.py --store examples \
  --perimeter soma:acme_corp_advisory --role advisor
```

The advisor perimeter receives `decisions` and `entities` from
`examples/soma_contract.aix` — never `text` — with a recomputed Merkle
root that points back to the original via `signature.derived_from`.

## Token Reduction

`.aix` reduces context token consumption by 35–78% vs. raw text
injection through Knowledge Compiler preprocessing (deduplication +
JSON distillation).

The `token_budget` field enables agents to plan context usage before
loading an envelope. See `AIX-SPEC.md` Section 3.6 and, for the
enterprise-scale numbers, `SOMA-USAGE.md`.

## Quick Start

pip install (not yet on PyPI — clone and import directly)

```python
from aix_parser import AIXEnvelope, AIXMemory

# Create an envelope
env = AIXEnvelope(
    subject_id="user_opaque_hash",
    device_id="device_opaque_hash",
    session_id="session_001"
)

# Add a memory
mem = AIXMemory(
    source="apple_notes",
    role="founder",
    content={
        "text": "Decided to close pre-seed before Q4.",
        "decisions": ["close pre-seed before Q4"],
        "entities": ["Geometrical", "pre-seed"]
    }
)
env.add_memory(mem)

# Save
env.to_file("my_memory.aix")

# Load
env2 = AIXEnvelope.from_file("my_memory.aix")
```

## Specification

Read the full spec: [AIX-SPEC.md](AIX-SPEC.md) · MCP binding:
[MCP-BINDING.md](MCP-BINDING.md)

## Papers

| Paper | Version | DOI |
|---|---|---|
| AIX Protocol: An Open Format for Portable Episodic Identity Memory with Permission-Scoped Federation | v1.1 (Oct 2026) — adds `.aix` over MCP | [10.5281/zenodo.23640824](https://doi.org/10.5281/zenodo.23640824) |
| | v1.0 (Aug 2026) | [10.5281/zenodo.21923809](https://doi.org/10.5281/zenodo.21923809) |
| Minimum Viable Exposure | v1.0 (Oct 2026) | [10.5281/zenodo.23457060](https://doi.org/10.5281/zenodo.23457060) |

## Comparison

| Format | Episodic identity | Local-first | PII layer | Federation | Token reduction |
|---|---|---|---|---|---|
| **.aix** (this) | ✅ 9-DIM | ✅ | ✅ patent | ✅ Nexus | ✅ 35–78% |
| PAM (MS, 2605.11032) | ✗ | ✗ | ✗ | ✗ | ✗ |
| MemGPT context | ✗ | ✗ | ✗ | ✗ | ✗ |
| JSON-LD | ✗ | ✓ | ✗ | ✗ | ✗ |

Same table lives in `AIX-SPEC.md` Section 7, kept in sync with this one.

## Use Cases

- [Personal Memory (Self)](AIX-SPEC.md)
- [Enterprise Memory (Soma)](SOMA-USAGE.md)
- [Agent Memory (Axis)](AIX-SPEC.md) — no dedicated Axis section yet;
  Axis consumes the same `.aix` format as Self and Soma.
- [Federation (Nexus)](AIX-SPEC.md#11-nexus-protocol-v01)

## Why Open?

The episodic identity layer is infrastructure, not product.

No one monetizes TCP/IP. No one monetizes JSON.
Everyone monetizes what they build on top.

`.aix` is the protocol. [Geometrical](https://thegeometrical.com) builds
Self, Soma, Nexus, and Axis — the surfaces that implement it with
production quality, privacy guarantees, and enterprise governance.

Publishing `.aix` open means:

- Any agent can read and write episodic memory portably
- Users own their memory across vendors and devices
- The ecosystem grows around a shared standard
- Geometrical is the origin of that standard

## Implementations

| Project | Type | Status |
|---|---|---|
| [Self](https://thegeometrical.com) | Personal episodic substrate | v1.1 production |
| Your project here | — | Submit a PR |

## Badge

Add this to your README if your project implements `.aix`:

```markdown
[![Implements .aix](https://img.shields.io/badge/implements-.aix-orange)](https://github.com/alanlapid/aix-protocol)
```

[![Implements .aix](https://img.shields.io/badge/implements-.aix-orange)](https://github.com/alanlapid/aix-protocol)

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
Governance opens to the community at v1.0.

---

*Built by [Geometrical](https://thegeometrical.com) · Patent P202631047 (OEPM) · August 2026*
