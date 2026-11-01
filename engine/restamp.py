#!/usr/bin/env python3
"""Re-stamp the <VERSION> of existing .pkt files to match the local PT build.

Packet Tracer refuses to open a file whose <VERSION> is newer than itself
("not compatible with this version"). The library seed is stamped 9.0.1.0858,
so on an older PT every generated file is rejected. This rewrites the version in
place (container is decoded and re-encoded; nothing else changes).

Usage:
    python -m engine.restamp 8.2.2.0400 generated/lab_05/*.pkt generated/assignment_cisco/*.pkt
    python -m engine.restamp 8.2.2.0400            # defaults to all generated .pkt
"""

from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

from pkt_core import decode, encode_bytes

_VERSION_RE = re.compile(rb"<VERSION>[^<]*</VERSION>")
_ROOT = Path(__file__).resolve().parents[1] / "generated"


def restamp(path: str, version: str) -> tuple[str, str]:
    """Rewrite one file's <VERSION>; returns (old, new)."""
    container = decode(path)
    xml = container.xml
    old = _VERSION_RE.search(xml)
    old_ver = old.group(0).decode("utf-8", "replace") if old else "<none>"
    new_xml = _VERSION_RE.sub(("<VERSION>%s</VERSION>" % version).encode("utf-8"), xml, count=1)
    Path(path).write_bytes(encode_bytes(new_xml, container.format_name))
    # verify it still round-trips
    assert decode(path).xml == new_xml, "round-trip failed after restamp"
    return old_ver, "<VERSION>%s</VERSION>" % version


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m engine.restamp <VERSION> [files...]", file=sys.stderr)
        return 2
    version = argv[0]
    targets = argv[1:]
    files: list[str] = []
    if targets:
        for t in targets:
            files.extend(glob.glob(t))
    else:
        files = [str(p) for p in _ROOT.rglob("*.pkt")]
    if not files:
        print("no .pkt files matched", file=sys.stderr)
        return 1
    for f in files:
        old, new = restamp(f, version)
        print("%-52s %s -> %s" % (f, old, new))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
