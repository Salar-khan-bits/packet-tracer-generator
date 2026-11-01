#!/usr/bin/env python3
"""Build the Lab 05 practice tasks as five separate Packet Tracer projects.

Produces:  generated/lab_05/task1.pkt ... task5.pkt

Each task is a client-server SMTP lab per the Lab 05 brief; some add DNS, DHCP
and a router as the task requires. Device counts and services match the brief;
topology labels ("mesh"/"ring") are realised as described below because a single
switch/hub is physically a star — see the notes printed per task.

The files carry the built, configured networks. Sending the test emails and
running the PDU/ping checks are done by you in Packet Tracer.
"""

from __future__ import annotations

from pathlib import Path

from pkt_core.builder.lab import Lab

from engine.emit import services as svc
from engine.emit import clients as cli
from validators.check import check_pkt

MASK = "255.255.255.0"
DOMAIN = "mail.com"                   # matches the Lab 05 walkthrough
OUT = Path(__file__).resolve().parent / "generated" / "lab_05"


def _server_smtp(lab, *, ip, accounts, dns_records=None, dhcp=None):
    """Add a Server-PT with SMTP(+POP3), optionally DNS and DHCP. Returns dev id."""
    server = lab.add_device("Server-PT", "Server0", x=430, y=110,
                            pc_ip=[ip, MASK, "0.0.0.0"])
    cli.client_static(lab, server, ip=ip, mask=MASK, dns=ip if dns_records else "")
    svc.clean_services(lab, server)
    svc.author_email(lab, server, domain=DOMAIN, accounts=accounts)
    if dns_records:
        svc.author_dns(lab, server, dns_records)
    if dhcp:
        svc.author_dhcp(lab, server, **dhcp)
    return server


def _add_client(lab, name, model, x, y, *, user, server_ip, static=None):
    """Add a PC/laptop, set addressing (static tuple or DHCP) and mail client."""
    if static:
        dev = lab.add_device(model, name, x=x, y=y, pc_ip=[static, MASK, "0.0.0.0"])
    else:
        dev = lab.add_device(model, name, x=x, y=y)
        cli.client_dhcp(lab, dev)
    cli.client_email(lab, dev, display_name=name, mail_id="%s@%s" % (user, DOMAIN),
                     server_ip=server_ip, user=user, password=user)
    return dev


def _row(n, x0=90, dx=120, y=430):
    return [(x0 + i * dx, y) for i in range(n)]


# --------------------------------------------------------------------------- #
def task1() -> Path:
    """5 PCs + switch + SMTP server, static addressing (single-switch star)."""
    lab = Lab(); lab.prune_seed_devices()
    sw = lab.add_device("2960-24TT", "Switch0", x=430, y=250)
    users = ["pc%d" % (i + 1) for i in range(5)]
    server = _server_smtp(lab, ip="192.168.1.10", accounts=[(u, u) for u in users])
    lab.link(server, "FastEthernet0", sw, "FastEthernet0/6", kind="copper")
    for i, ((x, y), u) in enumerate(zip(_row(5), users)):
        dev = _add_client(lab, "PC%d" % i, "PC-PT", x, y, user=u,
                          server_ip="192.168.1.10", static="192.168.1.%d" % (11 + i))
        lab.link(dev, "FastEthernet0", sw, "FastEthernet0/%d" % (i + 1), kind="copper")
    return _save(lab, "task1")


def task2() -> Path:
    """8 PCs + switch + SMTP server, static addressing."""
    lab = Lab(); lab.prune_seed_devices()
    sw = lab.add_device("2960-24TT", "Switch0", x=490, y=250)
    users = ["pc%d" % (i + 1) for i in range(8)]
    server = _server_smtp(lab, ip="192.168.1.10", accounts=[(u, u) for u in users])
    lab.link(server, "FastEthernet0", sw, "FastEthernet0/9", kind="copper")
    for i, ((x, y), u) in enumerate(zip(_row(8, x0=70, dx=110), users)):
        dev = _add_client(lab, "PC%d" % i, "PC-PT", x, y, user=u,
                          server_ip="192.168.1.10", static="192.168.1.%d" % (11 + i))
        lab.link(dev, "FastEthernet0", sw, "FastEthernet0/%d" % (i + 1), kind="copper")
    return _save(lab, "task2")


def task3() -> Path:
    """9 PCs on 3 hubs (3 each), hubs in a ring, SMTP + DHCP (dynamic)."""
    lab = Lab(); lab.prune_seed_devices()
    users = ["pc%d" % (i + 1) for i in range(9)]
    server = _server_smtp(lab, ip="192.168.1.1", accounts=[(u, u) for u in users],
                          dhcp=dict(pool_name="lab3Pool", network="192.168.1.0", mask=MASK,
                                    start_ip="192.168.1.100", end_ip="192.168.1.200",
                                    dns_server="0.0.0.0", default_router="0.0.0.0", max_users=100))
    hubs = [lab.add_device("Hub-PT", "Hub%d" % h, x=200 + h * 240, y=250) for h in range(3)]
    # 3 PCs per hub on Fa0..Fa2
    k = 0
    for h, hub in enumerate(hubs):
        for p in range(3):
            x, y = 150 + h * 240 + p * 70, 430
            dev = _add_client(lab, "PC%d" % k, "PC-PT", x, y, user=users[k],
                              server_ip="192.168.1.1")
            lab.link(dev, "FastEthernet0", hub, "FastEthernet%d" % p, kind="copper")
            k += 1
    # ring of hubs: Hub0-Hub1-Hub2-Hub0 (L1 loop; see note)
    lab.link(hubs[0], "FastEthernet3", hubs[1], "FastEthernet3", kind="copper")
    lab.link(hubs[1], "FastEthernet4", hubs[2], "FastEthernet3", kind="copper")
    lab.link(hubs[2], "FastEthernet4", hubs[0], "FastEthernet4", kind="copper")
    # server on Hub0 Fa5
    lab.link(server, "FastEthernet0", hubs[0], "FastEthernet5", kind="copper")
    return _save(lab, "task3")


def task4() -> Path:
    """4 PCs + 1 hub + SMTP + DNS + DHCP (dynamic). Star around the hub."""
    lab = Lab(); lab.prune_seed_devices()
    users = ["pc%d" % (i + 1) for i in range(4)]
    server = _server_smtp(
        lab, ip="192.168.1.1", accounts=[(u, u) for u in users],
        dns_records=[("mail.com", "192.168.1.1")],
        dhcp=dict(pool_name="lab4Pool", network="192.168.1.0", mask=MASK,
                  start_ip="192.168.1.100", end_ip="192.168.1.200",
                  dns_server="192.168.1.1", default_router="0.0.0.0", max_users=100))
    hub = lab.add_device("Hub-PT", "Hub0", x=430, y=250)
    lab.link(server, "FastEthernet0", hub, "FastEthernet4", kind="copper")
    for i, ((x, y), u) in enumerate(zip(_row(4, x0=170, dx=140), users)):
        dev = _add_client(lab, "PC%d" % i, "PC-PT", x, y, user=u, server_ip="192.168.1.1")
        lab.link(dev, "FastEthernet0", hub, "FastEthernet%d" % i, kind="copper")
    return _save(lab, "task4")


def task5() -> Path:
    """3 PCs + 2 laptops + switch + SMTP + DHCP + router (ping the router)."""
    lab = Lab(); lab.prune_seed_devices()
    users = ["pc1", "pc2", "pc3", "lap1", "lap2"]
    server = _server_smtp(
        lab, ip="192.168.1.10", accounts=[(u, u) for u in users],
        dhcp=dict(pool_name="lab5Pool", network="192.168.1.0", mask=MASK,
                  start_ip="192.168.1.100", end_ip="192.168.1.200",
                  dns_server="0.0.0.0", default_router="192.168.1.1", max_users=100))
    sw = lab.add_device("2960-24TT", "Switch0", x=430, y=250)
    router = lab.add_device("2911", "Router0", x=430, y=110, ios_config=[
        "enable", "configure terminal", "hostname Router0",
        "interface GigabitEthernet0/0", "ip address 192.168.1.1 255.255.255.0",
        "no shutdown", "exit", "end",
    ])
    lab.link(router, "GigabitEthernet0/0", sw, "GigabitEthernet0/1", kind="copper")
    lab.link(server, "FastEthernet0", sw, "FastEthernet0/7", kind="copper")
    devs = [("PC0", "PC-PT"), ("PC1", "PC-PT"), ("PC2", "PC-PT"),
            ("Laptop0", "Laptop-PT"), ("Laptop1", "Laptop-PT")]
    for i, ((x, y), (name, model)) in enumerate(zip(_row(5), devs)):
        dev = _add_client(lab, name, model, x, y, user=users[i], server_ip="192.168.1.10")
        lab.link(dev, "FastEthernet0", sw, "FastEthernet0/%d" % (i + 1), kind="copper")
    return _save(lab, "task5")


def _save(lab, stem: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / ("%s.pkt" % stem)
    lab.save(str(out))
    return out


def main() -> int:
    for fn in (task1, task2, task3, task4, task5):
        out = fn()
        rep = check_pkt(str(out))
        print("%-6s -> %s  %s" % (
            out.stem, out.name,
            {k: rep[k] for k in ("devices", "links", "dhcp_pools", "dns_records", "validate_ok")}))
    print("\nNote: task3 builds a literal hub RING (an L1 loop). To run PDUs without a")
    print("broadcast storm, temporarily remove one hub-to-hub cable in Packet Tracer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
