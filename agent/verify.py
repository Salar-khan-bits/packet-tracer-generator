"""Live verification over the PT bridge: run a REAL ping between two hosts and
read the result straight from Packet Tracer.

This is the first "driving" milestone (the spike only read state). It proves we
can make PT *do* something and judge the outcome -- the core of turning a
walkthrough's "verifiable" step into "verified".

    python -m agent.verify                 # auto: first two PCs in the open lab
    python -m agent.verify PC1 PC2         # ping from PC1 to PC2
    python -m agent.verify PC1 192.168.1.10

Requires: Packet Tracer open with the lab loaded, and the bridge module Started
(see agent/README.md). Runs on whatever lab is ACTIVE in PT.
"""
from __future__ import annotations

import json
import re
import sys
import time

from agent.ptclient import PTClient, PTBridgeError

_IPV4 = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
# PCs/servers are end hosts we can drive from a command prompt.
_END_HOST_TYPES = {8, 9, 17, 18}  # PC, Server, Laptop, TabletPC

# JS that reads a device's full console buffer WITHOUT sending a command, so we
# can poll it from Python between sleeps (letting PT's simulation run).
_READ_CONSOLE_JS = (
    "(function(){var d=ipc.network().getDevice(%s);if(!d){return '';}"
    "var l=null;try{l=d.getConsoleLine();}catch(e){}"
    "if(!l){try{l=d.getCommandLine();}catch(e){}}"
    "return l?String(l.getOutput()):'';})()"
)


def _send(pt: PTClient, device: str, command: str, timeout_ms: int = 4000) -> str:
    """Send one command to a device's console (returns the immediate output)."""
    res = pt.call("exec", {"device": device, "command": command,
                           "timeout_ms": timeout_ms})
    return str(res.get("output", "")) if isinstance(res, dict) else str(res)


def read_console(pt: PTClient, device: str) -> str:
    """Read a device's accumulated console buffer (no command sent)."""
    res = pt.call("eval", {"js": _READ_CONSOLE_JS % json.dumps(device)})
    val = res.get("value") if isinstance(res, dict) else res
    if isinstance(val, str):
        # the eval op returns the value JSON-stringified -> decode one layer
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return val
    return str(val)


def host_ipv4(pt: PTClient, device: str) -> str | None:
    """Best-effort read of a host's IPv4 address via `ipconfig`."""
    _send(pt, device, "ipconfig")
    out = read_console(pt, device)
    tail = out[out.rfind("ipconfig"):] if "ipconfig" in out else out
    for m in _IPV4.finditer(tail):
        ip = m.group(1)
        if ip not in ("0.0.0.0", "255.255.255.0") and not ip.startswith("127."):
            return ip
    return None


def ping(pt: PTClient, src: str, target: str, *, wait_s: float = 12.0) -> dict:
    """Ping `target` from `src`, polling the console while PT's sim runs."""
    _send(pt, src, "ping " + target)
    deadline = time.time() + wait_s
    out = ""
    while time.time() < deadline:
        time.sleep(1.5)                     # let PT advance the simulation
        out = read_console(pt, src)
        tail = out[out.rfind("ping " + target):] if ("ping " + target) in out else out
        if re.search(r"Packets:\s*Sent", tail, re.I) or \
           re.search(r"Reply from", tail, re.I):
            out = tail
            break
    else:
        out = out[out.rfind("ping " + target):] if ("ping " + target) in out else out

    replies = len(re.findall(r"Reply from", out, re.I))
    m = re.search(r"Received\s*=\s*(\d+).*?Lost\s*=\s*(\d+)", out, re.I | re.S)
    received = int(m.group(1)) if m else replies
    lost = int(m.group(2)) if m else None
    return {"ok": received > 0, "received": received, "lost": lost,
            "raw": out.strip()}


def _pick_hosts(pt: PTClient) -> list[str]:
    listing = pt.call("list_devices")
    return [d["name"] for d in listing.get("devices", [])
            if d.get("type") in _END_HOST_TYPES]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        pt = PTClient()
    except PTBridgeError as e:
        print("ERROR:", e)
        return 2

    try:
        if len(argv) >= 2:
            src, target = argv[0], argv[1]
        else:
            hosts = _pick_hosts(pt)
            if len(hosts) < 2:
                print("need at least two end hosts (PC/Server) in the open lab; "
                      "found:", hosts)
                return 1
            src = hosts[0]
            target = argv[0] if argv else hosts[1]

        # If target is a device name (not an IP), resolve its IPv4.
        if not _IPV4.fullmatch(target):
            print("resolving %s's IP ..." % target)
            ip = host_ipv4(pt, target)
            if not ip:
                print("could not read %s's IPv4 (is it configured / powered?)." % target)
                return 1
            print("   %s = %s" % (target, ip))
            target_ip = ip
            target_label = "%s (%s)" % (target, ip)
        else:
            target_ip = target
            target_label = target

        print("\nping  %s  ->  %s" % (src, target_label))
        verdict = ping(pt, src, target_ip)
        print("-" * 56)
        print(verdict["raw"])
        print("-" * 56)
        if verdict["ok"]:
            print("VERIFIED: %s can reach %s (received %s)."
                  % (src, target_label, verdict["received"]))
            return 0
        print("NOT reachable: %s got no reply from %s." % (src, target_label))
        return 1
    except PTBridgeError as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
