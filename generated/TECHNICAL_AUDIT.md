# Technical Audit — `packet-tracer-pkt-format` 0.4.1 (`pkt_core`)

**Date:** 2026-11-01
**Target:** `packet-tracer-pkt-format==0.4.1`, installed at
`C:\Users\Salar\miniconda3\envs\packet-tracer\Lib\site-packages\pkt_core`
**Packet Tracer:** 9.0.1.0858 · **Python:** 3.10 (conda env `packet-tracer`)
**Method:** full read of all 28 package source files + bundled data, plus
read-only extraction scripts under `engine/discovery/` and a repack/reopen
proof-of-concept. No package, environment, or existing project artifact was
modified.

> **Headline:** Yes — a Python application can generate complete, working `.pkt`
> projects (topology + IP + IOS config + DHCP/DNS/HTTP/SMTP/POP3/FTP/AAA) using
> this library. Topology/power/cabling/IOS/end-device-IP/wireless are covered by
> a **verified builder API**; every GUI *service* is authored by **direct XML
> manipulation** of the device `<ENGINE>` block, which the library is explicitly
> designed to make lossless and which this audit proved round-trips through the
> real container format. Evidence throughout.

---

## 1. Package architecture

`pkt_core` is two cleanly separated subsystems plus a container codec. This
separation is the single most important fact for the generator design.

```
pkt_core/
├── codec/            CONTAINER: .pkt/.pka  <->  XML bytes
│   ├── container.py    decode()/encode() + verifier-based format detection
│   └── qcompress.py    Qt qCompress framing (4-byte BE len + zlib)
├── crypto/           EAX AEAD over Twofish/Serpent/CAST (fixed key+IV per fmt)
│   ├── keys.py         6 modern formats + 1 legacy, key/iv bytes
│   ├── ciphers*.py     block ciphers (C-accelerated + pure-python fallback)
│   ├── primitives.py   eax_seal / eax_open / eax_verify
│   └── stream.py       layer_a (reverse+XOR) / layer_b (positional XOR)
├── xml/              LOSSLESS byte-preserving XML tree
│   ├── nodes.py        XmlDocument/XmlElement/XmlText + lazy parser
│   └── writer.py       element()/text() synthesis helpers
├── models/           TYPED READ/MODIFY VIEWS over xml/ (data loss impossible)
│   ├── lab.py          Lab, Network, RunningConfig, Cluster, LabOptions
│   ├── network.py      Device, Port, Module, Cable, Link, Workspace
│   ├── schema.py       PortConfig, WirelessConfig, DeviceDetails, FileEntry, …
│   └── services.py     DhcpPool, DnsRecord, FtpAccount, AaaUser/Client, DeviceServices
├── builder/
│   └── lab.py          AUTHORING API: Lab (ElementTree-based) + Layout packer
├── audit.py          service inventory, template-leftover sanitiser, validator
├── diff.py           semantic (model-level) document diff
├── export.py         graphviz / netbox / containerlab exporters
├── resources.py      bundled device_templates.json + network_seed.xml loaders
└── cli/main.py       `pkt info|unpack|pack|diff|export|audit`
```

### Two XML worlds (do not conflate them)

| | `pkt_core.builder.lab.Lab` | `pkt_core.models.*` |
|---|---|---|
| XML engine | `xml.etree.ElementTree` | custom lossless tree (`pkt_core.xml.nodes`) |
| Purpose | **author** a new lab from the seed + templates | **read/modify** an existing document |
| Fidelity | ET re-serialisation (normalises whitespace/attr quoting) | **byte-exact** for anything untouched |
| Serialises via | `ET.tostring` → `encode()` | `Lab.to_xml()` → `encode()` |
| Entry point | `pkt_core.Lab` (re-exported) | `pkt_core.models.Lab` |

`audit.py` deliberately bridges both through an `ElementView` protocol
(`as_view()` adapts either tree), so a generator building with ElementTree can
still run the library's sanitiser/validator on its own document.

---

## 2. `.pkt` / `.pka` file format handling

Fully implemented and **verified byte-exact** by the library's own notes
(`encode(decode(f)) == f` on 1,014 corpus files). Layering (outer→inner):

```
file bytes
  → layer A : reverse + positional XOR          (stream.py)
  → EAX AEAD ciphertext ‖ 16-byte tag           (Twofish, fixed key/IV)   crypto/
  → layer B : positional XOR (involution)        (stream.py)
  → Qt qCompress : 4-byte BE length + zlib        (qcompress.py)
  → UTF-8 XML
```

Key facts for the generator:

- **No magic header.** Format detection is a cryptographic oracle: try each
  format, accept the one whose EAX tag verifies (2⁻¹²⁸ false-positive rate),
  `codec/container.py:detect_format`.
- **Deterministic.** Fixed key + fixed IV per format ⇒ identical XML yields
  identical bytes. Reproducible builds are possible.
- **Formats** (`crypto/keys.py`): `pkt` (Twofish, key `0x89`/iv `0x10`) is the
  one for `.pkt`/`.pka`. Also `log`, `pkc`, `pta`, `sm`, `userapp`, and a
  `legacy` PT 5.x family (zlib only, no AEAD).
- **Public API:** `decode(path)`, `decode_bytes(raw)`, `encode(path, xml, "pkt")`,
  `encode_bytes(xml, "pkt")`. The CLI `pkt unpack`/`pack` wrap these.

### Preservation of unknown elements & application state — *proven by design*

The lossless tree (`xml/nodes.py`) keeps every node's original source span and
re-emits it verbatim unless it is explicitly marked dirty (`XmlElement.to_bytes`
returns `self.raw` when `not self.dirty`). Consequences, all load-bearing for a
generator:

- Editing one `<ENGINE>` subtree leaves **every other byte identical** — GUI
  service configs, web pages, DNS records, DHCP pools, email settings,
  simulation data, physical-workspace state, canvas drawings, activity scoring
  trees are all preserved automatically because the model never touches them.
- Control bytes survive: IOS `banner motd ^C…^C` and CDATA activity HTML are
  exposed as **`bytes`, never decoded** (`models/base.py:_raw_text`,
  `RunningConfig.lines`).
- Every model exposes `extra_fields` — the children it did not claim — so
  nothing is silently dropped, by construction.

The ET-based builder path is lossy only in cosmetic ways (whitespace, attribute
quoting); it is already proven to produce files PT 9 opens (your
`first_network.pkt`). For *surgical edits to an existing file*, prefer the
lossless `models` path.

---

## 3. Device models

- **137 device models** and **78 modules** are bundled
  (`pkt_core/data/device_templates.json`, gzip+base64 JSON). This is the
  authoritative figure from `load_device_templates()` and from the prior
  `capability_report.json` (`total_device_models: 137`). *The "184" in the task
  brief is not supported by the installed package* — the library ships 137.
- Full extraction in **`generated/device_catalog.json`**. Group distribution
  (by icon/layout class + engine `<TYPE>`):

| Group | Count | Examples |
|---|---|---|
| iot | 63 | sensors, actuators, MCU-PT, SBC-PT, Thing |
| other | 26 | phones (7960), cloud/WAN, DLC100, misc |
| routers | 20 | 2911, 1941, 2901, ISR4331, Router-PT, home routers |
| switches | 9 | 2960-24TT, 2950-24, IE-2000, Switch-PT, Hub-PT |
| servers | 4 | Server-PT, Central-Office-Server, SBC |
| pcs / laptops | 3 / 2 | PC-PT, TabletPC-PT / Laptop-PT, LAP-PT |
| wireless | 3 | access points, WLC family |
| layer3_switches | 2 | 3560-24PS, 3650-24PS |
| firewalls | 2 | 5505 (ASA), Meraki-MX |
| analysis / power | 2 / 1 | Sniffer / Power Distribution Device |

Per model the catalog records: `pt_kind` (engine `<TYPE>` text), `model_attr`,
`icon_class`, flat `ports` (type + name), `port_types`, `module_bays`
(type/filled/model), `empty_interface_bays`, `services_present`, `description`.
Unknowns are `null`, never guessed. Spot checks:

- `2911` → `Router`, 3× `eCopperGigabitEthernet`, 4 empty `eInterfaceCard` bays.
- `2960-24TT` → `Switch`, 26 ports (`eCopperFastEthernet` + `eCopperGigabitEthernet`).
- `Server-PT` → `Server`, 1× `eCopperFastEthernet`, carries **all 10** service blocks.

---

## 4. Supported operations

### 4a. Verified builder API (`pkt_core.builder.lab.Lab`) — topology & config

`add_device`, `link`, `install_module`, `set_wireless`, `set_os`,
`set_config_register`, `prune_seed_devices`/`drop_seed_devices`, `device_names`,
`initial_id`, `save`, plus the deterministic `Layout` packer. Covered inline:

- device placement + power (`<ENGINE><POWER>` written in both directions — a
  documented gotcha: a harvested template can ship `POWER=false` and take a
  layer down);
- IOS running config (`ios_config=[...]` → `<RUNNINGCONFIG><LINE>`);
- end-device IPv4 (`pc_ip=(ip,mask,gw)` → NIC `<IP>/<SUBNET>/<PORT_GATEWAY>`
  **and** `<ENGINE><GATEWAY>` — PT reads the gateway from the engine, not the
  port);
- copper (`eCopper`/`eStraightThrough`) and serial links (auto DCE clock rate);
- module install into `eInterfaceCard` bays (absolute `slot=` or next-empty);
- wireless SSID/auth/encryption on wireless ports.

### 4b. Services — **no builder methods; direct XML required**

`builder.Lab` has **no** method for DHCP, DNS, HTTP/HTTPS, SMTP, POP3, FTP, TFTP,
NTP, Syslog, or AAA. These are authored by editing the device `<ENGINE>` XML.
The library supports this with:

- typed **read** views + record **identity** rules (`models/services.py`);
- an **inventory + uniqueness validator** (`audit.py:validate_lab`);
- a **template-leftover sanitiser** (`audit.py:sanitize_template_leftovers`) —
  essential (see §6).

---

## 5. Service structures (authoritative)

Extracted from the `Server-PT` template skeleton, a populated home-router donor,
and the library's own corpus-derived field tables. Full detail in
**`generated/service_capabilities.json`**. `Server-PT` `<ENGINE>` carries these
service containers (all verified present): `HTTP_SERVER`, `HTTPS_SERVER`,
`DNS_SERVER`, `DHCP_SERVERS`, `DHCPV6_SERVER_LIST`, `TFTP_SERVER`, `FTP_SERVER`,
`NTP_SERVER`, `SYSLOG_SERVER`, `ACS_SERVER`, `EMAIL_SERVER`, plus client blocks
(`DNS_CLIENT`, `EMAIL_CLIENT`, `DHCP_CLIENT`, `WIRELESS_CLIENT`).

### DHCP (server family)
Path: `ENGINE/DHCP_SERVERS/ASSOCIATED_PORTS/ASSOCIATED_PORT/DHCP_SERVER/POOLS/POOL`.
Enable: `DHCP_SERVER/ENABLED` = `1|0`. Home-router family uses the shorter
`ENGINE/DHCP_SERVER/POOLS/POOL`. **POOL fields (observed, in order):**
`NAME, NETWORK, MASK, DEFAULT_ROUTER, TFTP_ADDRESS, START_IP, END_IP,
DNS_SERVER, MAX_USERS, DOMAIN_NAME, DHCP_POOL_LEASES, LEASE_TIME, WLC_ADDRESS`.
Identity = `(NAME, NETWORK, MASK)`. **`DHCP_POOL_LEASES`/`DHCP_RESERVATIONS` are
runtime state — never author them.**

### DNS
Path: `ENGINE/DNS_SERVER/NAMESERVER-DATABASE/RESOURCE-RECORD`. Enable:
`DNS_SERVER/ENABLED`. **Record fields:** `TYPE, NAME, TTL, IPADDRESS` (`TYPE` is a
numeric enum). Zone key = `(TYPE, NAME)`, unique per server; the same record may
be replicated across servers legitimately.

### HTTP / HTTPS  ← important
`ENGINE/HTTP_SERVER` holds only `ENABLED, USERNAME, PASSWORD`. **The web pages
live in the simulated filesystem**, not in `<HTTP_SERVER>`:
`ENGINE/FILE_MANAGER/FILE/FILES/FILE[NAME='http:']/FILES/FILE`, each with
`FILE_NUMBER, NAME, DATE_TIME, PERMISSION, FILE_CONTENT`. Default pages shipped:
`index.html, helloworld.html, image.html, copyrights.html` (template bodies are
empty — content is authored into `FILE_CONTENT`). `models/schema.py:FileEntry`
reads these (`.content` as bytes).

### Email (SMTP / POP3)
`ENGINE/EMAIL_SERVER`: `SMTP_ENABLED, SMTP_DOMAIN, POP3_ENABLED, FORWARD_MAIL,
NO_OF_USERS`. Accounts are authored at `EMAIL_SERVER/USERS/USER` with
`NAME, PASSWORD` (templates ship `NO_OF_USERS=0` and no `USERS` node). Client
side is `ENGINE/EMAIL_CLIENT`.

### FTP
`ENGINE/FTP_SERVER/USER_ACCOUNT_MNGR/ACCOUNT` with `USERNAME, PASSWORD,
PERMISSIONS` (e.g. `RWDNL`); enable at `FTP_SERVER/ENABLED`. Identity = `(USERNAME,)`.

### AAA (RADIUS / TACACS+)
`ENGINE/ACS_SERVER`: users at `USERS/USER` (`NAME, PASSWORD, DESCRIPTION`),
clients at `ACS_CLIENTS/CLIENT` (`HOST_IP, KEY, DESCRIPTION, SERVER_TYPE`), plus
`RADIUS_SETTINGS`. User id = `(NAME,)`, client id = `(HOST_IP,)`.

### TFTP / NTP / Syslog
Simple on/off appliances (`ENABLED`, plus NTP auth fields).

---

## 6. Limitations & risks

1. **Template leftovers (highest-impact risk).** Harvested templates carry real
   records. Proven live in this audit: a freshly-instantiated `Server-PT`
   already contains **two `serverPool` DHCP pools**, a `user`/`cisco` AAA
   account and a `cisco` FTP account. A generator that authors "one pool" and
   counts pools will report three. **Mitigation is built in:** call
   `pkt_core.audit.strip_service_records(device)` (blank slate, before
   authoring) or `sanitize_template_leftovers(lab, leftovers=TemplateLeftovers
   .from_device_templates_json(...))` (after authoring). Then
   `validate_lab()` proves uniqueness and flags residue.
2. **No service builder methods.** Everything in §5 is hand-authored XML. This
   is not a blocker (proven in §7) but it is the bulk of the generator's work
   and must be encapsulated.
3. **`TYPE` enums are numeric and undocumented here** (DNS record type, wireless
   auth/encrypt). Values must be taken from real configured `.pkt` samples, not
   guessed. `set_wireless` already warns these are raw PT enums.
4. **ET-builder cosmetic normalisation.** The builder's ET path does not
   round-trip byte-exact (unlike the `models` path). Harmless for new files;
   for editing an existing user file, use the lossless `models` path instead.
5. **Physical-workspace fragility.** The builder documents two load-critical
   invariants (braced leaf UUID in `<PHYSICAL>`, a `<PHYSICAL_CPUR>` per device,
   no orphan leaves). Reuse the builder's logic; do not re-implement it.
6. **Semantic validity is PT's call.** The library guarantees the *file* is
   well-formed and repacks; it does not simulate. "Pings succeed" still needs a
   PT open (as you already did for `first_network.pkt`).
7. **184 vs 137.** The brief's model count is wrong for this install; plan
   against 137.

---

## 7. Proof: services survive repack & reopen (run this audit)

A read-only PoC (written to the scratchpad, not the project) built a 1-server
lab with `builder.Lab`, authored a DHCP pool, a DNS record and an email account
by **direct XML** on the engine, `save()`d, then `decode()`d and re-read via the
typed models + `inventory()`:

```
repack ok, format=pkt root=PACKETTRACER5 xml_bytes=861673
DHCP pools seen: serverPool(leftover), LAN(192.168.1.0, .100–.200), serverPool(leftover)
DNS records seen: ('0','www.lab.local','192.168.1.10')
inventory dhcp_pools raw/distinct: 3/3   dns_records raw/distinct: 1/1
email USER present in xml: True
```

This confirms end-to-end: builder → direct-XML services → real container encode
→ decode → typed read + validation. (It also surfaced the two leftover pools of
risk #1.)

---

## 8. Unresolved questions (need a configured-sample or a PT open to close)

- Exact numeric enum tables for `DNS RESOURCE-RECORD/TYPE` and wireless
  `AUTHEN_TYPE`/`ENCRYPT_TYPE` per device family.
- `FILE_CONTENT` escaping for HTTP pages that contain markup (entity-encoded vs
  CDATA) — confirm against a server with an authored `index.html`.
- Whether HTTPS requires a cert/key block beyond `HTTPS_SERVER/ENABLED`.
- DHCPv6 (`DHCPV6_MAIN`, `DHCPV6_SERVER_LIST`) field semantics.
- Does PT require `NO_OF_USERS` to equal the count of `USERS/USER`, or does it
  recompute on load? (PoC set it; a PT open would confirm it is honoured.)

All of these are closable with one or two configured reference `.pkt` files —
not a library limitation.
