"""ptbot bridge spike: prove Packet Tracer answers us over the file-drop mailbox.

Prereq (one-time): in Packet Tracer, add the Script Module from
``agent/bridge/ptbot_bridge.js`` and Start it (see agent/README.md), with a
lab open.  Then:

    python -m agent.spike

Expected: PT's version + device count, and a listing of the open lab's devices.
"""
from __future__ import annotations

import sys

from agent.ptclient import PTClient, PTBridgeError, find_mailbox


def main() -> int:
    box = find_mailbox()
    print("mailbox:", box if box else "NOT FOUND (is the ptbot module Started?)")
    try:
        pt = PTClient()
    except PTBridgeError as e:
        print("ERROR:", e)
        return 2

    try:
        pong = pt.call("ping")
        print("ping   :", pong)
        listing = pt.call("list_devices")
        devs = listing.get("devices", [])
        print("devices: %d (links: %s)" % (len(devs), listing.get("links")))
        for d in devs:
            print("   - %-10s %-14s %s"
                  % (d.get("name"), d.get("model"), d.get("typeName")))
    except PTBridgeError as e:
        print("ERROR:", e)
        return 1

    print("\nPASS: Packet Tracer answered over the bridge. The channel works.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
