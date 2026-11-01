#!/usr/bin/env python3
"""Spec-driven Packet Tracer lab generator.

Describe a lab in a small JSON file and build a fully-configured .pkt — no Python
editing per task. Services (DHCP / DNS / HTTP / SMTP+POP3) are authored with the
real PT formats, so output opens and is ready to use.

    python genlab.py mylab.json                 # -> generated/<name>.pkt
    python genlab.py mylab.json -o out.pkt
    python genlab.py mylab.json --pt-version 8.2.2.0400   # stamp for an older PT

Spec shape (see specifications/example_showcase.json):

{
  "name": "showcase",
  "pt_version": "9.0.1.0858",          # optional; or --pt-version / $PT_VERSION
  "mask": "255.255.255.0",
  "devices": [
    {"name":"Switch0","model":"2960-24TT","x":430,"y":250},
    {"name":"Server0","model":"Server-PT","x":430,"y":110,"ip":"192.168.10.10",
     "connect_to":"Switch0"},
    {"name":"PC1","model":"PC-PT","x":150,"y":420,"dhcp":true,"connect_to":"Switch0",
     "email":{"user":"a","password":"a","mail_id":"a@showcase.test"},
     "ios_config":["..."]}
  ],
  "links": [                            # for links connect_to can't express
    {"a":"Hub0","a_port":"FastEthernet3","b":"Hub1","b_port":"FastEthernet3"}
  ],
  "services": {                         # all optional
    "server":"Server0",
    "dhcp":{"pool_name":"p","network":"192.168.10.0","start":"192.168.10.100",
            "end":"192.168.10.200","dns":"192.168.10.10","gateway":"0.0.0.0"},
    "dns":[["www.showcase.test","192.168.10.10"]],
    "email":{"domain":"showcase.test","accounts":[["a","a"],["b","b"]]},
    "http":"<html>...</html>"
  }
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from pkt_core.builder.lab import Lab

from engine.emit import services as svc
from engine.emit import clients as cli
from validators.check import check_pkt

_ROOT = Path(__file__).resolve().parent


# --- port naming per model family (matches the verified conventions) -------
def _is_ios_switch(model: str) -> bool:
    return bool(re.match(r"^(2960|2950|2900|3560|3650|3550|IE-)", model))


def _is_generic_l2(model: str) -> bool:
    return model in ("Switch-PT", "Hub-PT")


def _is_router(model: str) -> bool:
    return bool(re.match(r"^(29\d\d|19\d\d|18\d\d|28\d\d|26\d\d|ISR|IR\d|CGR|8[12]\d|Router-PT)", model))


def _target_port(model: str, n: int) -> str:
    """The n-th access port on a switch/hub (0-based)."""
    if _is_ios_switch(model):
        return "FastEthernet0/%d" % (n + 1)
    if _is_generic_l2(model):
        return "FastEthernet%d" % n
    # fallback (router/other acting as target)
    return "GigabitEthernet0/%d" % n


def _source_port(model: str, n: int) -> str:
    """The port a connecting device uses toward a switch/hub."""
    if _is_router(model):
        return "GigabitEthernet0/%d" % n
    if _is_ios_switch(model) or _is_generic_l2(model):
        return _target_port(model, n)
    return "FastEthernet0"            # PC / laptop / server NIC


def build(spec: dict, pt_version: str | None) -> tuple[Lab, str]:
    mask = spec.get("mask", "255.255.255.0")
    lab = Lab()
    lab.prune_seed_devices()

    ids: dict[str, str] = {}          # device name -> builder id
    models: dict[str, str] = {}       # device name -> model
    port_use: dict[str, int] = {}     # device name -> next free port index

    # 1) devices
    for d in spec.get("devices", []):
        name, model = d["name"], d["model"]
        kwargs = dict(x=int(d.get("x", 100)), y=int(d.get("y", 100)))
        if d.get("ip"):
            kwargs["pc_ip"] = [d["ip"], mask, d.get("gateway", "0.0.0.0")]
        if d.get("ios_config"):
            kwargs["ios_config"] = list(d["ios_config"])
        dev_id = lab.add_device(model, name, **kwargs)
        ids[name] = dev_id
        models[name] = model
        port_use[name] = 0

    # mail server IP: explicit, else the services server's own ip
    srv_spec = spec.get("services") or {}
    default_mail_ip = ""
    for d in spec.get("devices", []):
        if d["name"] == srv_spec.get("server"):
            default_mail_ip = d.get("ip", "")

    # 2) client addressing mode + mail client
    for d in spec.get("devices", []):
        dev_id = ids[d["name"]]
        if d.get("dhcp"):
            cli.client_dhcp(lab, dev_id)
        em = d.get("email")
        if em:
            cli.client_email(lab, dev_id, display_name=d["name"],
                             mail_id=em["mail_id"],
                             server_ip=em.get("server_ip", default_mail_ip),
                             user=em["user"], password=em["password"])

    # 3) auto links (connect_to) + explicit links
    for d in spec.get("devices", []):
        tgt = d.get("connect_to")
        if not tgt:
            continue
        if tgt not in ids:
            raise ValueError("%s connect_to unknown device %r" % (d["name"], tgt))
        a_port = d.get("port") or _source_port(d["model"], port_use[d["name"]])
        port_use[d["name"]] += 1
        b_port = _target_port(models[tgt], port_use[tgt])
        port_use[tgt] += 1
        lab.link(ids[d["name"]], a_port, ids[tgt], b_port, kind=d.get("link_kind", "copper"))

    for lk in spec.get("links", []):
        lab.link(ids[lk["a"]], lk["a_port"], ids[lk["b"]], lk["b_port"],
                 kind=lk.get("kind", "copper"))

    # 4) services on the named server
    s = spec.get("services")
    if s:
        srv = ids[s["server"]]
        svc.clean_services(lab, srv)
        if s.get("dhcp"):
            p = s["dhcp"]
            svc.author_dhcp(lab, srv, pool_name=p.get("pool_name", "pool"),
                            network=p["network"], mask=p.get("mask", mask),
                            start_ip=p["start"], end_ip=p["end"],
                            dns_server=p.get("dns", "0.0.0.0"),
                            default_router=p.get("gateway", "0.0.0.0"),
                            max_users=int(p.get("max_users", 100)))
        if s.get("dns"):
            svc.author_dns(lab, srv, [tuple(r) for r in s["dns"]])
        if s.get("email"):
            e = s["email"]
            svc.author_email(lab, srv, domain=e.get("domain", "mail.com"),
                             accounts=[tuple(a) for a in e.get("accounts", [])])
        if s.get("http"):
            svc.author_http(lab, srv, s["http"])

    if pt_version:
        svc.set_version(lab, pt_version)
    return lab, spec.get("name", "lab")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a Packet Tracer lab from a JSON spec.")
    ap.add_argument("spec", type=Path, help="lab spec .json")
    ap.add_argument("-o", "--output", type=Path, help="output .pkt (default generated/<name>.pkt)")
    ap.add_argument("--pt-version", default=os.environ.get("PT_VERSION"),
                    help="stamp <VERSION> for an older PT (e.g. 8.2.2.0400); or set $PT_VERSION")
    args = ap.parse_args(argv)

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    lab, name = build(spec, args.pt_version)

    out = args.output or (_ROOT / "generated" / ("%s.pkt" % name))
    out.parent.mkdir(parents=True, exist_ok=True)
    lab.save(str(out))
    report = check_pkt(str(out))
    print("built  :", out)
    print("checked:", {k: report[k] for k in
                       ("devices", "links", "dhcp_pools", "dns_records", "validate_ok")})
    if args.pt_version:
        print("version:", args.pt_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
