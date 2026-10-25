"""
aix_mcp_server.py — Reference MCP server for the `.aix` over MCP binding
(MCP-BINDING.md, AIX Protocol paper v1.1, Section 7).

MCP is the pipe; `.aix` is the payload. This server exposes a folder of
`.aix` envelopes to any MCP host over stdio, applying Nexus v0.1
federation *before* anything is serialized into an MCP message.

Pure Python standard library, no third-party dependencies (same rule as
aix_parser.py). Targets MCP revision 2026-07-28 (stateless: no
`initialize`, per-request `_meta`, `server/discover`) and still answers
the legacy `initialize` handshake so 2025-11-25 hosts can connect.

Who is asking (perimeter + role) is bound at deployment time through
CLI flags / environment variables -- it is the authorization context.
It is NEVER read from request `_meta` or tool arguments (conformance C2).
An HTTP deployment would derive the same two values from the OAuth
access token instead.

Usage:
    python aix_mcp_server.py --store examples \\
        --perimeter soma:acme_corp_advisory --role advisor

Programmatic:
    from aix_mcp_server import AIXMCPServer
    server = AIXMCPServer(store="examples",
                          perimeter="soma:acme_corp_advisory", role="advisor")
    response = server.handle({"jsonrpc": "2.0", "id": 1,
                              "method": "tools/list", "params": {}})
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from aix_parser import AIX_VERSION, CONTENT_FIELDS, AIXEnvelope, _sha256_of

SERVER_NAME = "aix-reference-mcp-server"
SERVER_VERSION = "0.1.0"

EXTENSION_ID = "com.thegeometrical/aix"
META_PREFIX = "com.thegeometrical.aix"
MIME_TYPE = "application/x-aix-memory"
SUPPORTED_PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

# Keys MCP reserves inside _meta (2026-07-28, SEP-2575).
META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

# JSON-RPC / MCP error codes.
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602  # also "resource not found" since 2026-07-28
ERR_UNSUPPORTED_PROTOCOL_VERSION = -32022

DEFAULT_TTL_MS = 60_000
RECALL_TOOL = "aix_recall"

# Record metadata that survives federation. trace (location, local time)
# and embeddings are not content.* fields, so Nexus cannot grant them --
# a derived envelope never carries them (Minimum Viable Exposure).
RECORD_METADATA_KEPT = (
    "id",
    "timestamp",
    "source",
    "role",
    "doc_type",
    "tier",
    "epic_score",
    "verification_score",
    "pii_protected",
)


# ─── Binding logic (transport-independent) ────────────────────────────────


def merkle_root(records: list[dict[str, Any]]) -> str:
    """Same tree as AIXEnvelope.compute_merkle(), but over plain record
    dicts, so a derived (federated) envelope can be signed and verified
    without round-tripping through AIXMemory."""
    leaves = [_sha256_of(r) for r in records]
    if not leaves:
        return _sha256_of([])
    level = leaves
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.sha256((left + right).encode("utf-8")).hexdigest())
        level = nxt
    return level[0]


def estimate_tokens(obj: Any) -> int:
    """Planning heuristic (~4 characters per token), not a tokenizer --
    same status as token_budget in AIX-SPEC.md Section 3.6."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return max(1, (len(text) + 3) // 4)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def grant_for(
    envelope: dict[str, Any], perimeter: str, role: str, now: datetime | None = None
) -> dict[str, Any] | None:
    """Nexus v0.1 decision for (perimeter, role). Returns the effective
    grant {"fields": [...], "read_only": bool} or None (no access).

    - federate absent: PRIVATE default (AIX-SPEC.md Section 4) -- only a
      `self:*` perimeter listed in permissions.read sees the envelope.
    - federate present: the perimeter's rule must exist, list the role
      (or "*"), and not be expired at request time (conformance C5).
    """
    now = now or datetime.now(timezone.utc)
    env = envelope.get("aix_envelope", {})
    federate = env.get("federate")

    if federate is None:
        readers = (env.get("permissions") or {}).get("read", [])
        if perimeter.split(":", 1)[0] == "self" and "self" in readers:
            return {"fields": list(CONTENT_FIELDS), "read_only": False}
        return None

    rule = federate.get(perimeter)
    if not isinstance(rule, dict):
        return None
    roles = rule.get("roles") or []
    if "*" not in roles and role not in roles:
        return None
    expires = _parse_time(rule.get("expires_at"))
    if expires is not None and expires <= now:
        return None
    fields = rule.get("fields") or []
    if "*" in fields:
        fields = list(CONTENT_FIELDS)
    return {"fields": [f for f in fields if f in CONTENT_FIELDS], "read_only": bool(rule.get("read_only", True))}


def _record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in record.get("content", {}).values():
        parts.extend(value if isinstance(value, list) else [value])
    return " ".join(str(p) for p in parts).lower()


def derive_envelope(
    envelope: dict[str, Any],
    perimeter: str,
    role: str,
    *,
    query: str | None = None,
    memory_roles: list[str] | None = None,
    max_tokens: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Builds the derived envelope a (perimeter, role) is allowed to see.

    One filter for every channel (conformance C2/C3): the structured
    result, the text fallback and resource reads are all rendered from
    this dict and nothing else. Returns None when access is denied.
    """
    grant = grant_for(envelope, perimeter, role, now)
    if grant is None:
        return None
    fields = grant["fields"]
    source_env = envelope.get("aix_envelope", {})
    is_self = perimeter.split(":", 1)[0] == "self"

    records: list[dict[str, Any]] = []
    for original in envelope.get("memories", []):
        if memory_roles and original.get("role") not in memory_roles:
            continue
        content = {f: original.get("content", {}).get(f) for f in fields}
        content = {k: v for k, v in content.items() if v not in (None, "", [])}
        if not content:
            continue  # nothing granted in this record: omit it entirely
        record = {k: original[k] for k in RECORD_METADATA_KEPT if k in original}
        record["content"] = content
        if is_self:
            for k in ("embeddings", "trace"):
                if k in original:
                    record[k] = original[k]
        records.append(record)

    if query:
        q = query.lower()
        records = [r for r in records if q in _record_text(r)]

    # Highest EPIC weight first, so a token budget keeps what matters most.
    records.sort(key=lambda r: (r.get("epic_score") or 0.0), reverse=True)

    original_root = (source_env.get("signature") or {}).get("root") or merkle_root(
        envelope.get("memories", [])
    )

    def build(selected: list[dict[str, Any]]) -> dict[str, Any]:
        env_out: dict[str, Any] = {
            "aix_version": source_env.get("aix_version", AIX_VERSION),
            "created_at": source_env.get("created_at"),
            "updated_at": source_env.get("updated_at"),
            "subject_id": source_env.get("subject_id"),
            "session_id": source_env.get("session_id"),
            "memory_count": len(selected),
            "checksum": _sha256_of(selected),
            "permissions": {"read": [perimeter], "write": [], "share": []},
            "pii_protected": any(r.get("pii_protected") for r in selected),
            "substrate_version": source_env.get("substrate_version", "1.0"),
            "signature": {
                "algorithm": "merkle-sha256",
                "root": merkle_root(selected),
                "derived_from": original_root,
                "signed_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        if not grant["read_only"] and is_self:
            env_out["permissions"]["write"] = [perimeter]
        # Only the requester's own rule travels -- other perimeters'
        # grants are metadata the requester must not learn.
        if source_env.get("federate") is not None:
            env_out["federate"] = {perimeter: source_env["federate"][perimeter]}
        out = {"aix_envelope": env_out, "memories": selected}
        if is_self and "aix_identity" in envelope:
            out["aix_identity"] = envelope["aix_identity"]
        return out

    if max_tokens is not None:
        kept: list[dict[str, Any]] = []
        for record in records:
            if estimate_tokens(build(kept + [record])) > max_tokens:
                break
            kept.append(record)
        records = kept

    derived = build(records)
    derived["aix_envelope"]["token_budget"] = {
        "max_tokens": max_tokens if max_tokens is not None else estimate_tokens(derived),
        "used_tokens": estimate_tokens(derived),
        "compression": "none",
    }
    return derived


def verify_derived(derived: dict[str, Any]) -> bool:
    """Receiver-side check (conformance C4): the declared root matches the
    disclosed records. Proves internal consistency, not who signed."""
    sig = derived.get("aix_envelope", {}).get("signature") or {}
    return sig.get("root") == merkle_root(derived.get("memories", []))


def _has_stm(derived: dict[str, Any]) -> bool:
    return any(r.get("tier") == "stm" for r in derived.get("memories", []))


def render_text(derived: dict[str, Any], perimeter: str) -> str:
    """Text fallback for hosts without the extension. Rendered from the
    derived envelope only, so it cannot expose a field the structured
    result omits (conformance C3)."""
    memories = derived.get("memories", [])
    if not memories:
        return f"No .aix memories visible to {perimeter}."
    lines = [f"{len(memories)} .aix memories visible to {perimeter}:"]
    for record in memories:
        bits = []
        for field, value in record.get("content", {}).items():
            shown = "; ".join(value) if isinstance(value, list) else str(value)
            bits.append(f"{field}: {shown}")
        lines.append(f"- [{record.get('tier', '?')}] " + " | ".join(bits))
    return "\n".join(lines)


# ─── MCP server ───────────────────────────────────────────────────────────


class MCPError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class AIXMCPServer:
    """Stateless request handler. The only state is configuration: the
    envelope store and the authorization context (perimeter, role)."""

    def __init__(self, store: str | Path, perimeter: str, role: str, ttl_ms: int = DEFAULT_TTL_MS):
        if ":" not in perimeter and perimeter != "public":
            raise ValueError("perimeter must look like 'self:<id>', 'soma:<id>', 'axis:<id>' or 'public'")
        self.store = Path(store)
        self.perimeter = perimeter
        self.role = role
        self.ttl_ms = ttl_ms
        # Only used for legacy (2025-11-25) clients, which send
        # capabilities once in `initialize` instead of per request.
        self._legacy_client_capabilities: dict[str, Any] | None = None

    # -- store ---------------------------------------------------------------

    def _envelope_ids(self) -> list[str]:
        return sorted(p.stem for p in self.store.glob("*.aix"))

    def _load(self, envelope_id: str) -> dict[str, Any]:
        path = self.store / f"{envelope_id}.aix"
        if not path.is_file() or path.parent.resolve() != self.store.resolve():
            raise MCPError(ERR_INVALID_PARAMS, f"Resource not found: {envelope_id}")
        # Round-trip through the reference parser so malformed files fail
        # here, not halfway through federation.
        return AIXEnvelope.from_file(str(path)).to_dict()

    # -- URIs ----------------------------------------------------------------

    def _scope(self) -> tuple[str, str]:
        kind, _, scope_id = self.perimeter.partition(":")
        return kind, scope_id or "-"

    def _uri(self, envelope_id: str) -> str:
        kind, scope_id = self._scope()
        return f"aix://{kind}/{scope_id}/{envelope_id}"

    def _template(self) -> str:
        kind, scope_id = self._scope()
        return f"aix://{kind}/{scope_id}/recall{{?q,roles,max_tokens}}"

    # -- helpers -------------------------------------------------------------

    def _server_meta(self) -> dict[str, Any]:
        return {META_SERVER_INFO: {"name": SERVER_NAME, "version": SERVER_VERSION}}

    def _client_has_extension(self, params: dict[str, Any]) -> bool:
        caps = (params.get("_meta") or {}).get(META_CLIENT_CAPABILITIES)
        if caps is None:
            caps = self._legacy_client_capabilities or {}
        return EXTENSION_ID in (caps.get("extensions") or {})

    def _check_version(self, params: dict[str, Any]) -> None:
        requested = (params.get("_meta") or {}).get(META_PROTOCOL_VERSION)
        if requested is not None and requested not in SUPPORTED_PROTOCOL_VERSIONS:
            raise MCPError(
                ERR_UNSUPPORTED_PROTOCOL_VERSION,
                f"Unsupported protocol version: {requested}",
                {"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
            )

    def _complete(self, result: dict[str, Any], cacheable: bool = False, volatile: bool = False) -> dict[str, Any]:
        result["resultType"] = "complete"
        if cacheable:
            # STM-tier memory is still being consolidated: never fresh.
            result["ttlMs"] = 0 if volatile else self.ttl_ms
            result["cacheScope"] = "private"  # memory is subject-specific (C1)
        result.setdefault("_meta", {}).update(self._server_meta())
        return result

    def _capabilities(self) -> dict[str, Any]:
        return {
            "tools": {},
            "resources": {},
            "extensions": {
                EXTENSION_ID: {
                    "versions": [AIX_VERSION],
                    "perimeters": ["self", "soma", "axis"],
                    "integrity": ["merkle-sha256"],
                    "piiProtected": True,
                }
            },
        }

    def _resource_entry(self, envelope_id: str, derived: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(derived, ensure_ascii=False)
        epic = [r.get("epic_score") for r in derived["memories"] if isinstance(r.get("epic_score"), (int, float))]
        return {
            "uri": self._uri(envelope_id),
            "name": envelope_id,
            "title": f".aix envelope {envelope_id}",
            "mimeType": f"{MIME_TYPE}; version={derived['aix_envelope']['aix_version']}",
            "size": len(body.encode("utf-8")),
            "annotations": {
                "audience": ["assistant"],
                "priority": min(1.0, max(0.0, max(epic))) if epic else 0.5,
                "lastModified": derived["aix_envelope"].get("updated_at"),
            },
            "_meta": {f"{META_PREFIX}/tokenBudget": derived["aix_envelope"]["token_budget"]},
        }

    def _recall(
        self, query: str | None, memory_roles: list[str] | None, max_tokens: int | None
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        """Merges every visible envelope into one derived envelope.

        Returns (derived, sources). signature.derived_from of a merged
        recall is the Merkle root over the source envelopes' roots; the
        per-source roots travel in the MCP result _meta so a receiver can
        trace each one back."""
        merged: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []
        for envelope_id in self._envelope_ids():
            derived = derive_envelope(
                self._load(envelope_id), self.perimeter, self.role, query=query, memory_roles=memory_roles
            )
            if derived and derived["memories"]:
                merged.extend(derived["memories"])
                sources.append({"uri": self._uri(envelope_id), "root": derived["aix_envelope"]["signature"]["derived_from"]})
        now = datetime.now(timezone.utc).isoformat()
        container = {
            "aix_envelope": {
                "aix_version": AIX_VERSION,
                "created_at": now,
                "updated_at": now,
                "subject_id": "recall",
                "session_id": "recall",
                "permissions": {"read": ["self"], "write": [], "share": []},
                "federate": {self.perimeter: {"roles": [self.role], "fields": ["*"], "expires_at": None, "read_only": True}},
            },
            "memories": merged,
        }
        # Records are already federated; this pass only applies the budget
        # and signs the result.
        derived = derive_envelope(container, self.perimeter, self.role, max_tokens=max_tokens)
        assert derived is not None
        derived["aix_envelope"].pop("federate", None)
        derived["aix_envelope"]["signature"]["derived_from"] = merkle_root([s["root"] for s in sources])
        return derived, sources

    # -- methods -------------------------------------------------------------

    def _server_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._complete(
            {
                "supportedVersions": list(SUPPORTED_PROTOCOL_VERSIONS),
                "capabilities": self._capabilities(),
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Memories are .aix envelopes, already filtered by Nexus for this perimeter.",
            }
        )

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Legacy (2025-11-25) handshake. Kept so current hosts connect."""
        requested = params.get("protocolVersion")
        self._legacy_client_capabilities = params.get("capabilities") or {}
        version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[-1]
        return {
            "protocolVersion": version,
            "capabilities": self._capabilities(),
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }

    def _tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        tool: dict[str, Any] = {
            "name": RECALL_TOOL,
            "title": "Recall .aix memory",
            "description": (
                "Recall episodic memory as a .aix envelope, filtered by Nexus for this "
                "perimeter. Use max_tokens to bound the context size."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Case-insensitive text filter."},
                    "roles": {"type": "array", "items": {"type": "string"}, "description": "Memory roles to include."},
                    "max_tokens": {"type": "integer", "minimum": 1, "description": "Token budget for the result."},
                },
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False},
        }
        if self._client_has_extension(params):
            tool["outputSchema"] = {
                "type": "object",
                "required": ["aix_envelope", "memories"],
                "properties": {"aix_envelope": {"type": "object"}, "memories": {"type": "array"}},
            }
        return self._complete({"tools": [tool]}, cacheable=True)

    def _tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("name") != RECALL_TOOL:
            raise MCPError(ERR_INVALID_PARAMS, f"Unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        max_tokens = args.get("max_tokens")
        if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens < 1):
            return self._complete(
                {"content": [{"type": "text", "text": "max_tokens must be a positive integer."}], "isError": True}
            )
        derived, sources = self._recall(args.get("q"), args.get("roles"), max_tokens)
        result: dict[str, Any] = {
            "content": [{"type": "text", "text": render_text(derived, self.perimeter)}],
            "_meta": {f"{META_PREFIX}/sources": sources},
        }
        if self._client_has_extension(params):
            result["structuredContent"] = derived
        return self._complete(result)

    def _resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        resources = []
        volatile = False
        for envelope_id in self._envelope_ids():
            derived = derive_envelope(self._load(envelope_id), self.perimeter, self.role)
            if derived and derived["memories"]:
                resources.append(self._resource_entry(envelope_id, derived))
                volatile = volatile or _has_stm(derived)
        return self._complete({"resources": resources}, cacheable=True, volatile=volatile)

    def _resources_templates_list(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._complete(
            {
                "resourceTemplates": [
                    {
                        "uriTemplate": self._template(),
                        "name": "recall",
                        "title": "Recall .aix memory",
                        "mimeType": MIME_TYPE,
                        "annotations": {"audience": ["assistant"]},
                    }
                ]
            },
            cacheable=True,
        )

    def _resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri", "")
        parts = urlsplit(uri)
        kind, scope_id = self._scope()
        segments = parts.path.strip("/").split("/")
        if parts.scheme != "aix" or parts.netloc != kind or len(segments) != 2 or segments[0] != scope_id:
            raise MCPError(ERR_INVALID_PARAMS, f"Resource not found: {uri}")
        name = segments[1]
        if name == "recall":
            query = parse_qs(parts.query)
            max_tokens = query.get("max_tokens", [None])[0]
            derived, _ = self._recall(
                query.get("q", [None])[0],
                query["roles"][0].split(",") if "roles" in query else None,
                int(max_tokens) if max_tokens and max_tokens.isdigit() else None,
            )
        else:
            derived = derive_envelope(self._load(name), self.perimeter, self.role)
            if derived is None or not derived["memories"]:
                # Answered exactly like "does not exist": the requester
                # must not learn that an envelope it cannot see exists.
                raise MCPError(ERR_INVALID_PARAMS, f"Resource not found: {uri}")
        return self._complete(
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": f"{MIME_TYPE}; version={derived['aix_envelope']['aix_version']}",
                        "text": json.dumps(derived, ensure_ascii=False),
                    }
                ]
            },
            cacheable=True,
            volatile=_has_stm(derived),
        )

    METHODS = {
        "server/discover": "_server_discover",
        "initialize": "_initialize",
        "tools/list": "_tools_list",
        "tools/call": "_tools_call",
        "resources/list": "_resources_list",
        "resources/templates/list": "_resources_templates_list",
        "resources/read": "_resources_read",
    }

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handles one JSON-RPC message. Returns the response, or None for
        notifications."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return {"jsonrpc": "2.0", "id": None, "error": {"code": ERR_INVALID_REQUEST, "message": "Invalid request"}}
        if "id" not in message:
            return None  # notifications (e.g. notifications/initialized)
        msg_id = message["id"]
        params = message.get("params") or {}
        try:
            handler = self.METHODS.get(message["method"])
            if handler is None:
                raise MCPError(ERR_METHOD_NOT_FOUND, f"Method not found: {message['method']}")
            if message["method"] != "initialize":
                self._check_version(params)
            return {"jsonrpc": "2.0", "id": msg_id, "result": getattr(self, handler)(params)}
        except MCPError as exc:
            error: dict[str, Any] = {"code": exc.code, "message": exc.message}
            if exc.data is not None:
                error["data"] = exc.data
            return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def serve_stdio(server: AIXMCPServer) -> None:
    """Newline-delimited JSON-RPC over stdin/stdout (MCP stdio transport).
    Logs go to stderr only."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": ERR_PARSE, "message": "Parse error"},
            }
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Reference MCP server for .aix envelopes (stdio).")
    parser.add_argument("--store", default=os.environ.get("AIX_STORE", "examples"), help="Folder of .aix files.")
    parser.add_argument(
        "--perimeter",
        default=os.environ.get("AIX_PERIMETER"),
        help="Authorization context: requesting perimeter, e.g. soma:acme_corp_advisory.",
    )
    parser.add_argument(
        "--role", default=os.environ.get("AIX_ROLE"), help="Authorization context: requester's role, e.g. advisor."
    )
    parser.add_argument("--ttl-ms", type=int, default=DEFAULT_TTL_MS)
    args = parser.parse_args(argv)
    if not args.perimeter or not args.role:
        parser.error("--perimeter and --role are required (or AIX_PERIMETER / AIX_ROLE).")
    print(
        f"{SERVER_NAME} {SERVER_VERSION}: store={args.store} perimeter={args.perimeter} role={args.role}",
        file=sys.stderr,
    )
    serve_stdio(AIXMCPServer(args.store, args.perimeter, args.role, args.ttl_ms))


if __name__ == "__main__":
    main()
