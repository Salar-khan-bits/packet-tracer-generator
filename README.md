# Packet Tracer Lab Generator

Generates complete, configured Cisco Packet Tracer `.pkt` projects (topology,
IP addressing, DHCP, DNS, HTTP, SMTP/POP3 email) from Python builders or a small
JSON spec. Built on `packet-tracer-pkt-format` (`pkt_core`). Output opens in
Packet Tracer and is ready to use — no manual service entry.

> ### 🆕 New task? Use any AI.
> Open **[`AI_PROMPT.md`](AI_PROMPT.md)**, copy the prompt into Claude Code,
> Codex, ChatGPT, Gemini (any of them), paste your task, and it writes a spec.
> Save it under `specifications/`, run `python genlab.py specifications/<name>.json`,
> and open the `.pkt`. That's the whole loop. Full setup is below.

---

## 1. Setup (once per machine)

Needs Python 3.10+ and the library:

```bash
pip install packet-tracer-pkt-format==0.4.1      # (also in requirements.txt)
```

A conda env works well:

```bash
conda create -n packet-tracer python=3.10 -y
conda activate packet-tracer
pip install -r requirements.txt
```

> **You only need Python to *generate* labs.** To just *open* already-generated
> `.pkt` files you only need Packet Tracer — copy the files and open them.

---

## 2. Generate a lab

### A. From a JSON spec (recommended — no code editing per task)

```bash
python genlab.py specifications/example_showcase.json
# -> generated/<name>.pkt
```

Write one JSON file per assignment; see **Section 4** and
`specifications/example_showcase.json`.

### B. From the ready-made builders

```bash
python build_assignment1.py 22F-1234     # -> generated/assignment_cisco/22F-1234_Showcase.pkt
python build_lab05.py                    # -> generated/lab_05/task1..5.pkt
```

Every build is validated (no duplicate/invalid records) and re-decoded before it
is written.

---

## 3. Version mismatch ("not compatible with this version")

Packet Tracer **refuses a file whose version is newer than itself**. Files are
stamped `9.0.1.0858` by default. If your PT is older, stamp to its build number
(PT → Help → About):

```bash
# at build time:
python genlab.py mylab.json --pt-version 8.2.2.0400
set PT_VERSION=8.2.2.0400 && python build_assignment1.py 22F-1234   # Windows cmd

# or re-stamp files already built:
python -m engine.restamp 8.2.2.0400                      # all generated/*.pkt
python -m engine.restamp 8.2.2.0400 generated/lab_05/task1.pkt
```

Equal or older than your PT always opens. (This is the *only* reason a generated
file fails to open — the topology/services are version-independent.)

---

## 4. Writing a lab spec

A spec is one JSON object. All services are optional. Minimal shape:

```json
{
  "name": "mylab",
  "mask": "255.255.255.0",
  "devices": [
    {"name": "Switch0", "model": "2960-24TT", "x": 430, "y": 250},
    {"name": "Server0", "model": "Server-PT", "x": 430, "y": 110,
     "ip": "192.168.1.10", "connect_to": "Switch0"},
    {"name": "PC1", "model": "PC-PT", "x": 150, "y": 420, "dhcp": true,
     "connect_to": "Switch0",
     "email": {"user": "pc1", "password": "pc1", "mail_id": "pc1@mail.com"}}
  ],
  "services": {
    "server": "Server0",
    "dhcp": {"pool_name": "p", "network": "192.168.1.0",
             "start": "192.168.1.100", "end": "192.168.1.200",
             "dns": "192.168.1.10", "gateway": "0.0.0.0"},
    "dns":   [["www.mysite.test", "192.168.1.10"]],
    "email": {"domain": "mail.com", "accounts": [["pc1", "pc1"]]},
    "http":  "<html><body><h1>Hi</h1></body></html>"
  }
}
```

**Device fields:** `name`, `model` (required); `x`, `y` (canvas position);
`ip` (static address — omit for DHCP); `dhcp: true` (acquire via DHCP);
`connect_to` (auto-cable to a switch/hub, ports chosen automatically);
`port` (override the source port); `ios_config` (list of IOS lines, for routers);
`email` (pre-fill the mail client: `user`, `password`, `mail_id`;
server IP is taken from the services server automatically).

**`links`** (array): for cables `connect_to` can't express (hub rings, router
uplinks) — `{"a","a_port","b","b_port","kind"}` with `kind` `copper` or `serial`.

**Models:** 137 available — see `generated/device_catalog.json`. Common ones:
`2960-24TT` (switch), `Hub-PT` (hub), `2911` (router), `PC-PT`, `Laptop-PT`,
`Server-PT`.

Port names (if setting `port`/`links` by hand): IOS switch `FastEthernet0/1…`,
generic Switch-PT/Hub-PT `FastEthernet0…`, router `GigabitEthernet0/0…`,
end devices `FastEthernet0`.

---

## 5. What's automatic vs. manual

**Automatic** (in the file): topology, cabling, static + DHCP addressing, DHCP
pools, DNS A-records, HTTP page content, SMTP/POP3 accounts, pre-filled PC mail
clients, IOS config.

**Yours, in Packet Tracer** (runtime proofs — a generator can't fake them):
running PDU/ping tests, actually sending/receiving the demo emails, opening pages
in the browser, screenshots, and any Wireshark exercise.

> `Laptop-PT` ships without a mail-client block, so its Configure Mail is not
> pre-filled — set it by hand only if you need to send mail *from* the laptop.

---

## 6. Project layout

```
genlab.py              spec-driven generator (Section 2A)
build_assignment1.py   CNET Assignment 1 builder
build_lab05.py         Lab 05 tasks 1–5 builder
engine/emit/           service + client authors (the real PT XML formats)
engine/restamp.py      version re-stamp utility (Section 3)
engine/discovery/      read-only capability inspectors (-> generated/*.json, *.md)
validators/check.py    post-build validation gate
specifications/        lab specs (JSON)
generated/             outputs + the capability audit (TECHNICAL_AUDIT.md, etc.)
```

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "not compatible with this version" on open | file version newer than your PT | re-stamp (Section 3) |
| `ModuleNotFoundError: pkt_core` | library not installed | `pip install -r requirements.txt` |
| a service tab is empty in PT | that service wasn't in the spec | add it under `services` and rebuild |
