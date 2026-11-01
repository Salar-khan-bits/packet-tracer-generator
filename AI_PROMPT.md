# Paste-into-any-AI prompt (new task → `.pkt`)

When a new Packet Tracer task is given, copy the block below into **any** AI
(Claude Code, Codex, ChatGPT/OpenAI, Gemini, …), replace the two `<<< >>>`
placeholders, and it will produce a spec file. Then run the one command it prints.

The AI's only job is to write a **JSON spec** — it does **not** need to know PT's
file format; `genlab.py` already encodes the correct, verified formats.

---

```
You are generating a lab spec for a Cisco Packet Tracer generator called
`genlab.py`. Produce ONE JSON spec file and nothing else, following this schema.

SCHEMA (all services optional):
{
  "name": "<short_filename>",
  "mask": "255.255.255.0",
  "devices": [
    {"name","model","x","y",
     "ip":"<static IP>"            (omit for DHCP),
     "dhcp": true                  (acquire via DHCP),
     "connect_to":"<switch/hub name>"   (auto-cables; ports auto-assigned),
     "port":"<override source port>",
     "ios_config":["IOS line", ...]      (routers),
     "email":{"user","password","mail_id":"user@domain"}   (pre-fill PC mail client)
    }
  ],
  "links": [ {"a","a_port","b","b_port","kind":"copper|serial"} ]  (only for cables
             connect_to can't express: hub-to-hub rings, router uplinks),
  "services": {
    "server":"<the server device name>",
    "dhcp": {"pool_name","network","start","end","dns","gateway","max_users"},
    "dns":  [ ["name.example.test","<IP>"] ],
    "email":{"domain","accounts":[ ["user","password"], ... ]},
    "http": "<html>...</html>"
  }
}

MODELS (use these exact strings): switch "2960-24TT"; hub "Hub-PT";
router "2911"; PC "PC-PT"; laptop "Laptop-PT"; server "Server-PT".
(Full list: generated/device_catalog.json.)

PORT NAMES if you set "port"/"links" by hand: IOS switch (2960) "FastEthernet0/1",
"FastEthernet0/2", ...; generic Switch-PT/Hub-PT "FastEthernet0","FastEthernet1",...;
router 2911 "GigabitEthernet0/0","GigabitEthernet0/1"; PC/laptop/server "FastEthernet0".

RULES:
- One LAN unless the task says otherwise; typical subnet 192.168.1.0/24.
- Put every end device and the server on the switch/hub with "connect_to".
- A server providing SMTP/DNS/HTTP/DHCP is ONE "Server-PT"; list the service
  blocks under "services" with "server" = that device's name.
- For DHCP clients set "dhcp": true and DON'T set "ip"; give the server a static "ip".
- To let clients send email, give the server "email".accounts AND give each PC an
  "email" block (user/password matching an account). Laptops can't be pre-filled —
  leave their "email" out.
- Keep x spread ~125 apart on one row (y=420) for clients; switch y=250; server y=110.

THE TASK:
<<< PASTE THE FULL TASK / ASSIGNMENT TEXT HERE >>>

Output ONLY the JSON. Also tell me the exact command to run it, in the form:
  python genlab.py specifications/<name>.json --pt-version <<< YOUR PACKET TRACER BUILD >>>
```

---

## After the AI replies
1. Save its JSON as `specifications/<name>.json`.
2. Run the command it printed (find your PT build in Packet Tracer → Help → About;
   drop `--pt-version` if your PT is 9.0.1.0858 or newer).
3. Open `generated/<name>.pkt` in Packet Tracer.
4. Do the runtime parts yourself: PDU/ping tests, send/receive the demo emails,
   open pages in the browser, screenshots.

## Want a standalone `.py` instead of a spec?
Ask the AI: *"Instead of JSON, write a Python script like `build_assignment1.py`
that imports `engine.emit.services` and `engine.emit.clients` to build the same
lab, and give me the run command."* The JSON+`genlab.py` route is simpler and
less error-prone, so prefer it unless the task needs custom logic.
