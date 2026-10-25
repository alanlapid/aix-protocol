"""Tests for aix_mcp_server.py (.aix over MCP binding) -- stdlib unittest,
no third-party dependencies. Conformance items C1-C8 refer to
MCP-BINDING.md."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aix_mcp_server import (  # noqa: E402
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    ERR_UNSUPPORTED_PROTOCOL_VERSION,
    EXTENSION_ID,
    MIME_TYPE,
    AIXMCPServer,
    derive_envelope,
    merkle_root,
    render_text,
    verify_derived,
)
from aix_parser import AIXEnvelope, AIXMemory  # noqa: E402

EXAMPLES = ROOT / "examples"
SOMA = json.loads((EXAMPLES / "soma_contract.aix").read_text(encoding="utf-8"))
ADVISORY = "soma:acme_corp_advisory"
LEGAL = "soma:acme_corp_legal"


def _meta(with_extension: bool = True, version: str = "2026-07-28") -> dict:
    caps = {"extensions": {EXTENSION_ID: {}}} if with_extension else {}
    return {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientCapabilities": caps,
    }


def _call(server: AIXMCPServer, method: str, params: dict | None = None, **meta_kwargs) -> dict:
    params = dict(params or {})
    params["_meta"] = _meta(**meta_kwargs)
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


class TestMerkle(unittest.TestCase):
    def test_merkle_root_matches_parser(self):
        env = AIXEnvelope.from_file(str(EXAMPLES / "soma_contract.aix"))
        records = [m.to_dict() for m in env.memories]
        self.assertEqual(merkle_root(records), env.compute_merkle())


class TestFederation(unittest.TestCase):
    def test_advisor_sees_only_granted_fields(self):
        derived = derive_envelope(SOMA, ADVISORY, "advisor")
        self.assertIsNotNone(derived)
        for record in derived["memories"]:
            self.assertTrue(set(record["content"]) <= {"decisions", "entities"})
            self.assertNotIn("text", record["content"])
            self.assertNotIn("trace", record)
            self.assertNotIn("embeddings", record)

    def test_role_not_in_rule_is_denied(self):
        self.assertIsNone(derive_envelope(SOMA, ADVISORY, "legal_team"))

    def test_unknown_perimeter_is_denied(self):
        self.assertIsNone(derive_envelope(SOMA, "soma:someone_else", "advisor"))

    def test_expired_grant_is_denied(self):  # C5
        after_expiry = datetime(2027, 9, 1, tzinfo=timezone.utc)
        self.assertIsNone(derive_envelope(SOMA, ADVISORY, "advisor", now=after_expiry))

    def test_other_perimeters_rules_do_not_leak(self):
        derived = derive_envelope(SOMA, ADVISORY, "advisor")
        self.assertEqual(list(derived["aix_envelope"]["federate"]), [ADVISORY])
        self.assertNotIn("aix_identity", derived)

    def test_private_default_without_federate(self):
        full = json.loads((EXAMPLES / "full.aix").read_text(encoding="utf-8"))
        self.assertIsNone(derive_envelope(full, "soma:any_org", "employee"))
        self.assertIsNotNone(derive_envelope(full, "self:device_1", "owner"))

    def test_derived_signature_verifies_and_references_original(self):  # C4
        derived = derive_envelope(SOMA, ADVISORY, "advisor")
        self.assertTrue(verify_derived(derived))
        self.assertEqual(derived["aix_envelope"]["signature"]["derived_from"], SOMA["aix_envelope"]["signature"]["root"])
        derived["memories"][0]["content"]["decisions"] = ["tampered"]
        self.assertFalse(verify_derived(derived))

    def test_token_budget_is_honoured(self):  # C6
        full = derive_envelope(SOMA, LEGAL, "legal_team")
        tight = derive_envelope(SOMA, LEGAL, "legal_team", max_tokens=full["aix_envelope"]["token_budget"]["used_tokens"] - 1)
        self.assertLess(len(tight["memories"]), len(full["memories"]))
        self.assertLessEqual(tight["aix_envelope"]["token_budget"]["used_tokens"], tight["aix_envelope"]["token_budget"]["max_tokens"])

    def test_text_fallback_never_exposes_ungranted_text(self):  # C3
        derived = derive_envelope(SOMA, ADVISORY, "advisor")
        rendered = render_text(derived, ADVISORY)
        for record in SOMA["memories"]:
            self.assertNotIn(record["content"]["text"], rendered)


class TestServer(unittest.TestCase):
    def setUp(self):
        self.server = AIXMCPServer(EXAMPLES, ADVISORY, "advisor")

    def test_discover_advertises_extension(self):
        result = _call(self.server, "server/discover")["result"]
        self.assertIn(EXTENSION_ID, result["capabilities"]["extensions"])
        self.assertIn("2026-07-28", result["supportedVersions"])
        self.assertEqual(result["resultType"], "complete")

    def test_unsupported_version(self):
        response = _call(self.server, "tools/list", version="1999-01-01")
        self.assertEqual(response["error"]["code"], ERR_UNSUPPORTED_PROTOCOL_VERSION)

    def test_unknown_method(self):
        self.assertEqual(_call(self.server, "prompts/list")["error"]["code"], ERR_METHOD_NOT_FOUND)

    def test_cacheable_results_are_private(self):  # C1
        for method in ("tools/list", "resources/list", "resources/templates/list"):
            result = _call(self.server, method)["result"]
            self.assertEqual(result["cacheScope"], "private", method)
            self.assertIn("ttlMs", result)

    def test_resources_list_only_visible_envelopes(self):
        resources = _call(self.server, "resources/list")["result"]["resources"]
        self.assertEqual([r["name"] for r in resources], ["soma_contract"])
        entry = resources[0]
        self.assertEqual(entry["uri"], "aix://soma/acme_corp_advisory/soma_contract")
        self.assertTrue(entry["mimeType"].startswith(MIME_TYPE))
        self.assertEqual(entry["annotations"]["audience"], ["assistant"])

    def test_resources_read_returns_federated_envelope(self):
        result = _call(self.server, "resources/read", {"uri": "aix://soma/acme_corp_advisory/soma_contract"})["result"]
        derived = json.loads(result["contents"][0]["text"])
        self.assertTrue(verify_derived(derived))
        for record in derived["memories"]:
            self.assertNotIn("text", record["content"])
        self.assertEqual(result["cacheScope"], "private")

    def test_invisible_envelope_reads_as_not_found(self):
        response = _call(self.server, "resources/read", {"uri": "aix://soma/acme_corp_advisory/full"})
        self.assertEqual(response["error"]["code"], ERR_INVALID_PARAMS)

    def test_path_traversal_is_rejected(self):
        response = _call(self.server, "resources/read", {"uri": "aix://soma/acme_corp_advisory/..%2F..%2Fetc"})
        self.assertIn("error", response)

    def test_recall_template_read(self):
        uri = "aix://soma/acme_corp_advisory/recall?q=terminate&max_tokens=4000"
        derived = json.loads(_call(self.server, "resources/read", {"uri": uri})["result"]["contents"][0]["text"])
        self.assertGreaterEqual(len(derived["memories"]), 1)

    def test_recall_filters_by_memory_roles(self):
        # memory_roles filters memories[].role; it is not federate.roles
        args = {"name": "aix_recall", "arguments": {"memory_roles": ["legal_analyst"]}}
        kept = _call(self.server, "tools/call", args)["result"]["structuredContent"]
        self.assertEqual(len(kept["memories"]), 3)
        args["arguments"]["memory_roles"] = ["advisor"]
        dropped = _call(self.server, "tools/call", args)["result"]["structuredContent"]
        self.assertEqual(dropped["memories"], [])
        uri = "aix://soma/acme_corp_advisory/recall?memory_roles=legal_analyst"
        derived = json.loads(_call(self.server, "resources/read", {"uri": uri})["result"]["contents"][0]["text"])
        self.assertEqual(len(derived["memories"]), 3)

    def test_tools_call_with_extension(self):
        result = _call(self.server, "tools/call", {"name": "aix_recall", "arguments": {"max_tokens": 4000}})["result"]
        self.assertIn("structuredContent", result)
        self.assertTrue(verify_derived(result["structuredContent"]))
        self.assertEqual(result["content"][0]["type"], "text")
        sources = result["_meta"]["com.thegeometrical.aix/sources"]
        self.assertEqual(sources, [{"uri": "aix://soma/acme_corp_advisory/soma_contract", "root": SOMA["aix_envelope"]["signature"]["root"]}])
        self.assertEqual(result["structuredContent"]["aix_envelope"]["signature"]["derived_from"], merkle_root([s["root"] for s in sources]))

    def test_tools_call_without_extension_degrades_to_text(self):  # C7
        result = _call(self.server, "tools/call", {"name": "aix_recall", "arguments": {}}, with_extension=False)["result"]
        self.assertNotIn("structuredContent", result)
        self.assertEqual(result["content"][0]["type"], "text")
        tools = _call(self.server, "tools/list", with_extension=False)["result"]["tools"]
        self.assertNotIn("outputSchema", tools[0])

    def test_authorization_context_cannot_be_overridden_by_request(self):  # C2
        params = {"name": "aix_recall", "arguments": {}, "_meta": {**_meta(), "com.thegeometrical.aix/perimeter": "soma:acme_corp_legal", "com.thegeometrical.aix/role": "legal_team"}}
        result = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params})["result"]
        for record in result["structuredContent"]["memories"]:
            self.assertNotIn("text", record["content"])

    def test_invalid_max_tokens_is_tool_error(self):
        result = _call(self.server, "tools/call", {"name": "aix_recall", "arguments": {"max_tokens": 0}})["result"]
        self.assertTrue(result["isError"])

    def test_legacy_initialize_handshake(self):
        server = AIXMCPServer(EXAMPLES, ADVISORY, "advisor")
        init = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {"extensions": {EXTENSION_ID: {}}}, "clientInfo": {"name": "t", "version": "0"}},
            }
        )["result"]
        self.assertEqual(init["protocolVersion"], "2025-11-25")
        self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        result = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "aix_recall", "arguments": {}}})["result"]
        self.assertIn("structuredContent", result)

    def test_self_perimeter_with_fresh_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = AIXEnvelope(subject_id="s", device_id="d", session_id="x")
            env.add_memory(AIXMemory(source="notes", role="founder", content={"text": "Ship v1.1", "decisions": ["ship"]}))
            env.sign()
            env.to_file(str(Path(tmp) / "mine.aix"))
            server = AIXMCPServer(tmp, "self:d", "owner")
            derived = _call(server, "tools/call", {"name": "aix_recall", "arguments": {}})["result"]["structuredContent"]
            self.assertEqual(derived["memories"][0]["content"]["text"], "Ship v1.1")
            self.assertIn("trace", derived["memories"][0])
            # Fresh memories are STM-tier, so they must not be cached (C1).
            listing = _call(server, "resources/list")["result"]
            self.assertEqual(listing["ttlMs"], 0)
            self.assertEqual(listing["cacheScope"], "private")


class TestStdio(unittest.TestCase):
    def test_stdio_round_trip(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": _meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": _meta()}},
        ]
        proc = subprocess.run(
            [sys.executable, str(ROOT / "aix_mcp_server.py"), "--store", str(EXAMPLES), "--perimeter", ADVISORY, "--role", "advisor"],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ROOT,
        )
        lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual([line["id"] for line in lines], [1, 2])
        self.assertEqual(lines[1]["result"]["tools"][0]["name"], "aix_recall")


if __name__ == "__main__":
    unittest.main()
