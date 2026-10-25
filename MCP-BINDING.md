# `.aix` over MCP — Binding v0.1

> MCP is the pipe. `.aix` is the payload.

Status: **draft**, October 2026. Defined in the AIX Protocol paper
v1.1, Section 7 ([DOI 10.5281/zenodo.23640824](https://doi.org/10.5281/zenodo.23640824)).
Reference server: [`aix_mcp_server.py`](aix_mcp_server.py).

The key words MUST, MUST NOT, SHOULD and MAY are to be interpreted as
described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

---

## 1. Why a binding

The [Model Context Protocol](https://modelcontextprotocol.io) standardises
how a host discovers a server, negotiates capabilities, authorises, calls
tools and reads resources. It does not standardise what a *memory* looks
like. Memory servers today answer a recall with free text or an ad-hoc
JSON shape, so the receiving agent cannot verify integrity, plan its
context budget, or tell which fields it was allowed to see.

This binding carries `.aix` envelopes inside ordinary MCP messages.

Constraints:

1. No change to MCP core: only resources, tools, embedded resources,
   `_meta` and extensions are used.
2. Targets MCP revision **2026-07-28** (stateless) and degrades to
   **2025-11-25**.
3. No breaking change to the `.aix` v0.2 schema. One optional field is
   added: `signature.derived_from`.
4. Nexus decisions are taken **before** serialisation into any MCP
   message.

### Why the payload must carry the state

MCP 2026-07-28 removed the `initialize` handshake and the
`Mcp-Session-Id` header. Servers that need cross-call state must pass
explicit handles. A `.aix` envelope is such a handle: self-contained,
versioned, signed, carrying its own budget and permissions. Memory
continuity lives in the payload, not in the connection. The envelope's
`session_id` is application-level and unrelated to the removed header.

---

## 2. Mapping

| MCP construct | `.aix` binding |
|---|---|
| `Resource.uri` | `aix://{perimeter_type}/{scope_id}/{envelope_id}` — e.g. `aix://soma/acme_legal/env_7f3a` ([RFC 3986](https://www.rfc-editor.org/rfc/rfc3986) custom scheme) |
| `ResourceTemplate.uriTemplate` | `aix://{perimeter_type}/{scope_id}/recall{?q,memory_roles,max_tokens}` ([RFC 6570](https://www.rfc-editor.org/rfc/rfc6570)) |
| `mimeType` | `application/x-aix-memory; version=0.2` (spec §3.1 plus version parameter) |
| `size` | bytes of the serialised **derived** envelope |
| `_meta` | `com.thegeometrical.aix/tokenBudget` mirrors `token_budget` |
| `annotations.audience` | `["assistant"]` |
| `annotations.priority` | highest `epic_score` in the envelope, clamped to `[0,1]` |
| `annotations.lastModified` | `aix_envelope.updated_at` |
| `cacheScope` / `ttlMs` | always `"private"`; `ttlMs` set by the server (0 when STM-tier records are included) |
| `tools/call` | `structuredContent` = derived envelope; `outputSchema` describes `.aix` |
| `EmbeddedResource` | envelope inlined in a prompt or tool result (`type: "resource"`) |
| `capabilities.extensions` | `com.thegeometrical/aix` (§3) |

`perimeter_type` is the part of the Nexus perimeter key before the colon
(`self`, `soma`, `axis`); `scope_id` is the part after it. `public` uses
`-` as `scope_id`.

---

## 3. Extension declaration

The binding is an **unofficial** MCP extension in the sense of
[SEP-2133](https://modelcontextprotocol.io/community/seps/2133-extensions),
identified with the reverse-DNS prefix of its maintainer.

Servers advertise it in `server/discover` (and in the legacy
`initialize` result):

```json
"extensions": {
  "com.thegeometrical/aix": {
    "versions": ["0.2"],
    "perimeters": ["self", "soma", "axis"],
    "integrity": ["merkle-sha256"],
    "piiProtected": true
  }
}
```

Clients on 2026-07-28 send `"extensions": {"com.thegeometrical/aix": {}}`
inside `io.modelcontextprotocol/clientCapabilities` in the `_meta` of
each request. On earlier revisions they send it in the `initialize`
capabilities.

**Graceful degradation.** A client that does not advertise the extension
gets no `outputSchema` in `tools/list` and no `structuredContent` in
`tools/call` — only a `TextContent` rendering of the **already derived**
envelope.

---

## 4. Recall as a tool

`aix_recall` arguments (all optional):

| Argument | Type | Meaning |
|---|---|---|
| `q` | string | case-insensitive filter over granted fields |
| `memory_roles` | string[] | memory roles to include (`memories[].role`) |
| `max_tokens` | integer ≥ 1 | token budget for the result |

Result (abridged):

```json
{
  "resultType": "complete",
  "structuredContent": {
    "aix_envelope": {
      "aix_version": "0.2",
      "pii_protected": true,
      "token_budget": { "max_tokens": 2000, "used_tokens": 448, "compression": "none" },
      "signature": {
        "algorithm": "merkle-sha256",
        "root": "bf5b…",
        "derived_from": "61c2…"
      }
    },
    "memories": [
      { "id": "…", "tier": "ltm", "role": "legal_analyst",
        "content": { "decisions": ["…"], "entities": ["[PERSONA_1]"] } }
    ]
  },
  "content": [
    { "type": "text", "text": "3 .aix memories visible to soma:acme_corp_advisory: …" }
  ],
  "_meta": {
    "com.thegeometrical.aix/sources": [
      { "uri": "aix://soma/acme_corp_advisory/soma_contract", "root": "61c2…" }
    ]
  }
}
```

MCP recommends returning the serialised JSON as text alongside
`structuredContent`. The binding allows a distilled rendering instead,
subject to the same filter (§5, C3).

---

## 5. Permissions and integrity across the pipe

**Who is asking.** The requesting perimeter and role come from the
authorization context — the OAuth access token issued for that
perimeter in an HTTP deployment, or deployment configuration for stdio.
They are never read from request `_meta` or tool arguments, which are
client-asserted and therefore untrusted.

**Nexus decision** (per envelope):

- `federate` absent → PRIVATE default (spec §4): only a `self:*`
  perimeter, and only if `permissions.read` contains `"self"`.
- `federate` present → the perimeter's rule must exist, list the
  requester's role (or `"*"`), and not be past `expires_at` at request
  time.

**Derived envelope.** What crosses the pipe is a *derived* envelope:

- `content.*` fields not granted are **omitted**, not masked. Records
  with no granted non-empty field are dropped.
- `trace` and `embeddings` are not `content.*` fields, so Nexus cannot
  grant them: they are dropped for every perimeter except `self`.
- `aix_identity` is dropped for every perimeter except `self`.
- `federate` keeps **only the requester's own rule**; other perimeters'
  grants are not disclosed.
- `checksum` and `signature.root` are recomputed over the disclosed
  records.
- An envelope the requester cannot see is answered exactly like one
  that does not exist (`-32602`).

**One filter, every channel.** `structuredContent`, the text fallback,
embedded resources and every `resource_link` target are rendered from
the same derived envelope. A text rendering that exposes a field absent
from the structured result is a conformance failure.

**`signature.derived_from`** (new, optional, proposed for spec v0.3):

- Single envelope: the original envelope's `signature.root` (or its
  computed Merkle root if it was unsigned).
- Merged recall over several envelopes: the Merkle root over the
  source roots, which are listed in the result `_meta` under
  `com.thegeometrical.aix/sources`.

This proves internal consistency, not who signed. Signer keys remain a
Nexus v0.2 item.

**Privacy before the pipe.** When `pii_protected` is `true`, the
transformation described in spec §5 has been applied before the envelope
enters the MCP result, so neither the MCP host nor the model provider
receives raw identifiers. How that transformation works is
implementation-defined and out of scope here.

**Budget.** `max_tokens` bounds the result; the server keeps the
highest-`epic_score` records first and reports `used_tokens`. Token
counts are a planning heuristic (spec §3.6), not a tokenizer guarantee.
Sending only what the task needs is
[Minimum Viable Exposure](https://doi.org/10.5281/zenodo.23457060)
applied at the transport boundary.

---

## 6. Conformance

A conforming `.aix`-over-MCP server:

| # | Requirement |
|---|---|
| C1 | MUST label envelopes `application/x-aix-memory` and MUST set `cacheScope: "private"` on every cacheable result (`resources/list`, `resources/read`) that exposes one. |
| C2 | MUST derive perimeter and role from the authorization context and MUST apply `federate` before serialisation. |
| C3 | MUST apply the same filter to every content channel of a result. |
| C4 | MUST recompute `signature.root` for derived envelopes and SHOULD populate `signature.derived_from`. |
| C5 | MUST honour `expires_at` at request time. |
| C6 | SHOULD honour `max_tokens` and report `used_tokens`. |
| C7 | SHOULD provide a text fallback for clients without the extension. |
| C8 | MUST NOT require any change to MCP core methods. |

`tests/test_aix_mcp_server.py` exercises each item against the reference
server (tests are tagged with the item they cover).

---

## 7. Reference server

[`aix_mcp_server.py`](aix_mcp_server.py) — Python standard library only,
stdio transport.

```bash
python aix_mcp_server.py --store examples \
  --perimeter soma:acme_corp_advisory --role advisor
```

Implements `server/discover`, `tools/list`, `tools/call` (`aix_recall`),
`resources/list`, `resources/templates/list`, `resources/read`, and the
legacy `initialize` handshake for 2025-11-25 hosts.

Example host configuration (the `mcpServers` format used by several
desktop hosts — check your host's documentation):

```json
{
  "mcpServers": {
    "aix": {
      "command": "python3",
      "args": [
        "/path/to/aix-protocol/aix_mcp_server.py",
        "--store", "/path/to/your/aix/files",
        "--perimeter", "self:my_laptop",
        "--role", "owner"
      ]
    }
  }
}
```

Not included: HTTP transport, OAuth, the `io.modelcontextprotocol/tasks`
extension, subscriptions, and any PII transformation (envelopes are
served as stored).

---

## 8. What this binding does not change

- No MCP core method is added.
- `aix_version` stays `0.2`; `signature.derived_from` is optional.
- No privacy-transformation mechanism is specified.
- Key exchange for envelope signing and revocation of `federate` grants
  remain Nexus v0.2 work. MCP with OAuth supplies transport and
  perimeter authentication, which Nexus v0.1 had deferred.

---

*Built by [Geometrical](https://thegeometrical.com) · October 2026*
