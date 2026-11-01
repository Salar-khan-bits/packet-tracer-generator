#!/usr/bin/env python3
"""One-command sanity check — run this after setup on any machine.

Builds the bundled example spec to a temporary file and confirms it is a valid,
re-openable Packet Tracer container. If this prints PASS, your environment is
ready to generate labs.

    python verify.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def main() -> int:
    try:
        import pkt_core  # noqa: F401
    except ImportError:
        print("FAIL: pkt_core not installed. Run:  pip install -r requirements.txt")
        return 1

    import json
    from genlab import build
    from validators.check import check_pkt

    spec_path = Path(__file__).resolve().parent / "specifications" / "example_showcase.json"
    if not spec_path.exists():
        print(f"FAIL: missing {spec_path}")
        return 1

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    lab, name = build(spec, pt_version=None)

    out = Path(tempfile.gettempdir()) / "pkt_verify_example.pkt"
    lab.save(str(out))
    report = check_pkt(str(out))

    ok = report["validate_ok"] and report["devices"] == 8 and report["dhcp_pools"] == 1
    print("built example spec ->", out)
    print("  devices=%(devices)s links=%(links)s dhcp_pools=%(dhcp_pools)s "
          "dns_records=%(dns_records)s validate_ok=%(validate_ok)s" % report)
    print("PASS: environment is ready." if ok else "FAIL: output did not validate as expected.")
    try:
        out.unlink()
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
