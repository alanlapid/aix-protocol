"""Tests for the .aix v0.3 ↔ Portable Agent Memory bridge (aix_pam.py)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import aix_v03 as a  # noqa: E402

try:
    import blake3  # noqa: F401
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
    DEPS = True
except ImportError:
    DEPS = False

import aix_pam as ap  # noqa: E402

T = "2026-09-24T10:00:00+00:00"
FULL = json.loads((RAIZ / "examples" / "v0.3" / "full.aix.jsonld").read_text())


@unittest.skipUnless(DEPS, "needs blake3 and cryptography")
class TestPam(unittest.TestCase):
    def setUp(self) -> None:
        k = Ed25519PrivateKey.generate()
        self.priv = k.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        self.pub = k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.otra = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def test_entry_ids_match_the_sdk(self) -> None:
        # known answers computed with the PAM SDK's pydantic models (non-ASCII included)
        e = ap.entry("episodic", created_at=T, timestamp="2026-09-24", actor="agent:x", observation="Café ☕", salience=1)
        s = ap.entry("semantic", created_at=T, subject="a", predicate="b", object="c", confidence=1, source_event_ids=[e["id"]])
        self.assertEqual(e["id"], "blake3:9a73ae8cd296d48be128c1a98604c408b60e16403f490792139d1904e054f9f8")
        self.assertEqual(s["id"], "blake3:35cf201ac0a0ae67c2d93a42f1a4717d49c18a3e41597c5157fd536ba8382c12")

    def test_projection_signature_and_lossless_return(self) -> None:
        art = ap.sign(ap.to_pam(FULL), self.priv)
        self.assertEqual([len(art[c]) for c in ap.COMPONENTES], [2, 5, 1, 0, 1])
        fact = next(e for e in art["semantic"] if e["predicate"] == "worksFor" and "aix:status:active" in e["tags"])
        episodio = next(e for e in art["episodic"] if "aix:id:gm:episode/1" in e["tags"])
        self.assertEqual(fact["source_event_ids"], [episodio["id"]])
        self.assertTrue(ap.verify(art, self.pub))
        self.assertFalse(ap.verify(art, self.otra))
        self.assertEqual(ap.to_aix(art), FULL)

    def test_tampering_is_detected(self) -> None:
        art = ap.sign(ap.to_pam(FULL), self.priv)
        cambiada = json.loads(json.dumps(art))
        cambiada["semantic"][0]["object"] = "gm:entity/intruder"
        self.assertFalse(ap.verify(cambiada))
        # metadata is not hashed by PAM: a changed embedded document is not trusted
        meta = json.loads(json.dumps(art))
        meta["metadata"]["aix"]["gm:scope"] = "public"
        self.assertTrue(ap.verify(meta, self.pub))
        self.assertNotEqual(ap.to_aix(meta).get("gm:scope"), "public")

    def test_sensitive_records_never_cross_the_bridge(self) -> None:
        d = a.Document(subject="gm:subject/x", recorded_at=T)
        d.add(a.Record("gm:fact/1", "gm:Fact", T, "human:x", {"gm:subject": "gm:entity/x", "gm:predicate": "p",
                                                              "gm:object": "gm:entity/y", "gm:sensitivity": "sensitive"}))
        with self.assertRaises(ValueError):
            ap.to_pam(a.dump(d))

    def test_foreign_artifact_maps_to_a_valid_document(self) -> None:
        ep = ap.entry("episodic", created_at=T, timestamp="yesterday", actor="Some Agent", observation="asked for coffee")
        art = {"pam_version": "1.0", "created_at": T, "root_hash": "", "signature": "",
               "source_agent": {"name": "other", "model_family": "gpt", "runtime": "custom", "version": "1"},
               "episodic": [ep], "working": [ap.entry("working", created_at=T, goals=["book a table"])],
               "semantic": [ap.entry("semantic", created_at=T, subject="user", predicate="likes", object="coffee",
                                     source_event_ids=[ep["id"]])],
               "procedural": [ap.entry("procedural", created_at=T, name="brew", body="1. grind\n2. brew")], "identity": []}
        art = ap.sign(art, self.priv)
        doc = ap.to_aix(art)
        self.assertEqual(a.validate(doc)[0], [])
        tipos = sorted(r["@type"] for r in doc["@graph"])
        self.assertEqual(tipos, ["HowTo", "InstantaneousEvent", "PlanAction", "gm:Fact"])
        evento = next(r for r in doc["@graph"] if r["@type"] == "InstantaneousEvent")
        self.assertEqual((evento["pam:timestamp"], evento["prov:wasAttributedTo"]), ("yesterday", "agent:Some-Agent"))
        hecho = next(r for r in doc["@graph"] if r["@type"] == "gm:Fact")
        self.assertEqual(hecho["prov:wasDerivedFrom"], [evento["@id"]])

    def test_schema_layout_signs_in_schema_form(self) -> None:
        art = ap.sign(ap.to_pam(FULL, layout="schema"), self.priv)
        self.assertIn("components", art)
        self.assertTrue(art["signature"].startswith("ed25519:"))
        self.assertTrue(ap.verify(art, self.pub))


if __name__ == "__main__":
    unittest.main()
