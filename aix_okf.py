"""
aix_okf.py — Export .aix v0.3 (DRAFT) procedures to an Open Knowledge Format
(OKF v0.2, Google Cloud) bundle.

OKF (github.com/GoogleCloudPlatform/knowledge-catalog, okf/SPEC.md) is a
directory of Markdown concept files with YAML frontmatter (`type` is the
only required key), plus the reserved `index.md` and `log.md`. It describes
shared, organizational knowledge. .aix describes a person's memory, and
the two meet at procedures: a `HowTo` record becomes an OKF `Playbook`.

Mapping (§ numbers refer to OKF v0.2):
  name / description            → title / description (§4.1)
  step[]                        → "# Steps" numbered list (§4.2)
  gm:recordedAt, attributed-to  → generated {by, at} (§5.2)
  attributed to human:<id>      → also verified {by: human:<id>, at} (§5.3)
  gm:status                     → status: active → stable,
                                  superseded/discarded → deprecated,
                                  proposed → draft (§5.4)
  gm:supersededBy               → link to the replacement concept (§6.1)
  prov:wasDerivedFrom           → one `sources` entry, a scope descriptor
                                  ("N episodes of the subject's memory"):
                                  the count travels, episode ids do not (§5.1)
  actors                        → OKF actor convention (§7): human:/process:
                                  kept, agent:<id> → <id>/<producer version>

What never goes out: records marked `gm:sensitivity` personal or
sensitive, and every non-procedure record (facts, entities, episodes). A
document that does not validate is refused.

Standard library only; the YAML is emitted with JSON-quoted scalars, which
are valid YAML.

Usage:
    from aix_okf import to_okf_bundle, write_bundle
    files = to_okf_bundle(aix_document)          # {relative path: text}
    write_bundle(files, "out/okf")
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import aix_v03 as aix

OKF_VERSION = "0.2"
PRODUCER = f"aix_okf/{aix.VERSION}"
ESTADO = {"active": "stable", "superseded": "deprecated", "discarded": "deprecated", "proposed": "draft"}
NO_SALE = {"personal", "sensitive"}


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "procedure"


def _actor(a: str) -> str:
    if a.startswith(("human:", "process:")):
        return a
    return f"{a.split(':', 1)[-1]}/{aix.VERSION}"


def _yaml(v: Any) -> str:
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k}: {_yaml(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(_yaml(x) for x in v) + "]"
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return json.dumps(v)
    return json.dumps(str(v), ensure_ascii=False)


def _frontmatter(campos: dict[str, Any]) -> str:
    lineas = ["---"]
    for k, v in campos.items():
        if k in ("sources", "verified") and isinstance(v, list):
            lineas.append(f"{k}:")
            lineas += [f"  - {_yaml(x)}" for x in v]
        else:
            lineas.append(f"{k}: {_yaml(v)}")
    return "\n".join(lineas + ["---", ""])


def _exportable(r: dict[str, Any]) -> bool:
    tipos = r.get("@type", [])
    tipos = [tipos] if isinstance(tipos, str) else tipos
    return "HowTo" in tipos and r.get("gm:sensitivity") not in NO_SALE


def to_okf_bundle(data: dict[str, Any], directory: str = "procedures", tags: list[str] | None = None) -> dict[str, str]:
    """A dumped .aix v0.3 document → {bundle-relative path: file text}."""
    errores, _ = aix.validate(data)
    if errores:
        raise ValueError(f"invalid .aix v0.3 document, not exported: {errores[:3]}")
    procs = sorted((r for r in data.get("@graph", []) if _exportable(r)), key=lambda r: (str(r.get("name", "")), r["@id"]))
    rutas: dict[str, str] = {}
    usados: set[str] = set()
    for r in procs:
        base = _slug(str(r.get("name") or r["@id"]))
        nombre, n = base, 2
        while nombre in usados:
            nombre, n = f"{base}-{n}", n + 1
        usados.add(nombre)
        rutas[r["@id"]] = f"{directory}/{nombre}.md"

    archivos: dict[str, str] = {}
    indice: list[str] = []
    for r in procs:
        autor, cuando = str(r["prov:wasAttributedTo"]), str(r["gm:recordedAt"])
        campos: dict[str, Any] = {"type": "Playbook", "title": str(r.get("name") or r["@id"])}
        if r.get("description"):
            campos["description"] = str(r["description"])
        campos["tags"] = ["procedure", *(tags or [])]
        campos["status"] = ESTADO.get(str(r.get("gm:status", "active")), "stable")
        campos["generated"] = {"by": _actor(autor), "at": cuando}
        if autor.startswith("human:"):
            campos["verified"] = [{"by": autor, "at": cuando}]
        derivado = r.get("prov:wasDerivedFrom", [])
        n_ep = len([derivado] if isinstance(derivado, str) else derivado)
        if n_ep:
            campos["sources"] = [{"id": "episodes", "resource": f"{n_ep} episodes of the subject's memory (.aix, not exported)",
                                  "author": _actor(autor)}]
        campos["aix_id"] = r["@id"]
        cuerpo = []
        reemplazo = r.get("gm:supersededBy")
        if reemplazo in rutas:
            cuerpo += [f"> Deprecated: replaced by [{_titulo(data, reemplazo)}](/{rutas[reemplazo]}).", ""]
        pasos = sorted(r.get("step", []), key=lambda s: s.get("position", 0))
        if pasos:
            cuerpo += ["# Steps", ""] + [f"{i}. {p.get('text', '')}" for i, p in enumerate(pasos, 1)] + [""]
        if n_ep:
            cuerpo += [f"Derived from {n_ep} recorded episodes.[^episodes]", "", "[^episodes]: Episodes of the subject's memory", ""]
        archivos[rutas[r["@id"]]] = _frontmatter(campos) + "\n" + "\n".join(cuerpo)
        indice.append(f"* [{campos['title']}](/{rutas[r['@id']]}) - {campos.get('description', '')}".rstrip(" -"))

    archivos["index.md"] = (f"---\nokf_version: {_yaml(OKF_VERSION)}\n---\n\n# Procedures\n\n"
                            + ("\n".join(indice) if indice else "_No exportable procedures._") + "\n")
    fecha = str(data.get("gm:recordedAt", ""))[:10]
    archivos["log.md"] = (f"# Directory Update Log\n\n## {fecha}\n"
                          f"* **Creation**: Exported {len(procs)} procedures from an .aix v0.3 document ({PRODUCER}).\n")
    return archivos


def _titulo(data: dict[str, Any], rid: str) -> str:
    return next((str(r.get("name") or rid) for r in data.get("@graph", []) if r["@id"] == rid), rid)


def parse_frontmatter(texto: str) -> dict[str, Any]:
    """Minimal reader for the frontmatter this module writes (for tests and
    consumers without a YAML library)."""
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    if not m:
        raise ValueError("no frontmatter")
    out: dict[str, Any] = {}
    clave = None
    for linea in m.group(1).splitlines():
        if linea.startswith("  - ") and clave:
            out.setdefault(clave, []).append(_leer(linea[4:]))
        else:
            clave, _, valor = linea.partition(": ") if ": " in linea else (linea.rstrip(":"), "", "")
            if valor:
                out[clave] = _leer(valor)
    return out


def _leer(v: str) -> Any:
    v = v.strip()
    if v.startswith("{ ") and v.endswith(" }"):
        partes = re.findall(r'(\w+): ("(?:[^"\\]|\\.)*"|[^,]+)', v[2:-2])
        return {k: json.loads(x) for k, x in partes}
    return json.loads(v)


def write_bundle(archivos: dict[str, str], destino: str | Path) -> list[Path]:
    raiz = Path(destino)
    escritos = []
    for ruta, texto in archivos.items():
        p = raiz / ruta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")
        escritos.append(p)
    return escritos
