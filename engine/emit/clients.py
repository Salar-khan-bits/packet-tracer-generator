"""End-device (PC / laptop) configuration authors.

The builder's ``add_device(pc_ip=...)`` covers a static NIC; these add what it
does not: switching a client to DHCP, setting the DNS client, and pre-filling
the built-in mail client so the student only has to press Send/Receive.

All fields verified against the PC-PT template engine.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from engine.emit.services import engine_of, _set


def _first_port(lab, dev_id: str) -> ET.Element:
    port = lab._els[dev_id].find(".//PORT")
    if port is None:  # pragma: no cover
        raise ValueError(f"{dev_id}: device has no <PORT>")
    return port


def client_static(
    lab,
    dev_id: str,
    *,
    ip: str,
    mask: str,
    gateway: str = "0.0.0.0",
    dns: str = "",
) -> None:
    """Static NIC addressing plus DNS client (idempotent with builder pc_ip)."""
    port = _first_port(lab, dev_id)
    _set(port, "IP", ip)
    _set(port, "SUBNET", mask)
    _set(port, "PORT_GATEWAY", gateway)
    _set(port, "PORT_DNS", dns)
    _set(port, "PORT_DHCP_ENABLE", "false")
    eng = engine_of(lab, dev_id)
    _set(eng, "GATEWAY", gateway)
    dc = eng.find("DNS_CLIENT") or ET.SubElement(eng, "DNS_CLIENT")
    _set(dc, "SERVER_IP", dns)


def client_dhcp(lab, dev_id: str) -> None:
    """Switch the NIC to DHCP; PT performs DORA on load.

    IP/mask/gateway/DNS are cleared so nothing stale shadows the lease; the DNS
    server is delivered by the DHCP pool's ``DNS_SERVER`` option.
    """
    port = _first_port(lab, dev_id)
    _set(port, "PORT_DHCP_ENABLE", "true")
    _set(port, "IP", "0.0.0.0")
    _set(port, "SUBNET", "0.0.0.0")
    _set(port, "PORT_GATEWAY", "")
    _set(port, "PORT_DNS", "")
    eng = engine_of(lab, dev_id)
    _set(eng, "GATEWAY", "0.0.0.0")


def client_email(
    lab,
    dev_id: str,
    *,
    display_name: str,
    mail_id: str,
    server_ip: str,
    user: str,
    password: str,
) -> bool:
    """Pre-fill the built-in mail client (Desktop → Email → Configure Mail).

    `server_ip` is used for both incoming (POP3) and outgoing (SMTP) servers so
    it works regardless of DNS; `mail_id` is the full ``user@domain`` address.
    Returns True if filled, False if the device has no EMAIL_CLIENT (e.g. laptop).
    """
    eng = engine_of(lab, dev_id)
    em = eng.find("EMAIL_CLIENT")
    if em is None:
        # Some end devices (e.g. Laptop-PT) ship no EMAIL_CLIENT block. Packet
        # Tracer rejects a file with an invented one ("not compatible with this
        # version"), so we do NOT create it — the student fills the mail client
        # on that device by hand (Desktop -> Email). Returns silently.
        return False
    _set(em, "ENABLED", "1")
    _set(em, "NAME", display_name)
    _set(em, "MAIL_ID", mail_id)
    _set(em, "POP3_SERVER", server_ip)
    _set(em, "SMTP_SERVER", server_ip)
    _set(em, "USER", user)
    _set(em, "PASSWORD", password)
    return True
