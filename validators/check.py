"""Post-build validation gate: fail closed before a .pkt is handed over.

Two checks, both from the library's own guarantees:
  1. `pkt_core.audit.validate_lab(...).ok`  — no duplicate/leftover records.
  2. decode round-trip                       — the container re-reads cleanly.
"""

from __future__ import annotations

from pkt_core import decode
from pkt_core.models import Lab as MLab
from pkt_core.audit import validate_lab, inventory


def check_pkt(path: str) -> dict:
    """Validate a generated .pkt; returns a small report dict (raises on hard fail)."""
    container = decode(path)                      # proves the container decodes
    lab = MLab.from_bytes(container.xml)
    report = validate_lab(lab)
    inv = inventory(lab)
    summary = {
        "path": str(path),
        "format": container.format_name,
        "devices": len(lab.devices),
        "links": len(lab.links),
        "dhcp_pools": inv.dhcp_pools.distinct,
        "dns_records": inv.dns_records.distinct,
        "validate_ok": report.ok,
        "failures": [f"{f.code}: {f.message}" for f in report.failures],
    }
    if not report.ok:
        raise AssertionError(f"validation failed for {path}: {summary['failures']}")
    return summary
