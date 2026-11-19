#!/usr/bin/env python
"""Build a Packet Tracer **Activity (.pka) guide** from a lab spec.

The learner opens ONE ``.pka`` and sees the generated network together with a
step-by-step instructions pane that walks them through it (overview, each
service, and a "try it yourself" checklist).

    python genactivity.py specifications/example_lan.json
        -> generated/example_lan_guide.pka
    python genactivity.py specifications/mylab.json --pt-version 8.2.2.0400
    python genactivity.py specifications/mylab.json --from generated/mylab.pkt

This is the Tier-1 guide activity: it shows and explains the network.  It does
not grade the learner yet (that is Tier 2).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
from pathlib import Path

from engine.emit.activity import author_activity
from genlab import build, vary_spec

_ROOT = Path(__file__).resolve().parent


def _esc(s: object) -> str:
    return html.escape(str(s), quote=False)


def walkthrough_pages(spec: dict) -> list[tuple[str, str]]:
    """Return a list of (title, limited-HTML) instruction pages for ``spec``."""
    devices = spec.get("devices", [])
    services = spec.get("services") or {}
    server = services.get("server")
    pages: list[tuple[str, str]] = []

    # ---- Overview ---------------------------------------------------------
    lines = [
        "<b>%s</b><br>" % _esc(spec.get("name", "Network")),
        "This activity is a guided tour of the network in this file. "
        "Use the <b>tabs above</b> (or Next) to step through it.<br><br>",
        "<b>Devices</b><br>",
    ]
    for d in devices:
        bits = "%s &mdash; %s" % (_esc(d["name"]), _esc(d["model"]))
        if d.get("ip"):
            bits += " (IP %s)" % _esc(d["ip"])
        elif d.get("dhcp"):
            bits += " (gets its IP from DHCP)"
        if d.get("connect_to"):
            bits += " &rarr; connects to %s" % _esc(d["connect_to"])
        lines.append("&bull; " + bits + "<br>")
    if server:
        roles = [k.upper() for k in ("dhcp", "dns", "http", "email") if services.get(k)]
        if roles:
            lines.append("<br><b>%s</b> is the server. It runs: %s.<br>"
                         % (_esc(server), ", ".join(roles)))
    pages.append(("Overview", "".join(lines)))

    # ---- DHCP -------------------------------------------------------------
    if services.get("dhcp"):
        p = services["dhcp"]
        dhcp_clients = [d["name"] for d in devices if d.get("dhcp")]
        body = [
            "<b>DHCP &mdash; automatic addressing</b><br><br>",
            "The server <b>%s</b> hands out IP addresses so the PCs don't need "
            "them set by hand.<br><br>" % _esc(server),
            "<b>Pool</b><br>",
            "&bull; Range: %s &ndash; %s<br>" % (_esc(p["start"]), _esc(p["end"])),
            "&bull; DNS given to clients: %s<br>" % _esc(p.get("dns", "—")),
        ]
        if p.get("gateway"):
            body.append("&bull; Default gateway: %s<br>" % _esc(p["gateway"]))
        if dhcp_clients:
            body.append("<br><b>Who uses it:</b> %s.<br>"
                        % _esc(", ".join(dhcp_clients)))
        body.append("<br><font color=\"#555555\">See it: click %s &rarr; "
                    "Services &rarr; DHCP; click a PC &rarr; Desktop &rarr; "
                    "IP Configuration &rarr; DHCP.</font>" % _esc(server))
        pages.append(("DHCP", "".join(body)))

    # ---- DNS --------------------------------------------------------------
    if services.get("dns"):
        recs = services["dns"]
        body = ["<b>DNS &mdash; names to addresses</b><br><br>",
                "<b>%s</b> translates names into IP addresses:<br>" % _esc(server)]
        for r in recs:
            body.append("&bull; %s &rarr; %s<br>" % (_esc(r[0]), _esc(r[1])))
        body.append("<br><font color=\"#555555\">See it: %s &rarr; Services "
                    "&rarr; DNS.</font>" % _esc(server))
        pages.append(("DNS", "".join(body)))

    # ---- HTTP -------------------------------------------------------------
    if services.get("http") is not None:
        body = [
            "<b>HTTP &mdash; the web page</b><br><br>",
            "<b>%s</b> hosts a web page. Any PC can open it in its browser."
            "<br><br>" % _esc(server),
            "<font color=\"#555555\">Try it: click a PC &rarr; Desktop &rarr; "
            "Web Browser &rarr; type the server's IP",
        ]
        dns = services.get("dns") or []
        if dns:
            body.append(" (or http://%s)" % _esc(dns[0][0]))
        body.append(".</font>")
        pages.append(("Web (HTTP)", "".join(body)))

    # ---- Email ------------------------------------------------------------
    if services.get("email"):
        e = services["email"]
        accts = e.get("accounts", [])
        body = [
            "<b>Email &mdash; SMTP &amp; POP3</b><br><br>",
            "<b>%s</b> is the mail server for domain <b>%s</b>.<br><br>"
            % (_esc(server), _esc(e.get("domain", ""))),
        ]
        if accts:
            body.append("<b>Accounts</b><br>")
            for a in accts:
                body.append("&bull; %s@%s<br>" % (_esc(a[0]), _esc(e.get("domain", ""))))
        body.append("<br><font color=\"#555555\">Try it: on a PC &rarr; Desktop "
                    "&rarr; Email, compose a message to another account and "
                    "Send, then Receive on the other PC.</font>")
        pages.append(("Email", "".join(body)))

    # ---- Try it yourself --------------------------------------------------
    checklist = ["<b>Try it yourself</b><br><br>Prove each part works:<br>"]
    if services.get("dhcp"):
        checklist.append("&#9633; A PC on DHCP shows an address in the pool range.<br>")
    checklist.append("&#9633; Ping between two PCs succeeds (Realtime, or a "
                     "Simulation PDU).<br>")
    if services.get("dns"):
        checklist.append("&#9633; A PC can ping/open a DNS name, not just an IP.<br>")
    if services.get("http") is not None:
        checklist.append("&#9633; A PC's Web Browser opens the server's page.<br>")
    if services.get("email"):
        checklist.append("&#9633; One PC emails another and it is received.<br>")
    checklist.append("<br><font color=\"#555555\">Take a screenshot of each for "
                     "your report.</font>")
    pages.append(("Try it", "".join(checklist)))

    return pages


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a Packet Tracer Activity (.pka) guide from a lab spec.")
    ap.add_argument("spec", type=Path, help="lab spec .json")
    ap.add_argument("-o", "--output", type=Path,
                    help="output .pka (default generated/<name>_guide.pka)")
    ap.add_argument("--from", dest="from_pkt", type=Path,
                    help="use this already-built network .pkt instead of "
                         "rebuilding from the spec")
    ap.add_argument("--pt-version", default=os.environ.get("PT_VERSION"),
                    help="stamp <VERSION> for an older PT (e.g. 8.2.2.0400)")
    ap.add_argument("--seed", default=None,
                    help="same per-person seed as genlab (keeps the guide's "
                         "network identical to the student's .pkt)")
    ap.add_argument("--keep-ip", action="store_true")
    ap.add_argument("--keep-mail", action="store_true")
    ap.add_argument("--template", type=Path, default=None,
                    help="activity template .pka (default templates/activity_template.pka)")
    args = ap.parse_args(argv)

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    vary_ip = bool(args.seed) and not args.keep_ip
    vary_mail = bool(args.seed) and not args.keep_mail
    if args.seed and (vary_ip or vary_mail):
        spec, changed = vary_spec(spec, args.seed, vary_ip=vary_ip, vary_mail=vary_mail)
        for key, val in changed.items():
            print("varied %-7s-> %s   (write THIS in your answer)" % (key, val))

    name = spec.get("name", "lab")
    pages = walkthrough_pages(spec)

    # Build (or reuse) the network .pkt.
    if args.from_pkt:
        net_pkt = args.from_pkt
    else:
        lab, _ = build(spec, args.pt_version, seed=args.seed)
        tmp = Path(tempfile.gettempdir()) / ("%s_netsrc.pkt" % name)
        lab.save(str(tmp))
        net_pkt = tmp

    out = args.output or (_ROOT / "generated" / ("%s_guide.pka" % name))
    author_activity(net_pkt, out, pages,
                    template=args.template, version=args.pt_version)

    # sanity: re-decode and confirm it is a real activity
    from pkt_core.builder.lab import decode
    c = decode(str(out))
    print("built  :", out)
    print("checked:", {"is_activity": c.is_activity, "root": c.root_tag,
                       "pages": len(pages)})
    if args.pt_version:
        print("version:", args.pt_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
