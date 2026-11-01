#!/usr/bin/env python3
"""Build the CNET Assignment-1 "showcase" Packet Tracer project.

Produces ONE .pkt:  generated/assignment_cisco/<ROLL>_Showcase.pkt

Scenario (from CNET Assignment 1): one LAN; 6 student clients incl. >=1 laptop;
a single server providing DHCP, DNS, HTTP and SMTP/POP3 email; room to grow to 8.

Usage:
    python build_assignment1.py [ROLL_NUMBER]

ROLL_NUMBER defaults to the placeholder "ROLLNUMBER" — pass your own to name the
file as the assignment requires (RollNumber_Showcase.pkt).

The file carries the BUILT, CONFIGURED network. Running the PDU tests, viewing
the page, sending/receiving the emails and the Wireshark exercise are done by
you in Packet Tracer / Wireshark — a generator cannot fabricate those proofs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from pkt_core.builder.lab import Lab

from engine.emit import services as svc
from engine.emit import clients as cli
from validators.check import check_pkt

# ---- network plan (single LAN 192.168.10.0/24) ---------------------------
SUBNET = "255.255.255.0"
SERVER_IP = "192.168.10.10"          # static: stays easy to find
DOMAIN = "showcase.test"
POOL = dict(                          # DHCP: excludes the server, room for >8
    pool_name="showcasePool",
    network="192.168.10.0",
    mask=SUBNET,
    start_ip="192.168.10.100",
    end_ip="192.168.10.200",
    dns_server=SERVER_IP,
    default_router="0.0.0.0",         # single LAN, no gateway needed
    max_users=100,
)

# Raw '&' here: ElementTree escapes it once to &amp; on write, which PT renders
# as '&'. (Pre-escaping would double-escape to &amp;amp;.)
PAGE = """<html>
<head><title>AI & Data Science Showcase</title></head>
<body>
<center><h1>AI & Data Science Showcase</h1></center>
<p>Welcome to the shared information page for the student showcase.</p>
<h2>AI Team</h2>
<p>Demonstrating machine-learning project prototypes. Fictional results for the demo.</p>
<h2>Data Science Team</h2>
<p>Presenting data-analysis dashboards and findings. Fictional results for the demo.</p>
<hr>
<p>Server: %s  |  Name: www.%s</p>
</body></html>""" % (SERVER_IP, DOMAIN)

# 6 clients, at least one laptop; three AI + three DS
CLIENTS = [
    # (name, model, account_user)
    ("AI-PC1", "PC-PT", "ai1"),
    ("AI-PC2", "PC-PT", "ai2"),
    ("AI-Laptop", "Laptop-PT", "ai3"),
    ("DS-PC1", "PC-PT", "ds1"),
    ("DS-PC2", "PC-PT", "ds2"),
    ("DS-PC3", "PC-PT", "ds3"),
]


def build(roll: str, out_dir: Path) -> Path:
    lab = Lab()
    lab.prune_seed_devices()

    # --- switch + server ---------------------------------------------------
    switch = lab.add_device("2960-24TT", "Switch0", x=430, y=250)
    server = lab.add_device("Server-PT", "Server0", x=430, y=110,
                            pc_ip=[SERVER_IP, SUBNET, "0.0.0.0"])
    cli.client_static(lab, server, ip=SERVER_IP, mask=SUBNET, dns=SERVER_IP)

    # --- services on the server (direct XML) -------------------------------
    svc.clean_services(lab, server)
    svc.author_dhcp(lab, server, **POOL)
    svc.author_dns(lab, server, [
        ("www.%s" % DOMAIN, SERVER_IP),
        ("mail.%s" % DOMAIN, SERVER_IP),
    ])
    svc.author_http(lab, server, PAGE)
    svc.author_email(lab, server, domain=DOMAIN,
                     accounts=[(u, u) for _, _, u in CLIENTS])

    # --- 6 DHCP clients, each with its mail client pre-filled --------------
    x0, dx, y = 110, 125, 420
    for i, (name, model, user) in enumerate(CLIENTS):
        dev = lab.add_device(model, name, x=x0 + i * dx, y=y)
        cli.client_dhcp(lab, dev)
        cli.client_email(lab, dev,
                         display_name=name,
                         mail_id="%s@%s" % (user, DOMAIN),
                         server_ip=SERVER_IP, user=user, password=user)
        lab.link(dev, "FastEthernet0", switch, "FastEthernet0/%d" % (i + 1), kind="copper")

    # server on the last used switch port
    lab.link(server, "FastEthernet0", switch, "FastEthernet0/7", kind="copper")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s_Showcase.pkt" % roll)
    lab.save(str(out))
    return out


def main() -> int:
    roll = sys.argv[1] if len(sys.argv) > 1 else "ROLLNUMBER"
    out_dir = Path(__file__).resolve().parent / "generated" / "assignment_cisco"
    out = build(roll, out_dir)
    report = check_pkt(str(out))
    print("built  :", out)
    print("checked:", {k: report[k] for k in
                       ("devices", "links", "dhcp_pools", "dns_records", "validate_ok")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
