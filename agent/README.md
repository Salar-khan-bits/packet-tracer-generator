# ptbot — external bot that drives Packet Tracer (spike)

Goal: a Claude-powered **walkthrough bot** that reads your live network in
Packet Tracer, highlights devices, runs real pings to *verify* each step, and
narrates it for a learner.

This folder is the **first milestone**: prove Packet Tracer will answer us.
Everything talks to PT through a tiny **file-drop mailbox** — no network sockets,
no third-party install. A small script runs *inside* PT (via its built-in
Scripting engine) and exchanges JSON files with Python.

```
Python (agent/ptclient.py) ──writes──▶ <PT user folder>/ptbot/jobs/<id>.json
                                             │
                        ptbot_bridge.js (inside PT) runs the ipc op
                                             │
Python ◀──reads── <PT user folder>/ptbot/results/<id>.json
```

## One-time Packet Tracer setup

1. Open Packet Tracer **with any lab open** (e.g. `generated/example_lan.pkt`).
2. Menu: **Extensions → Scripting → Configure PT Script Modules… → Add**.
3. **General** tab:
   - **ID:** `com.ptbot.bridge`
   - **Name:** `ptbot`
   - **Startup:** **On Startup**
4. **Script Engine** tab: click **Add**, name the file `bridge.js`, then open
   [`bridge/ptbot_bridge.js`](bridge/ptbot_bridge.js), copy its **entire**
   contents, and paste them into the editor. Click **Apply**.
5. **Security Privileges** tab — tick:
   - **Application**
   - **File Operations**
   - **Get Network Info**
   - **Miscellaneous UI** (optional — enables `[ptbot]` log lines)
6. **Save** to close the dialog, select **ptbot** in the module list, click
   **Start**.
7. In PT's script log you should see:
   `[ptbot] bridge ready (home=…/ptbot)` and `[ptbot] watching …/ptbot/jobs`.
8. Quit PT once with **File → Exit** so it remembers the module, then reopen
   your lab. (A crash/kill forgets the registration — re-add and exit cleanly.)

## Run the spike

With PT open (lab loaded, `ptbot` module Started):

```bat
python -m agent.spike
```

Expected:

```
mailbox: C:\Users\you\...\ptbot
ping   : {'version': '9.0.1.0858', 'deviceCount': 6}
devices: 6 (links: 5)
   - Switch0    2960-24TT      Switch
   - Server0    Server-PT      Server
   - PC1        PC-PT          PC
   ...
PASS: Packet Tracer answered over the bridge. The channel works.
```

If it can't find the mailbox, read the path PT logged after
`[ptbot] bridge ready (home=…)` and set it:

```bat
set PTBOT_HOME=C:\full\path\to\ptbot
python -m agent.spike
```

If a call times out, the folder watcher may not be firing on your install:
**Extensions → Scripting → Run File** (pick the module) forces a rescan.

## What this proves / what's next

The spike only **reads** (ping, list devices) — deliberately safe. Once this
round-trip works on your build, the next milestones add *driving*: highlight a
device, run a `ping` between two PCs and read the result (verification), then
the Claude agent that narrates a verified walkthrough.

Credit: the mailbox pattern and several `ipc` call names were learned from the
MIT-licensed [packet-tracer-mcp](https://github.com/psampir/packet-tracer-mcp)
by Pawel Sampir. The bridge here is an original, minimal, read-only
reimplementation.
