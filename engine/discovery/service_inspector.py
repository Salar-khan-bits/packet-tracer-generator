"""Service XML structure extractor.

Establishes the *exact* XML hierarchy, required/observed fields and default
values of each Packet Tracer service, using three evidence sources, in order of
authority:

1. The field tables in :mod:`pkt_core.models.services` and
   :mod:`pkt_core.audit` — these are the corpus-derived identity/record fields
   the library itself relies on, so they cannot drift from real documents.
2. The ``Server-PT`` template skeleton (service blocks, enabled flags, defaults).
3. A populated donor example mined from a template that ships a configured
   instance (e.g. the home-router DHCP pool), used to confirm record shape.

The result is the backbone of ``generated/service_capabilities.json``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pkt_core.audit import SERVICE_FAMILIES
from pkt_core.models.services import IDENTITY_FIELDS
from pkt_core.resources import load_device_templates

# Field sets the typed views claim, lifted straight from the models so the
# report and the library agree by construction.
from pkt_core.models.services import AaaClient, AaaUser, DhcpPool, DnsRecord, FtpAccount

_VIEW_FIELDS: dict[str, frozenset[str]] = {
    "dhcp_pools": DhcpPool._claimed,
    "dns_records": DnsRecord._claimed,
    "ftp_accounts": FtpAccount._claimed,
    "aaa_users": AaaUser._claimed,
    "aaa_clients": AaaClient._claimed,
}


def _skeleton(engine: ET.Element, tag: str, maxdepth: int = 3) -> dict[str, Any] | None:
    """Return a shallow {tag: default_text | {children}} skeleton for a block."""
    el = engine.find(tag)
    if el is None:
        return None

    def walk(node: ET.Element, depth: int) -> Any:
        children = list(node)
        if not children:
            return (node.text or "").strip()
        if depth >= maxdepth:
            return {"_children": sorted({c.tag for c in children})}
        out: dict[str, Any] = {}
        for c in children:
            # collapse repeated record tags to a single representative
            if c.tag in out:
                continue
            out[c.tag] = walk(c, depth + 1)
        return out

    return {tag: walk(el, 0)}


def extract_structures() -> dict[str, Any]:
    models, _ = load_device_templates()
    server = ET.fromstring(models["Server-PT"].decode("utf-8", "replace")).find("ENGINE")

    # the donor home router carries a fully-populated DHCP pool
    home = None
    for name in ("HomeRouter-PT-AC", "819HGW", "Linksys-WRT300N"):
        if name in models:
            eng = ET.fromstring(models[name].decode("utf-8", "replace")).find("ENGINE")
            if eng is not None and eng.find("DHCP_SERVER") is not None:
                home = eng
                break

    services: dict[str, Any] = {}

    # --- DHCP (server family) -------------------------------------------
    pool_fields = None
    if home is not None:
        pool = home.find("DHCP_SERVER/POOLS/POOL")
        if pool is not None:
            pool_fields = [c.tag for c in list(pool)]
    services["dhcp"] = {
        "server_container_path": "ENGINE/DHCP_SERVERS/ASSOCIATED_PORTS/ASSOCIATED_PORT/DHCP_SERVER/POOLS/POOL",
        "homerouter_container_path": "ENGINE/DHCP_SERVER/POOLS/POOL",
        "enable_flag": "ENGINE/DHCP_SERVERS/.../DHCP_SERVER/ENABLED (1|0)",
        "record_tag": "POOL",
        "identity_fields": list(IDENTITY_FIELDS["dhcp_pools"]),
        "pool_fields_observed": pool_fields,
        "view_fields": sorted(_VIEW_FIELDS["dhcp_pools"]),
        "server_skeleton": _skeleton(server, "DHCP_SERVERS", maxdepth=4),
        "runtime_only": ["DHCP_POOL_LEASES", "DHCP_RESERVATIONS"],
    }

    # --- DNS ------------------------------------------------------------
    services["dns"] = {
        "container_path": "ENGINE/DNS_SERVER/NAMESERVER-DATABASE/RESOURCE-RECORD",
        "enable_flag": "ENGINE/DNS_SERVER/ENABLED (1|0)",
        "record_tag": "RESOURCE-RECORD",
        "identity_fields": list(IDENTITY_FIELDS["dns_records"]),
        "view_fields": sorted(DnsRecord._claimed),
        "server_skeleton": _skeleton(server, "DNS_SERVER", maxdepth=3),
        "note": "A record's zone key is (TYPE, NAME); replication across servers is legitimate.",
    }

    # --- HTTP / HTTPS ---------------------------------------------------
    services["http"] = {
        "enable_block": "ENGINE/HTTP_SERVER (ENABLED, USERNAME, PASSWORD)",
        "https_block": "ENGINE/HTTPS_SERVER",
        "page_store_path": "ENGINE/FILE_MANAGER/FILE/FILES/FILE[NAME='http:']/FILES/FILE",
        "page_fields": ["FILE_NUMBER", "NAME", "DATE_TIME", "PERMISSION", "FILE_CONTENT"],
        "default_pages": _http_pages(server),
        "server_skeleton": _skeleton(server, "HTTP_SERVER", maxdepth=2),
        "note": "Web page bodies live in the simulated 'http:' filesystem, not inside <HTTP_SERVER>.",
    }

    # --- EMAIL (SMTP/POP3) ----------------------------------------------
    services["email"] = {
        "server_block": "ENGINE/EMAIL_SERVER",
        "server_skeleton": _skeleton(server, "EMAIL_SERVER", maxdepth=2),
        "enable_flags": ["SMTP_ENABLED (1|0)", "POP3_ENABLED (1|0)"],
        "domain_field": "SMTP_DOMAIN",
        "user_count_field": "NO_OF_USERS",
        "account_path": "ENGINE/EMAIL_SERVER/USERS/USER (NAME, PASSWORD)",
        "client_block": "ENGINE/EMAIL_CLIENT",
        "note": "Templates ship 0 accounts; USERS/USER records are authored directly.",
    }

    # --- FTP ------------------------------------------------------------
    services["ftp"] = {
        "container_path": "ENGINE/FTP_SERVER/USER_ACCOUNT_MNGR/ACCOUNT",
        "enable_flag": "ENGINE/FTP_SERVER/ENABLED (1|0)",
        "identity_fields": list(IDENTITY_FIELDS["ftp_accounts"]),
        "view_fields": sorted(FtpAccount._claimed),
        "server_skeleton": _skeleton(server, "FTP_SERVER", maxdepth=3),
    }

    # --- AAA (RADIUS/TACACS+) -------------------------------------------
    services["aaa"] = {
        "server_block": "ENGINE/ACS_SERVER",
        "users_path": "ENGINE/ACS_SERVER/USERS/USER",
        "clients_path": "ENGINE/ACS_SERVER/ACS_CLIENTS/CLIENT",
        "user_identity_fields": list(IDENTITY_FIELDS["aaa_users"]),
        "client_identity_fields": list(IDENTITY_FIELDS["aaa_clients"]),
        "server_skeleton": _skeleton(server, "ACS_SERVER", maxdepth=3),
    }

    # --- simple on/off appliances --------------------------------------
    for name, tag in (("tftp", "TFTP_SERVER"), ("ntp", "NTP_SERVER"), ("syslog", "SYSLOG_SERVER")):
        services[name] = {
            "block": f"ENGINE/{tag}",
            "server_skeleton": _skeleton(server, tag, maxdepth=2),
        }

    return {
        "source": "Server-PT template + home-router donor + pkt_core field tables",
        "library_counted_families": [f.name for f in SERVICE_FAMILIES],
        "services": services,
    }


def _http_pages(server: ET.Element) -> list[str]:
    fm = server.find("FILE_MANAGER")
    if fm is None:
        return []
    root = fm.find("FILE")
    if root is None or root.find("FILES") is None:
        return []
    for f in root.find("FILES").findall("FILE"):
        if (f.findtext("NAME") or "") == "http:":
            inner = f.find("FILES")
            if inner is not None:
                return [g.findtext("NAME") or "" for g in inner.findall("FILE")]
    return []


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(extract_structures(), indent=2)[:4000])
