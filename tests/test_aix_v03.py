"""Tests for the .aix v0.3 draft reference implementation (aix_v03.py)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import aix_v03 as a  # noqa: E402

T = "2026-09-24T10:00:00+00:00"
EJEMPLOS = RAIZ / "examples" / "v0.3"


class TestExamples(unittest.TestCase):
    def test_examples_validate_and_round_trip(self) -> None:
        for f in sorted(EJEMPLOS.glob("*.aix.jsonld")):
            data = json.loads(f.read_text())
            errores, _ = a.validate(data)
            self.assertEqual(errores, [], f.name)
            self.assertEqual(a.dump(a.load(data), integrity="gm:integrity" in data), data, f.name)

    def test_examples_match_json_schema(self) -> None:
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((RAIZ / "schema" / "aix-v0.3.schema.json").read_text())
        for f in sorted(EJEMPLOS.glob("*.aix.jsonld")):
            jsonschema.validate(json.loads(f.read_text()), schema)

    def test_full_example_integrity_detects_tampering(self) -> None:
        data = json.loads((EJEMPLOS / "full.aix.jsonld").read_text())
        self.assertTrue(a.verify(data))
        data["@graph"][0]["name"] = "tampered"
        self.assertFalse(a.verify(data))
        self.assertIn("gm:integrity does not match the records", a.validate(data)[0])


class TestRules(unittest.TestCase):
    def _doc(self, **props: object) -> dict:
        d = a.Document(subject="gm:subject/x", recorded_at=T)
        d.add(a.Record("gm:fact/1", "gm:Fact", T, "human:x", dict(props)))
        return a.dump(d)

    def test_datetime_without_offset_is_rejected_and_honest_dates_accepted(self) -> None:
        self.assertTrue(any("offset" in e for e in a.validate(self._doc(startDate="2017-03-01T09:00"))[0]))
        for ok in ("2017", "2017-03", "2017-03-14", "2017-03-14T09:00:00+01:00"):
            self.assertEqual(a.validate(self._doc(startDate=ok))[0], [], ok)

    def test_partial_records_are_tolerated_with_a_warning(self) -> None:
        errores, avisos = a.validate(self._doc())
        self.assertEqual(errores, [])
        self.assertTrue(any("partial gm:Fact" in w for w in avisos))

    def test_required_provenance_and_recorded_time(self) -> None:
        data = self._doc()
        del data["@graph"][0]["prov:wasAttributedTo"]
        self.assertIn("@graph[0]: missing required prov:wasAttributedTo", a.validate(data)[0])

    def test_sensitive_never_travels_and_superseded_needs_replacement(self) -> None:
        self.assertTrue(any("sensitive" in e for e in a.validate(self._doc(**{"gm:sensitivity": "sensitive"}))[0]))
        self.assertTrue(any("supersededBy" in e for e in a.validate(self._doc(**{"gm:status": "superseded"}))[0]))

    def test_undeclared_gm_terms_are_flagged_for_governance(self) -> None:
        _, avisos = a.validate(self._doc(**{"gm:inventedTerm": 1}))
        self.assertTrue(any("undeclared gm: term gm:inventedTerm" in w for w in avisos))

    def test_from_v02_keeps_every_memory(self) -> None:
        v02 = json.loads((RAIZ / "examples" / "full.aix").read_text())
        doc = a.dump(a.from_v02(v02))
        self.assertEqual(a.validate(doc)[0], [])
        self.assertEqual(len(doc["@graph"]), len(v02["memories"]))
        self.assertTrue(all(r["@type"] == "InstantaneousEvent" for r in doc["@graph"]))


try:
    from hypothesis import HealthCheck, given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    given = None

if given is not None:
    _ids = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=8)
    _hoja = st.none() | st.booleans() | st.integers(-10**6, 10**6) | st.text(alphabet="abcñé€ 0123", max_size=10)
    _json = st.recursive(
        _hoja,
        lambda hijos: st.lists(hijos, max_size=2) | st.dictionaries(st.sampled_from(["a", "b", "gm:c", "@id"]), hijos, max_size=2),
        max_leaves=4)
    _record = st.builds(
        lambda i, tipo, props: a.Record(f"gm:x/{i}", tipo, T, "process:gen", props),
        _ids, st.sampled_from(["gm:Fact", "Person", "InstantaneousEvent", ["CreateAction", "gm:PublishAction"]]),
        st.dictionaries(st.sampled_from(["name", "gm:note", "data", "gm:confidence"]), _json, max_size=3))

    class TestRoundTrip(unittest.TestCase):
        @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
        @given(st.lists(_record, max_size=6, unique_by=lambda r: r.id), st.booleans())
        def test_dump_load_is_lossless(self, records: list, integrity: bool) -> None:
            doc = a.Document(subject="gm:subject/gen", recorded_at=T, records=records)
            data = a.dump(doc, integrity=integrity)
            self.assertEqual(a.dump(a.load(data), integrity=integrity), data)
            self.assertEqual(json.loads(json.dumps(data)), data)  # plain JSON, nothing lost in transit
            if integrity:
                self.assertTrue(a.verify(data))


if __name__ == "__main__":
    unittest.main()
