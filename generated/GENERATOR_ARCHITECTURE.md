# Generator Architecture Recommendation

**Goal:** generate complete, working Cisco Packet Tracer `.pkt` projects —
topology, device configs, IPv4, DHCP, DNS, HTTP, SMTP/POP3, FTP, AAA — from
natural-language descriptions, assignment PDFs, and structured specs.

**Grounding:** every recommendation below follows from the audit
(`TECHNICAL_AUDIT.md`) and the verified API (`library_api_reference.md`). The
one non-negotiable architectural fact: `pkt_core` gives a **verified builder**
for topology/config and a **lossless XML layer** for everything else; services
are **direct-XML**. Build around that split, do not fight it.

---

## 1. Layered pipeline

```
          ┌─────────────────────────────────────────────────────────────┐
  INPUT   │  NL text  │  assignment PDF  │  structured spec (YAML/JSON)   │
          └───────┬───────────────┬──────────────────┬──────────────────┘
                  ▼               ▼                  ▼
          ┌─────────────────────────────────────────────────────────────┐
  (A)     │  INTENT / PARSING  →  canonical NetworkSpec (validated model) │
          └───────────────────────────────┬─────────────────────────────┘
                                           ▼
          ┌─────────────────────────────────────────────────────────────┐
  (B)     │  PLANNING  (IP allocation, device selection, port mapping,   │
          │             service placement)  →  resolved BuildPlan        │
          └───────────────────────────────┬─────────────────────────────┘
                                           ▼
          ┌─────────────────────────────────────────────────────────────┐
  (C)     │  EMISSION                                                    │
          │   C1 topology/config  → pkt_core.builder.Lab (verified API)  │
          │   C2 sanitise leftovers → audit.strip_service_records        │
          │   C3 services (DHCP/DNS/HTTP/SMTP/POP3/FTP/AAA) → direct XML  │
          │   C4 lab.save() → real .pkt                                  │
          └───────────────────────────────┬─────────────────────────────┘
                                           ▼
          ┌─────────────────────────────────────────────────────────────┐
  (D)     │  VALIDATION  pkt_core.audit.validate_lab + decode round-trip │
          │              (+ optional Packet Tracer open smoke-test)      │
          └─────────────────────────────────────────────────────────────┘
```

**Why this shape:** (A) and (B) are the only parts that need interpretation;
keep them free of any `.pkt` knowledge so they are independently testable. (C)
is deterministic given a `BuildPlan`. (D) reuses the library's own guarantees.

---

## 2. The central abstraction: `NetworkSpec` (intermediate representation)

A single validated Pydantic model (pydantic is already a dependency) that every
input path produces and every emitter consumes. This decouples messy input from
deterministic output and is the surface your tests pin.

```
NetworkSpec
├── devices:  [DeviceSpec{ role, model?, name, config?, interfaces[] }]
├── links:    [LinkSpec{ a, a_port, b, b_port, kind }]
├── subnets:  [SubnetSpec{ cidr, gateway, vlan? }]
└── services: [ServiceSpec]  # DhcpSpec, DnsSpec, HttpSpec, EmailSpec, FtpSpec, AaaSpec
                             # each references a host device by name
```

`model?` optional: the planner resolves a role → concrete model against
`device_catalog.json` (e.g. role "router" → `2911`, "server" → `Server-PT`).

---

## 3. Module layout (extends the existing `engine/` + `validators/` dirs)

```
engine/
├── discovery/                 # DONE — read-only inspectors + JSON reports
├── spec/
│   ├── models.py              # NetworkSpec + sub-models (pydantic)
│   └── catalog.py             # role→model resolution over device_catalog.json
├── parse/
│   ├── structured.py          # YAML/JSON spec -> NetworkSpec
│   ├── nl.py                  # NL -> NetworkSpec (LLM w/ schema-constrained output)
│   └── pdf.py                 # PDF -> text -> nl.py
├── plan/
│   ├── ipam.py                # subnet/address allocation (deterministic)
│   ├── ports.py               # interface selection per device from catalog
│   └── placement.py           # wraps builder.Layout for canvas coords
├── emit/
│   ├── topology.py            # thin wrapper over pkt_core.builder.Lab
│   ├── services/              # ONE module per service, direct-XML authors
│   │   ├── _engine.py         #   shared: locate/ensure <ENGINE> subtrees
│   │   ├── dhcp.py  dns.py  http.py  email.py  ftp.py  aaa.py
│   └── build.py               # orchestrates C1–C4, returns .pkt path
└── __init__.py
validators/
└── check.py                   # wraps audit.validate_lab + decode round-trip
app/                           # CLI / API entry (no GUI yet, per brief)
```

Keep `discovery/` as the regenerable source of truth for the catalog; the
planner reads `generated/device_catalog.json`, not hard-coded model lists.

---

## 4. Service authoring layer (the real work) — design rules

Encapsulate every service behind a uniform author function operating on a
device's `<ENGINE>` element, so the emitter never sprinkles raw XML around:

```python
# emit/services/dhcp.py
def author(engine: ET.Element, spec: DhcpSpec) -> None: ...
```

Rules distilled from the audit:

1. **Sanitise first (mandatory).** Immediately after `add_device`, before
   authoring any service, run `audit.strip_service_records(device)` on service
   hosts — the `Server-PT` template ships leftover `serverPool` pools, a `user`
   AAA account and a `cisco` FTP account (proven in the audit). Skipping this
   corrupts every count and may produce conflicting records.
2. **Author with the exact field order** from `service_capabilities.json`
   (e.g. DHCP POOL = `NAME, NETWORK, MASK, DEFAULT_ROUTER, TFTP_ADDRESS,
   START_IP, END_IP, DNS_SERVER, MAX_USERS, DOMAIN_NAME, …`). Set the block's
   `ENABLED`/`SMTP_ENABLED`/`POP3_ENABLED` flag to `1`.
3. **Never author runtime state** (`DHCP_POOL_LEASES`, `DHCP_RESERVATIONS`).
4. **HTTP pages go in the filesystem**, not `<HTTP_SERVER>`: author into
   `FILE_MANAGER/.../FILE[NAME='http:']/FILES/FILE/FILE_CONTENT`.
5. **Keep enum values data-driven.** DNS `TYPE`, wireless `AUTHEN_TYPE`/
   `ENCRYPT_TYPE` are numeric PT enums — put them in a small lookup table seeded
   from real configured samples, never hard-code guesses.
6. **Clients reference servers by IP** (DNS server IP, mail server IP, DHCP
   `DNS_SERVER`), resolved by the IPAM planner — not by element references.

### Which XML tree to author on

- **New project (the common case):** author services on the builder's live ET
  engine (`lab._els[dev_id].find("ENGINE")`) *before* `save()`. One tree, one
  serialisation. Simplest; this is what the PoC used.
- **Editing a user's existing `.pkt`:** use the lossless `models` path
  (`Device.engine` → `XmlElement`), author via `writer.element()` /
  `_set_text()`, then `lab.to_xml()` → `encode()`. This preserves every
  untouched byte (GUI state, other services, activity data).

Expose both behind the same `emit/services/*` functions by having them accept an
`ElementView`-compatible engine — `audit.as_view()` already proves this works
across both trees.

---

## 5. Validation gate (D) — fail closed

```python
from pkt_core import decode, encode_bytes
from pkt_core.models import Lab as MLab
from pkt_core.audit import validate_lab, TemplateLeftovers

report = validate_lab(ml, leftovers=TemplateLeftovers.from_device_templates_json(path))
assert report.ok, report.summary()          # no duplicates, no leftovers
assert decode(out).xml == ...                # container round-trips
```

Every generated project must pass `validate_lab().ok` and a decode round-trip
before it is handed to the user. Optionally add a PT-open smoke test behind a
flag for high-value templates (PT availability is the user's environment).

---

## 6. Determinism & testing

- The builder is deterministic (`_det_uuid` + fixed container key/IV), so
  **golden-file tests** are viable: pin the decoded XML (not the encrypted
  bytes) of representative specs. Diff with `pkt_core.diff.diff_labs` to keep
  assertions semantic.
- Unit-test each `emit/services/*` author function against the typed read views
  (`DeviceServices`) + `inventory()` — exactly the PoC pattern.
- Parser layer (A) is tested independently by asserting the produced
  `NetworkSpec`, with no `.pkt` in the loop.

---

## 7. Phasing (see milestone in the final summary)

1. **IR + structured parser + topology/IP emitter + validation gate.** Produces
   working multi-device labs from a YAML spec. Reuses only verified builder API.
2. **Service authoring layer** (DHCP → DNS → HTTP → SMTP/POP3 → FTP → AAA), each
   with sanitise + validate. This is where direct-XML lives.
3. **NL and PDF front-ends** feeding the same IR (schema-constrained LLM
   extraction; PDF → text first).
4. **Enum/sample library** hardened from a handful of configured reference
   `.pkt` files to close the open enum questions.

---

## 8. What NOT to build

- Do not re-implement the container crypto/compression, the physical-workspace
  scaffolding, the layout packer, or template harvesting — all are solved in
  `pkt_core`; wrap them.
- Do not build a parallel data model of the whole document; the lossless tree +
  typed views already are the model. Touch only what you author.
- No GUI yet (per brief). Ship a CLI/API over the pipeline first.
