"""Verified walkthrough of a generated lab, driven live in Packet Tracer.

Reads the lab spec (what the generator promised) and proves each part against
the RUNNING network over the bridge: devices present, DHCP addressing, DNS
resolution, and reachability -- each line backed by a real action, not a claim.

    python -m agent.walkthrough specifications/example_lan.json

Requires: Packet Tracer open with THAT lab loaded, in Realtime mode, and the
bridge module Started (see agent/README.md). For DHCP clients, give the sim a
few seconds in Realtime first so they pull an address.

Honest scope: DHCP, DNS and reachability are checked from the device console,
so they are truly verified. HTTP and email in Packet Tracer live only in the
Desktop GUI (no console client), so those are reported as manual steps until we
add UI automation.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from agent.ptclient import PTClient, PTBridgeError
from agent.verify import _send, read_console, host_ipv4, ping, _IPV4

OK, BAD, WARN, INFO = "[ OK ]", "[FAIL]", "[ -- ]", "  ... "


def _ip_int(ip: str) -> int:
    a, b, c, d = (int(x) for x in ip.split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def in_range(ip: str, start: str, end: str) -> bool:
    try:
        return _ip_int(start) <= _ip_int(ip) <= _ip_int(end)
    except (ValueError, AttributeError):
        return False


def dns_resolve(pt: PTClient, src: str, name: str, *, wait_s: float = 8.0):
    """Ping a hostname from a PC; return the IP PT resolved it to (or None)."""
    _send(pt, src, "ping " + name)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(1.2)
        out = read_console(pt, src)
        tail = out[out.rfind("ping " + name):] if ("ping " + name) in out else out
        if re.search(r"could not find host|unknown host", tail, re.I):
            return None, False
        # Packet Tracer prints the RESOLVED ip, not the name: "Pinging
        # 192.168.1.10 with 32 bytes" (no "name [ip]" form). Capturing that ip is
        # proof the name resolved. (The old name+[ip] regex never matched, so DNS
        # always read as failed even when it worked -- fixed 2026-11-19.)
        m = re.search(r"Pinging\s+(" + _IPV4.pattern + r")\s+with", tail, re.I)
        if m:
            replied = bool(re.search(r"Reply from", tail, re.I))
            return m.group(1), replied
    return None, False


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m agent.walkthrough <spec.json>")
        return 2
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    services = spec.get("services") or {}
    devices = spec.get("devices", [])
    server = services.get("server")
    server_ip = next((d.get("ip") for d in devices if d.get("name") == server), None)
    dhcp_pcs = [d["name"] for d in devices if d.get("dhcp")]

    try:
        pt = PTClient()
    except PTBridgeError as e:
        print("ERROR:", e)
        return 2

    passed = failed = manual = 0
    print("=== Verified walkthrough:", spec.get("name", "lab"), "===\n")

    # 1) Devices present in the live lab
    try:
        live = {d["name"] for d in pt.call("list_devices").get("devices", [])}
    except PTBridgeError as e:
        print("ERROR talking to PT:", e)
        return 2
    missing = [d["name"] for d in devices if d["name"] not in live]
    if missing:
        print(BAD, "Devices: missing from open lab:", ", ".join(missing))
        print(INFO, "Open the matching .pkt in Packet Tracer and retry.\n")
        failed += 1
    else:
        print(OK, "Devices: all %d present (%s)" % (len(devices),
              ", ".join(sorted(live))[:60]))
        passed += 1

    # 2) DHCP addressing
    pool = services.get("dhcp")
    host_ips: dict[str, str] = {}
    for pc in dhcp_pcs:
        if pc not in live:
            continue
        ip = host_ipv4(pt, pc)
        if ip:
            host_ips[pc] = ip
            note = ""
            if pool and pool.get("start") and pool.get("end"):
                note = " (in pool)" if in_range(ip, pool["start"], pool["end"]) \
                       else " (OUTSIDE pool %s-%s)" % (pool["start"], pool["end"])
            print(OK, "DHCP: %s got %s%s" % (pc, ip, note))
            passed += 1
        else:
            print(BAD, "DHCP: %s has no address (give it a few s in Realtime?)" % pc)
            failed += 1

    # 3) Reachability: a DHCP PC -> the server
    if server_ip and host_ips:
        src = next(iter(host_ips))
        v = ping(pt, src, server_ip)
        if v["ok"]:
            print(OK, "Reachability: %s can reach server %s (received %s)"
                  % (src, server_ip, v["received"]))
            passed += 1
        else:
            print(BAD, "Reachability: %s got no reply from server %s"
                  % (src, server_ip))
            failed += 1

    # 4) DNS resolution
    if services.get("dns") and host_ips:
        src = next(iter(host_ips))
        for name, expected_ip in [tuple(r) for r in services["dns"]]:
            resolved, replied = dns_resolve(pt, src, name)
            if resolved == expected_ip:
                print(OK, "DNS: %s -> %s%s" % (name, resolved,
                      " and replies" if replied else " (resolved)"))
                passed += 1
            elif resolved:
                print(BAD, "DNS: %s -> %s (expected %s)" % (name, resolved, expected_ip))
                failed += 1
            else:
                print(BAD, "DNS: %s did not resolve" % name)
                failed += 1

    # 5) HTTP / email -- GUI-only in PT, reported as manual
    if services.get("http") is not None:
        where = (services["dns"][0][0] if services.get("dns") else server_ip)
        print(WARN, "HTTP: open a PC Desktop -> Web Browser -> http://%s" % where)
        manual += 1
    if services.get("email"):
        print(WARN, "Email: open a PC Desktop -> Email to send/receive a message")
        manual += 1

    print("\n=== %d verified, %d failed, %d manual ===" % (passed, failed, manual))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
