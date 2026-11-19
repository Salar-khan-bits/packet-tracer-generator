"""Minimal Python side of the ptbot file-drop bridge.

Writes a job JSON into Packet Tracer's ``ptbot/jobs`` mailbox and waits for the
Script Module (``agent/bridge/ptbot_bridge.js``, running inside PT) to drop the
answer into ``ptbot/results``.  No sockets, no third-party install.

    from agent.ptclient import PTClient
    pt = PTClient()
    print(pt.call("ping"))            # {'version': '9.0.1.0858', 'deviceCount': N}
    print(pt.call("list_devices"))

The mailbox lives under PT's own user folder; we find it by trying the usual
candidates (or set ``PTBOT_HOME`` to the full path PT logged as
``[ptbot] bridge ready (home=...)``).
"""
from __future__ import annotations

import glob
import json
import os
import time
import uuid
from pathlib import Path


class PTBridgeError(RuntimeError):
    pass


class PTBridgeTimeout(PTBridgeError):
    pass


# mailbox folder names we understand: our own bridge uses "ptbot"; the
# compatible reference bridge (packet-tracer-mcp) uses "pt-mcp". Both use the
# same jobs/ + results/ layout and the same ping/list_devices protocol.
_MAILBOX_NAMES = ("ptbot", "pt-mcp")


def _candidate_homes() -> list[Path]:
    env = os.environ.get("PTBOT_HOME")
    cands: list[Path] = []
    if env:
        cands.append(Path(env))
    home = Path.home()
    parents = [home, home / "Documents"]
    # PT's getUserFolder() is its install-named profile dir, e.g.
    # ~/Cisco Packet Tracer 9.0.1 (Windows) or ~/Documents/Packet Tracer*.
    for pat in ("Cisco Packet Tracer*", "Documents/Packet Tracer*",
                "Documents/Cisco Packet Tracer*"):
        for hit in glob.glob(str(home / pat)):
            parents.append(Path(hit))
    parents.append(home / "pt")
    for parent in parents:
        for name in _MAILBOX_NAMES:
            cands.append(parent / name)
    return cands


def find_mailbox() -> Path | None:
    """Return a mailbox home that already has jobs/ and results/ (bridge ran)."""
    for c in _candidate_homes():
        if (c / "jobs").is_dir() and (c / "results").is_dir():
            return c
    return None


class PTClient:
    def __init__(self, home: str | os.PathLike | None = None, timeout: float = 20.0):
        self.timeout = timeout
        if home is not None:
            self.home = Path(home)
        else:
            found = find_mailbox()
            if found is None:
                raise PTBridgeError(
                    "ptbot mailbox not found. In Packet Tracer, start the 'ptbot' "
                    "Script Module (Extensions -> Scripting), check its log for "
                    "'[ptbot] bridge ready (home=...)', then set PTBOT_HOME to that "
                    "path (or pass home=...)."
                )
            self.home = found
        self.jobs = self.home / "jobs"
        self.results = self.home / "results"

    def call(self, op: str, args: dict | None = None, *, timeout: float | None = None):
        job_id = uuid.uuid4().hex[:12]
        req = {"id": job_id, "op": op, "args": args or {}}
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.results.mkdir(parents=True, exist_ok=True)

        # write atomically so the bridge never reads a half-written job
        tmp = self.jobs / (job_id + ".json.tmp")
        final = self.jobs / (job_id + ".json")
        tmp.write_text(json.dumps(req), encoding="utf-8")
        os.replace(tmp, final)

        res_path = self.results / (job_id + ".json")
        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while time.time() < deadline:
            if res_path.exists():
                try:
                    data = json.loads(res_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    time.sleep(0.05)  # partial write; retry
                    continue
                try:
                    res_path.unlink()
                except OSError:
                    pass
                if data.get("ok"):
                    return data.get("result")
                raise PTBridgeError("PT bridge error for %r: %s"
                                    % (op, data.get("error")))
            time.sleep(0.05)
        raise PTBridgeTimeout(
            "no response for %r within %.0fs. Is PT open with the 'ptbot' module "
            "Started? Try Extensions -> Scripting -> Run File to force a rescan."
            % (op, timeout if timeout is not None else self.timeout)
        )
