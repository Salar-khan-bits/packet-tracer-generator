"""Public-API surface extractor for ``pkt_core``.

Walks the two subsystems a generator actually calls — the authoring builder
(``pkt_core.builder.lab``) and the lossless read/modify models
(``pkt_core.models``) plus the container codec — and records every public class,
its methods and their signatures, with source locations. Pure introspection; no
state is changed.
"""

from __future__ import annotations

import importlib
import inspect
from typing import Any

# Modules whose public surface a generator reasonably depends on.
TARGET_MODULES: tuple[str, ...] = (
    "pkt_core",
    "pkt_core.builder.lab",
    "pkt_core.codec.container",
    "pkt_core.codec.qcompress",
    "pkt_core.crypto.keys",
    "pkt_core.resources",
    "pkt_core.models.lab",
    "pkt_core.models.network",
    "pkt_core.models.schema",
    "pkt_core.models.services",
    "pkt_core.xml.nodes",
    "pkt_core.xml.writer",
    "pkt_core.audit",
    "pkt_core.export",
    "pkt_core.diff",
)


def _sig(obj: Any) -> str:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return "(...)"


def _where(obj: Any) -> str:
    try:
        src = inspect.getsourcefile(obj) or ""
        line = inspect.getsourcelines(obj)[1]
        tail = src.split("site-packages")[-1].lstrip("/\\")
        return f"{tail}:{line}"
    except (TypeError, OSError):
        return ""


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def inspect_module(modname: str) -> dict[str, Any]:
    mod = importlib.import_module(modname)
    exported = getattr(mod, "__all__", None)
    classes: dict[str, Any] = {}
    functions: dict[str, Any] = {}

    members = exported if exported else [n for n in dir(mod) if _is_public(n)]
    for name in members:
        obj = getattr(mod, name, None)
        if obj is None:
            continue
        # keep only objects actually defined in this module (avoid re-exports)
        obj_mod = getattr(obj, "__module__", None)
        if inspect.isclass(obj):
            if obj_mod and obj_mod != modname and modname != "pkt_core":
                continue
            methods = {}
            for mname, m in inspect.getmembers(obj, predicate=lambda x: inspect.isfunction(x) or isinstance(x, property)):
                if not _is_public(mname):
                    continue
                if isinstance(m, property):
                    methods[mname] = {"kind": "property"}
                else:
                    methods[mname] = {"kind": "method", "signature": _sig(m)}
            classes[name] = {
                "where": _where(obj),
                "doc": (inspect.getdoc(obj) or "").split("\n")[0],
                "methods": methods,
            }
        elif inspect.isfunction(obj):
            if obj_mod and obj_mod != modname and modname != "pkt_core":
                continue
            functions[name] = {
                "signature": _sig(obj),
                "where": _where(obj),
                "doc": (inspect.getdoc(obj) or "").split("\n")[0],
            }
    return {"classes": classes, "functions": functions, "exports": list(members)}


def build_api_report() -> dict[str, Any]:
    import pkt_core

    out: dict[str, Any] = {"version": getattr(pkt_core, "__version__", "?"), "modules": {}}
    for modname in TARGET_MODULES:
        try:
            out["modules"][modname] = inspect_module(modname)
        except Exception as exc:  # pragma: no cover
            out["modules"][modname] = {"error": str(exc)}
    return out


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(build_api_report(), indent=2)[:4000])
