# Packet Tracer Lab Generator

Generate a complete, ready-to-use Cisco **Packet Tracer** project (`.pkt`) from a
small text file — devices, cabling, IP addressing, **DHCP, DNS, HTTP web page,
and SMTP/POP3 email**, all pre-configured. You describe the lab; the tool writes
the file. It opens straight in Packet Tracer.

> ## 🆕 Got a new task? Use any AI.
> Open **[`AI_PROMPT.md`](AI_PROMPT.md)**, copy the prompt into **Claude, ChatGPT,
> Gemini, Codex — any AI**, paste your task text, and it writes a small spec file.
> Save it, run one command, and open the `.pkt`. That's the whole loop.

---

## What it builds for you

- Switches, hubs, routers, PCs, laptops, servers — cabled automatically
- Static **and** DHCP IP addressing
- **DHCP** server (address pool)
- **DNS** server (name → IP records)
- **HTTP** web page (default or your own HTML)
- **SMTP + POP3 email** (server accounts + pre-filled PC mail clients)
- Router IOS config

You still run the live tests yourself in Packet Tracer (pings/PDU, sending the
emails, opening pages, screenshots) — a generator can't fake those.

---

## Part 1 — First-time setup (do once)

### 1. Install the tools
- **Packet Tracer** — the Cisco app you open `.pkt` files in. (Note its version:
  open PT → **Help → About**, e.g. `9.0.1.0858`. You'll need it in Part 3.)
- **Miniconda** (gives you Python): https://www.anaconda.com/download/success →
  download **Miniconda**, run the installer, accept the defaults.

### 2. Get the code
Go to this repo on GitHub → green **`< > Code`** button → **Download ZIP** →
unzip to a simple path like `D:\packet-tracer-generator`.

*(Or, if you have Git: `git clone <this repo URL>`.)*

### 3. Set up Python
Open **Anaconda Prompt** (Start menu → type "Anaconda Prompt"), then:

```bat
cd /d D:\packet-tracer-generator
conda create -n pt python=3.10 -y
conda activate pt
pip install -r requirements.txt
```

✅ Ends with `Successfully installed packet-tracer-pkt-format-0.4.1 ...`, and your
prompt now starts with `(pt)`.

#### No conda? Use Python's built-in `venv` instead

If you already have **Python 3.10+** and don't want Miniconda, skip step 1's
Miniconda and do this in a normal terminal (check `python --version` first):

**Windows:**

```bat
cd /d D:\packet-tracer-generator
python -m venv .venv
```

Activate — pick the line for your terminal:

```bat
.venv\Scripts\activate.bat            REM Command Prompt (CMD)
.venv\Scripts\Activate.ps1            REM PowerShell
source .venv/Scripts/activate         REM Git Bash
```

Then install:

```bat
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd /path/to/packet-tracer-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Notes:
- If `python` isn't found but `py` is, use `py -m venv .venv` (or `py -3.10 -m venv .venv`).
- PowerShell blocks activation? Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.
- Everyday use: re-activate the venv in each new terminal before running commands.
- The `.venv` folder is git-ignored, so it's never committed.

### 4. Check it works

```bat
python verify.py
```

✅ Expected last line: **`PASS: environment is ready.`**

---

## Part 2 — Make your first lab

```bat
python genlab.py specifications/example_lan.json
```

✅ Prints `built: ...\generated\example_lan.pkt` and `validate_ok: True`.
Open that `.pkt` in Packet Tracer — it has a switch, a server (DHCP + DNS + web +
email), and 4 PCs.

---

## Part 3 — Make a lab from a new task (the main use)

1. Open **`AI_PROMPT.md`** and copy the prompt block.
2. Paste it into any AI. At the bottom, replace the placeholders:
   - your **name + roll number**
   - your **task text**
   - your **Packet Tracer build** (from Help → About)
3. Save the JSON it gives back as `specifications/mylab.json`.
4. Generate (always use `--seed` with your name/roll so your file is unique):

```bat
python genlab.py specifications/mylab.json --seed "Your Name 22F-1234" --pt-version 9.0.1.0858
```

(use your real name/roll and PT build). 5. Open `generated\mylab.pkt` in Packet Tracer.

**Why this is safe for any task:** the AI only writes the *spec* (what devices
and services you want). The tool holds the correct Packet Tracer formats, so the
output is always a valid, openable file.

### Make your file unique (so no two people's files match)

Add `--seed` with your name or roll number. It nudges device positions (and fills
a blank web page) from your seed, so your `.pkt` is non-identical to everyone
else's — byte-for-byte and visibly — while the topology and services stay
correct. Same seed always rebuilds the same file.

```bat
python genlab.py specifications/mylab.json --seed "Your Name 22F-1234" --pt-version 9.0.1.0858
```

Two different seeds → two clearly different files; the same seed → the exact same
file every time.

**With `--seed`, your subnet and email domain also vary per person — by default.**
The whole LAN shifts to a per-person `192.168.N.0/24`, and the email domain becomes
something like `example-ab12.test`, with the server, DHCP pool, DNS and gateway all
kept consistent. The command **prints the subnet/domain it used — write those exact
values in your answer** so your report matches your file.

If the task **requires a specific** subnet or email domain, keep them with
`--keep-ip` / `--keep-mail`:

```bat
python genlab.py specifications/mylab.json --seed "Your Name 22F-1234" --keep-ip --keep-mail
```

- `--keep-ip` — keep the task's exact subnet/IPs.
- `--keep-mail` — keep the task's exact email domain.

(The `AI_PROMPT.md` prompt tells the AI to write you a unique web page, include
`--seed`, and add `--keep-ip`/`--keep-mail` automatically when your task pins a
specific subnet or domain.)

---

## Part 4 — Opening in Packet Tracer / version mismatch

- **Opens fine?** Done — do the live tests (pings, send emails, screenshots).
- **"not compatible with this version"?** The file is stamped newer than your PT.
  Rebuild for your version (Help → About):

  ```bat
  python genlab.py specifications/mylab.json --pt-version 8.2.2.0400
  ```

  or fix a file already made:

  ```bat
  python -m engine.restamp 8.2.2.0400
  ```

  (equal or older than your PT always opens). This is the *only* reason a
  generated file fails to open.

---

## The spec format (what the AI fills in)

A lab is one JSON file. All services are optional. See
`specifications/example_lan.json` for a full working example.

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
     "email": {"user": "pc1", "password": "pc1", "mail_id": "pc1@example.test"}}
  ],
  "services": {
    "server": "Server0",
    "dhcp":  {"pool_name": "lan", "network": "192.168.1.0",
              "start": "192.168.1.100", "end": "192.168.1.200", "dns": "192.168.1.10"},
    "dns":   [["www.example.test", "192.168.1.10"]],
    "email": {"domain": "example.test", "accounts": [["pc1", "pc1"]]},
    "http":  "<html><body><h1>Hi</h1></body></html>"
  }
}
```

**Device fields:** `name`, `model` (required); `x`,`y` (position); `ip` (static —
omit for DHCP); `dhcp: true`; `connect_to` (auto-cable to a switch/hub);
`port` (override the source port); `ios_config` (router IOS lines);
`email` (pre-fill the PC mail client).

**Models:** switch `2960-24TT`, hub `Hub-PT`, router `2911`, `PC-PT`,
`Laptop-PT`, `Server-PT`. Full list: `generated/device_catalog.json`.

**`links`** (array, optional): cables `connect_to` can't express (hub rings,
router uplinks) — `{"a","a_port","b","b_port","kind":"copper|serial"}`.

---

## Everyday use (after setup)

```bat
conda activate pt
python genlab.py specifications/<yourlab>.json --pt-version <your PT build>
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `conda not recognized` | Use **Anaconda Prompt**, not plain CMD |
| `python not recognized` | Run `conda activate pt` first |
| `ModuleNotFoundError: pkt_core` | `pip install -r requirements.txt` (with `(pt)` active) |
| PT: "not compatible with this version" | add `--pt-version <your PT build>` |
| `verify.py` didn't say PASS | redo Part 1, step 3, and confirm `(pt)` is active |

## Project layout

```
genlab.py              build a .pkt from a JSON spec
verify.py              one-command environment self-test
AI_PROMPT.md           copy-paste prompt for any AI (new task -> spec)
engine/emit/           the service + client authors (correct PT formats)
engine/restamp.py      change a file's version for an older PT
validators/check.py    validates every build before it's written
specifications/        your lab specs (JSON); example_lan.json included
generated/             output .pkt files + the device catalog
```

Built on the `packet-tracer-pkt-format` (`pkt_core`) library.
