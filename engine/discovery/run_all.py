"""Regenerate the machine-readable discovery reports.

Writes:
  generated/device_catalog.json       (model_inspector)
  generated/service_capabilities.json  (service_inspector + api cross-reference)
  generated/api_surface.json           (package_inspector)

Never touches generated/capability_report.json or the reference .pkt files.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.discovery import model_inspector, package_inspector, service_inspector

# resolve project_root/generated regardless of cwd
_GENERATED = Path(__file__).resolve().parents[2] / "generated"


def _service_capabilities(api: dict) -> dict:
    """Join the service structures with the library's API reality.

    For each service, state whether a dedicated builder method exists, or
    whether direct XML manipulation (via the lossless model tree) is required.
    """
    builder_methods = set(
        api["modules"]["pkt_core.builder.lab"]["classes"].get("Lab", {}).get("methods", {})
    )
    structures = service_inspector.extract_structures()

    # builder.Lab has no service authoring methods; map each service to how it
    # must be produced today.
    builder_covers = {
        "ios_config": "add_device(ios_config=[...])",
        "pc_ip": "add_device(pc_ip=(ip,mask,gw))",
        "wireless": "set_wireless(...)",
    }

    matrix = {}
    for name, struct in structures["services"].items():
        matrix[name] = {
            "xml_structure": struct,
            "builder_api_method": None,  # none of DHCP/DNS/HTTP/SMTP/POP3/FTP/AAA
            "requires_direct_xml": True,
            "typed_read_view": _typed_view_for(name),
            "validation": _validation_for(name),
        }
    return {
        "note": (
            "pkt_core.builder.Lab authors topology, power, modules, cabling, IOS "
            "config, end-device IP and wireless. It has NO method for DHCP/DNS/"
            "HTTP/HTTPS/SMTP/POP3/FTP/AAA services; those are authored by editing "
            "the device <ENGINE> XML directly. pkt_core.models + pkt_core.audit "
            "provide typed read views and uniqueness validation for the records."
        ),
        "builder_lab_methods": sorted(builder_methods),
        "builder_covers": builder_covers,
        "library_counted_families": structures["library_counted_families"],
        "services": matrix,
    }


def _typed_view_for(service: str) -> str | None:
    return {
        "dhcp": "pkt_core.models.services.DhcpPool",
        "dns": "pkt_core.models.services.DnsRecord",
        "ftp": "pkt_core.models.services.FtpAccount",
        "aaa": "pkt_core.models.services.AaaUser / AaaClient",
        "http": "pkt_core.models.schema.FileEntry (page bodies)",
    }.get(service)


def _validation_for(service: str) -> str | None:
    return {
        "dhcp": "pkt_core.audit.validate_lab -> duplicate-dhcp-pool/-name/-scope",
        "dns": "pkt_core.audit.validate_lab -> duplicate-dns-record (per server zone)",
        "ftp": "pkt_core.audit.validate_lab -> duplicate-ftp-account",
        "aaa": "pkt_core.audit.validate_lab -> duplicate-aaa-client/-user",
    }.get(service)


def main() -> int:
    _GENERATED.mkdir(parents=True, exist_ok=True)

    catalog = model_inspector.build_catalog()
    (_GENERATED / "device_catalog.json").write_text(
        json.dumps(catalog, indent=2), encoding="utf-8"
    )

    api = package_inspector.build_api_report()
    (_GENERATED / "api_surface.json").write_text(
        json.dumps(api, indent=2), encoding="utf-8"
    )

    caps = _service_capabilities(api)
    (_GENERATED / "service_capabilities.json").write_text(
        json.dumps(caps, indent=2), encoding="utf-8"
    )

    print(f"device_catalog.json       : {catalog['model_count']} models, "
          f"{catalog['module_count']} modules, {len(catalog['groups'])} groups")
    print(f"service_capabilities.json : {len(caps['services'])} services")
    print(f"api_surface.json          : {len(api['modules'])} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
