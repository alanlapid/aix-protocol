"""Tests for the .aix v0.3 → Open Knowledge Format v0.2 exporter (aix_okf.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import aix_okf as o  # noqa: E402
import aix_v03 as a  # noqa: E402

T = "2026-09-24T10:00:00+00:00"


def _doc() -> dict:
    d = a.Document(subject="gm:subject/x", recorded_at=T)
    pasos = lambda *t: [{"@type": "HowToStep", "position": i, "text": x} for i, x in enumerate(t, 1)]  # noqa: E731
    d.add(a.Record("gm:procedure/1", "HowTo", T, "human:subject",
                   {"name": "Publicar un artefacto técnico", "description": "Código y paper", "step": pasos("GitHub", "Zenodo", "arXiv"),
                    "prov:wasDerivedFrom": ["gm:episode/1", "gm:episode/2"], "gm:status": "superseded",
                    "gm:supersededBy": "gm:procedure/2"}))
    d.add(a.Record("gm:procedure/2", "HowTo", T, "agent:curation", {"name": "Publicar un artefacto técnico", "step": pasos("GitHub")}))
    d.add(a.Record("gm:procedure/3", "HowTo", T, "human:subject", {"name": "Rutina familiar", "gm:sensitivity": "personal"}))
    d.add(a.Record("gm:fact/1", "gm:Fact", T, "human:subject", {"gm:subject": "gm:entity/x", "gm:predicate": "p", "gm:object": "gm:entity/y"}))
    return a.dump(d)


class TestOkf(unittest.TestCase):
    def test_bundle_structure_and_frontmatter(self) -> None:
        b = o.to_okf_bundle(_doc())
        self.assertEqual(sorted(b), ["index.md", "log.md", "procedures/publicar-un-artefacto-tecnico-2.md",
                                     "procedures/publicar-un-artefacto-tecnico.md"])
        viejo = next(t for t in b.values() if '"gm:procedure/1"' in t)
        fm = o.parse_frontmatter(viejo)
        self.assertEqual(fm["type"], "Playbook")
        self.assertEqual(fm["status"], "deprecated")
        self.assertEqual(fm["generated"], {"by": "human:subject", "at": T})
        self.assertEqual(fm["verified"], [{"by": "human:subject", "at": T}])
        self.assertEqual(fm["sources"][0]["resource"], "2 episodes of the subject's memory (.aix, not exported)")
        self.assertIn("1. GitHub\n2. Zenodo\n3. arXiv", viejo)
        self.assertIn("Deprecated: replaced by", viejo)
        nuevo = o.parse_frontmatter(next(t for t in b.values() if '"gm:procedure/2"' in t))
        self.assertEqual((nuevo["status"], nuevo["generated"]["by"]), ("stable", f"curation/{a.VERSION}"))
        self.assertNotIn("verified", nuevo)  # an agent is not a human reviewer (OKF §5.3)
        self.assertTrue(b["index.md"].startswith('---\nokf_version: "0.2"\n---\n'))

    def test_nothing_personal_or_non_procedural_goes_out(self) -> None:
        texto = "\n".join(o.to_okf_bundle(_doc()).values())
        for prohibido in ("Rutina familiar", "gm:fact/1", "gm:episode/1", "gm:entity/y"):
            self.assertNotIn(prohibido, texto)

    def test_frontmatter_is_valid_yaml(self) -> None:
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for ruta, texto in o.to_okf_bundle(_doc()).items():
            if ruta.startswith("procedures/"):
                fm = yaml.safe_load(texto.split("---\n")[1])
                self.assertEqual(fm, json.loads(json.dumps(o.parse_frontmatter(texto))), ruta)

    def test_invalid_document_is_refused_and_bundle_is_written(self) -> None:
        malo = _doc()
        malo["@graph"][0]["gm:sensitivity"] = "sensitive"
        with self.assertRaises(ValueError):
            o.to_okf_bundle(malo)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(len(o.write_bundle(o.to_okf_bundle(_doc()), tmp)), 4)
            self.assertTrue((Path(tmp) / "procedures").is_dir())


if __name__ == "__main__":
    unittest.main()
