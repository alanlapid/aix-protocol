# aix-protocol

> The open format for portable episodic identity memory.

[![Spec Version](https://img.shields.io/badge/spec-v0.1-orange)](AIX-SPEC.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Status](https://img.shields.io/badge/status-draft-yellow)](https://github.com/alanlapid/aix-protocol)
[![Tests](https://github.com/alanlapid/aix-protocol/actions/workflows/test.yml/badge.svg)](https://github.com/alanlapid/aix-protocol/actions/workflows/test.yml)

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

Read the full spec: [AIX-SPEC.md](AIX-SPEC.md)

## Why Open?

The episodic identity layer is infrastructure, not product.

No one monetizes TCP/IP. No one monetizes JSON.
Everyone monetizes what they build on top.

`.aix` is the protocol. [Geometrical](https://geometrical.ai) builds
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
| [Self](https://geometrical.ai) | Personal episodic substrate | v1.1 production |
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

*Built by [Geometrical](https://geometrical.ai) · Patent P202631047 (OEPM) · August 2026*
