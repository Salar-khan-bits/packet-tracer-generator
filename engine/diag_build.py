#!/usr/bin/env python3
"""Isolation diagnostics: find which direct-XML edit makes PT reject the file.

Base = the known-good first_network pattern (switch + static server + static PC).
Each diagnostic adds exactly ONE edit on top of the base, so whichever file PT
refuses names the culprit. Files -> generated/_diag/.
"""

from __future__ import annotations

from pathlib import Path

from pkt_core.builder.lab import Lab
from engine.emit import services as svc
from engine.emit import clients as cli

OUT = Path(__file__).resolve().parents[1] / "generated" / "_diag"
IP_SRV, IP_PC, MASK = "192.168.1.10", "192.168.1.11", "255.255.255.0"


def _base():
    """switch + static server + static PC, linked — mirrors first_network."""
    lab = Lab(); lab.prune_seed_devices()
    sw = lab.add_device("2960-24TT", "Switch0", x=430, y=250)
    server = lab.add_device("Server-PT", "Server0", x=430, y=110, pc_ip=[IP_SRV, MASK, "0.0.0.0"])
    pc = lab.add_device("PC-PT", "PC0", x=250, y=420, pc_ip=[IP_PC, MASK, "0.0.0.0"])
    lab.link(server, "FastEthernet0", sw, "FastEthernet0/1", kind="copper")
    lab.link(pc, "FastEthernet0", sw, "FastEthernet0/2", kind="copper")
    return lab, sw, server, pc


def _save(lab, name):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / (name + ".pkt")
    lab.save(str(p))
    return p


def diag_base():
    lab, *_ = _base()
    return _save(lab, "0_base")


def diag_email():
    lab, sw, server, pc = _base()
    svc.author_email(lab, server, domain="mail.com", accounts=[("pc1", "pc1"), ("pc2", "pc2")])
    return _save(lab, "1_email")


def diag_sanitize():
    lab, sw, server, pc = _base()
    svc.clean_services(lab, server)
    return _save(lab, "2_sanitize")


def diag_dhcp():
    lab, sw, server, pc = _base()
    svc.author_dhcp(lab, server, pool_name="p", network="192.168.1.0", mask=MASK,
                    start_ip="192.168.1.100", end_ip="192.168.1.200",
                    dns_server="0.0.0.0", default_router="0.0.0.0", max_users=100)
    return _save(lab, "3_dhcp")


def diag_clientedit():
    lab, sw, server, pc = _base()
    cli.client_email(lab, pc, display_name="PC0", mail_id="pc1@mail.com",
                     server_ip=IP_SRV, user="pc1", password="pc1")
    cli.client_static(lab, pc, ip=IP_PC, mask=MASK, dns=IP_SRV)
    return _save(lab, "4_clientedit")


def main() -> int:
    for fn in (diag_base, diag_email, diag_sanitize, diag_dhcp, diag_clientedit):
        p = fn()
        print("built:", p.name)
    print("\nOpen each in Packet Tracer. 0_base should open (it is the first_network pattern).")
    print("Report which of 1_email / 2_sanitize / 3_dhcp / 4_clientedit FAIL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
