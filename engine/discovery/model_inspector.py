"""Device-template catalog extractor.

Reads the template library bundled in ``pkt_core`` (via the public
``load_device_templates`` loader) and, for every model, extracts the facts a
generator needs: the Packet Tracer ``kind``, the icon/layout class, the flat
port inventory (type + name where present), the installable module bays, and
which service blocks the template already carries.

Everything is derived from the actual ``<DEVICE>`` bytes; nothing is invented.
Attributes that cannot be determined are recorded as ``null`` rather than
guessed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pkt_core.builder.lab import kind_for_model
from pkt_core.resources import load_device_templates

# Service container tags that mark a device as capable of that service,
# keyed by the canonical service name used across the discovery reports.
SERVICE_MARKERS: dict[str, str] = {
    "dhcp": "DHCP_SERVERS",
    "dhcp_homerouter": "DHCP_SERVER",
    "dns": "DNS_SERVER",
    "http": "HTTP_SERVER",
    "https": "HTTPS_SERVER",
    "email": "EMAIL_SERVER",
    "ftp": "FTP_SERVER",
    "tftp": "TFTP_SERVER",
    "ntp": "NTP_SERVER",
    "syslog": "SYSLOG_SERVER",
    "aaa": "ACS_SERVER",
}

# Map a Packet Tracer engine <TYPE> / icon class onto a human group.
GROUP_BY_KIND: dict[str, str] = {
    "router": "routers",
    "switch": "switches",
    "multilayer-switch": "layer3_switches",
    "access-point": "wireless",
    "pc": "pcs",
    "laptop": "laptops",
    "server": "servers",
    "firewall": "firewalls",
    "iot": "iot",
    "sniffer": "analysis",
    "pdd": "power",
    "default": "other",
}


def _engine(dev: ET.Element) -> ET.Element | None:
    return dev.find("ENGINE")


def _ports(engine: ET.Element) -> list[dict[str, str]]:
    """Flat list of every PORT under the engine, with its TYPE and name."""
    out: list[dict[str, str]] = []
    for port in engine.iter("PORT"):
        ptype = port.findtext("TYPE") or ""
        # A PT PORT carries its name under <NAME> only in some schemas; the
        # reliable discriminator is TYPE. Record both when present.
        name = port.findtext("NAME") or ""
        out.append({"type": ptype.strip(), "name": name.strip()})
    return out


def _module_bays(engine: ET.Element) -> list[dict[str, Any]]:
    """Every SLOT bay, its TYPE, whether it is filled, and the module model."""
    out: list[dict[str, Any]] = []
    for slot in engine.iter("SLOT"):
        stype = (slot.findtext("TYPE") or "").strip()
        mod = slot.find("MODULE")
        out.append(
            {
                "bay_type": stype,
                "filled": mod is not None,
                "module_model": (mod.findtext("MODEL") or "").strip() if mod is not None else None,
            }
        )
    return out


def _services(engine: ET.Element) -> list[str]:
    present: list[str] = []
    for name, tag in SERVICE_MARKERS.items():
        if engine.find(tag) is not None:
            present.append(name)
    return present


def inspect_model(model: str, blob: bytes) -> dict[str, Any]:
    """Return the catalog record for one device model."""
    try:
        dev = ET.fromstring(blob.decode("utf-8", "replace"))
    except ET.ParseError as exc:  # pragma: no cover - templates are well-formed
        return {"model": model, "error": f"parse: {exc}"}

    engine = _engine(dev)
    if engine is None:
        return {"model": model, "error": "no <ENGINE>"}

    type_el = engine.find("TYPE")
    pt_kind = (type_el.text or "").strip() if type_el is not None else ""
    model_attr = (type_el.get("model") or "") if type_el is not None else ""
    icon_kind = kind_for_model(model)
    ports = _ports(engine)
    port_types = sorted({p["type"] for p in ports if p["type"]})
    bays = _module_bays(engine)

    return {
        "model": model,
        "pt_kind": pt_kind,                 # e.g. "Router", "Switch", "Pc", "Server"
        "model_attr": model_attr,           # <TYPE model="..."> value
        "icon_class": icon_kind,            # builder layout class
        "group": GROUP_BY_KIND.get(icon_kind, "other"),
        "port_count": len(ports),
        "port_types": port_types,
        "ports": ports,
        "module_bays": bays,
        "empty_interface_bays": sum(
            1 for b in bays if b["bay_type"] == "eInterfaceCard" and not b["filled"]
        ),
        "services_present": _services(engine),
        "description": (engine.findtext("DESCRIPTION") or "").strip(),
    }


def build_catalog() -> dict[str, Any]:
    """Build the full catalog from the bundled template library."""
    models, modules = load_device_templates()
    records = [inspect_model(name, blob) for name, blob in sorted(models.items())]

    by_group: dict[str, list[str]] = {}
    for rec in records:
        by_group.setdefault(rec.get("group", "other"), []).append(rec["model"])

    return {
        "source": "pkt_core.resources.load_device_templates()",
        "model_count": len(records),
        "module_count": len(modules),
        "groups": {g: sorted(v) for g, v in sorted(by_group.items())},
        "modules": sorted(modules.keys()),
        "models": records,
    }


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(build_catalog(), indent=2)[:4000])
