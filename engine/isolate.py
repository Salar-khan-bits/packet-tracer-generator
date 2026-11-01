#!/usr/bin/env python3
"""Three files, one variable each, to find exactly what PT rejects.

Output (directly in generated/, obvious names):
  A_builder_only.pkt   switch + 2 PCs + server, static IPs, NO service edits
  B_plus_email.pkt     A + email server (SMTP/POP3 + accounts) on the server
  C_plus_clientmail.pkt A + mail client pre-filled on the PCs

Open all three. Expected outcomes:
  * A fails  -> the pkt_core builder/codec itself is rejected by this PT build.
  * A opens, B fails -> the EMAIL_SERVER/USERS authoring is the culprit.
  * A opens, C fails -> the EMAIL_CLIENT authoring is the culprit.
  * all open -> the break is elsewhere (report back and we narrow further).
"""

from __future__ import annotations

from pathlib import Path

from pkt_core.builder.lab import Lab
from engine.emit import services as svc
from engine.emit import clients as cli

OUT = Path(__file__).resolve().parents[1] / "generated"
MASK = "255.255.255.0"


def _base():
    lab = Lab(); lab.prune_seed_devices()
    sw = lab.add_device("2960-24TT", "Switch0", x=430, y=250)
    server = lab.add_device("Server-PT", "Server0", x=430, y=110, pc_ip=["192.168.1.10", MASK, "0.0.0.0"])
    pcs = []
    for i in range(2):
        pc = lab.add_device("PC-PT", "PC%d" % i, x=250 + i * 200, y=420,
                            pc_ip=["192.168.1.%d" % (11 + i), MASK, "0.0.0.0"])
        lab.link(pc, "FastEthernet0", sw, "FastEthernet0/%d" % (i + 1), kind="copper")
        pcs.append(pc)
    lab.link(server, "FastEthernet0", sw, "FastEthernet0/3", kind="copper")
    return lab, server, pcs


def build_A():
    lab, server, pcs = _base()
    lab.save(str(OUT / "A_builder_only.pkt"))


def build_B():
    lab, server, pcs = _base()
    svc.author_email(lab, server, domain="mail.com", accounts=[("pc0", "pc0"), ("pc1", "pc1")])
    lab.save(str(OUT / "B_plus_email.pkt"))


def build_C():
    lab, server, pcs = _base()
    for i, pc in enumerate(pcs):
        cli.client_email(lab, pc, display_name="PC%d" % i, mail_id="pc%d@mail.com" % i,
                         server_ip="192.168.1.10", user="pc%d" % i, password="pc%d" % i)
    lab.save(str(OUT / "C_plus_clientmail.pkt"))


if __name__ == "__main__":
    build_A(); build_B(); build_C()
    for n in ("A_builder_only", "B_plus_email", "C_plus_clientmail"):
        print("built:", OUT / (n + ".pkt"))
