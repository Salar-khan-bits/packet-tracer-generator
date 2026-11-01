# `pkt_core` 0.4.1 — API Reference (generator-facing)

Signatures and source locations below are machine-extracted
(`engine/discovery/package_inspector.py`; full dump in
`generated/api_surface.json`). Pydantic-inherited noise
(`copy/dict/json/model_*`) on the model classes is omitted here. Paths are
relative to `site-packages/`.

---

## 1. Container codec — `.pkt`/`.pka` ⇄ XML  (`pkt_core`, from `codec/container.py`)

```python
decode(path, fmt=None, *, verify_tag=True) -> Container          # read file
decode_bytes(raw, fmt=None, *, verify_tag=True) -> Container     # read bytes
encode(path, xml: bytes, fmt="pkt", *, level=-1) -> None         # write file
encode_bytes(xml: bytes, fmt="pkt", *, level=-1) -> bytes        # write bytes
detect_format(raw, candidates=None) -> str                       # AEAD-oracle detection
root_tag(xml: bytes) -> str                                      # cheap root read
qcompress(data, level=-1) / quncompress(payload)                 # Qt framing
```

`Container` (frozen): `.xml: bytes`, `.format_name`, `.spec: FormatSpec`,
`.raw`, `.root_tag`, `.is_activity`.
`FORMATS: {name -> FormatSpec}` — use `"pkt"` for `.pkt`/`.pka`.

> Round-trip contract: `encode(decode(f)) == f` (byte-exact). Deterministic:
> same XML → same bytes.

---

## 2. Authoring — `pkt_core.builder.lab.Lab`  (`builder/lab.py:615`)

Re-exported as `pkt_core.Lab`. ElementTree-based; the verified way to build a
new lab.

```python
Lab(seed=None, models=None, modules=None)        # None => bundled seed + 137 templates

add_device(model, name, x=100, y=100, power=True,
           ios_config=None, pc_ip=None, install=None,
           bay=0, on_name_conflict="raise") -> dev_id:str   # ":615"
link(a_id, a_port, b_id, b_port, kind="copper",
     dce=None, dce_port=None, clock=128000)                 # copper | serial
install_module(dev_id, module_model, bay=None, *, slot=None)
set_wireless(dev_id, ssid=None, auth_type=None, encrypt_type=None,
             password=None, userid=None, channel=None, radio_band=None)
set_os(dev_id, image=None, file_name=None)
set_config_register(dev_id, value)
device_names() -> list[str]
prune_seed_devices() -> list[str]        # alias: drop_seed_devices / drop_initial
initial_id(index=0) -> dev_id
save(path)                               # ET.tostring -> encode(..., "pkt")
```

- `add_device` returns a `save-ref-id:` string — the handle for `link`,
  `install_module`, etc. Internally the live `ElementTree` element is
  `lab._els[dev_id]` (used for direct-XML service authoring, see §5).
- `pc_ip=(ip, mask, gw)` sets NIC `<IP>/<SUBNET>/<PORT_GATEWAY>` **and**
  `<ENGINE><GATEWAY>`.
- `Layout` (`builder/lab.py:420`) — deterministic label-aware packer:
  `place(name, model, group="")`, `reserve(...)`, `anchor(group, x, y)`;
  helpers `kind_for_model(model)`, `parse_devices(xml)`, `load_templates(path)`,
  `load_tier_map(path)`.

---

## 3. Lossless read/modify — `pkt_core.models`

Views over the byte-preserving tree; untouched bytes re-emit verbatim. Use for
**editing existing files** and for **reading back** anything the builder wrote.

### `models.Lab`  (`models/lab.py:147`)
```python
Lab.from_bytes(xml: bytes) -> Lab
.devices -> list[Device]      .links -> list[Link]      .network -> Network|None
.version  .is_activity  .options  .clusters  .canvas_shapes
.device_named(name) -> Device|None
.to_xml() -> bytes            # serialise (byte-exact if untouched)
.summary() -> dict
# activities: .activity_sections .scoring_tree .activity_password .set_activity_password(v)
```

### `models.Device`  (`models/network.py:179`)
```python
.kind .model .name .description .powered .power_state .position .cluster_id .dev_addr
.engine -> XmlElement|None            # the mutation anchor for services
.ports -> list[Port]   .modules -> list[Module]   .workspace
.services -> DeviceServices|None      # typed service read views
.port_configs -> list[PortConfig]     .wireless -> WirelessConfig|None
.files -> list[FileEntry]             .details -> DeviceDetails|None
.set_name(v)   .set_position(x, y)
```

### `models.services`  (`models/services.py`)
```python
DeviceServices: .aaa_clients .aaa_users .dhcp_pools .dns_records .ftp_accounts
DhcpPool:   .name .network .mask .default_router .start_ip .end_ip .dns_server
            .max_users .domain_name .lease_time .leases .identity .scope
DnsRecord:  .record_type .name .ttl .ip_address .identity .zone_key
FtpAccount: .username .password .permissions .identity
AaaUser:    .name .password .description .identity
AaaClient:  .host_ip .key .description .server_type .identity
# identity/record field tables (ground truth for authoring):
IDENTITY_FIELDS = {dhcp_pools:(NAME,NETWORK,MASK), dns_records:(TYPE,NAME,IPADDRESS),
                   ftp_accounts:(USERNAME,), aaa_users:(NAME,), aaa_clients:(HOST_IP,)}
```
These views are **read-only** (properties). To *write*, mutate the underlying
`XmlElement` (see §5) or author on the ET engine in the builder.

### `models.schema`  (`models/schema.py`)
`PortConfig` (IPv4/IPv6/DHCP/VLAN), `WirelessConfig`, `DeviceDetails`,
`FileEntry` (`.name .path .content:bytes` — **HTTP page bodies**), `ScoringNode`,
`EnvironmentOption`, `CanvasShape`, `ActivitySection`.

---

## 4. Lossless XML primitives — `pkt_core.xml`  (`xml/nodes.py`, `xml/writer.py`)

```python
parse_xml_bytes(data) -> XmlDocument       # lazy; .root, .to_bytes()
XmlElement: .find(name) .find_all(name) .iter_elements() .get(attr) .set(attr,v)
            .append(child) .remove(child) .text .to_bytes()  (mark ._dirty on edit)
writer.element(name, **attrs) -> XmlElement      # synthesise a new (dirty) element
writer.text(data) -> XmlText
```
`PktNode._set_text(name, value)` (base) creates/overwrites a child's text and
marks the subtree dirty — the clean primitive for editing a known field.

---

## 5. Services, validation & sanitising — `pkt_core.audit`  (`audit.py`)

```python
inventory(lab, *, leftovers=None) -> ServiceInventory       # raw+distinct counts/family
validate_lab(lab, *, leftovers=None) -> ValidationReport    # proves uniqueness; .ok, .findings
strip_service_records(target) -> SanitizeReport             # BLANK SLATE: remove all service records
sanitize_template_leftovers(target, *, leftovers=None)      # remove only template residue
sanitize_engine(engine, *, model="", leftovers=None)        # one <ENGINE>, either XML tree
TemplateLeftovers.from_device_templates_json(path)          # fingerprint the shipped templates
SERVICE_FAMILIES  # aaa_clients, aaa_users, dhcp_pools, dns_records, ftp_accounts
```
Works on **both** XML trees (ElementTree builder docs *and* lossless model docs)
via `as_view()`. Validation codes: `duplicate-dhcp-pool` / `-name` / `-scope`,
`duplicate-dns-record`, `duplicate-aaa-client` / `-user`, `duplicate-ftp-account`,
`template-leftovers`, `duplicate-device-name`, `duplicate-end-device-ip` (warn).

---

## 6. Other

- `pkt_core.export`: `to_graphviz(lab)`, `to_netbox(lab)`, `to_containerlab(lab)`,
  `export(lab, fmt)` (`export.py`).
- `pkt_core.diff`: `diff_labs(a, b) -> LabDiff` — semantic (by name/endpoint).
- `pkt_core.resources`: `load_device_templates() -> (models, modules)`,
  `load_network_seed() -> bytes`, `device_templates_path()`.
- CLI (`pkt`): `info | unpack | pack | diff | export | audit` (`cli/main.py`).

---

## 7. Minimal end-to-end (verified in this audit)

```python
from pkt_core.builder.lab import Lab
import xml.etree.ElementTree as ET

lab = Lab(); lab.prune_seed_devices()
sid = lab.add_device("Server-PT", "SRV", x=200, y=200,
                     pc_ip=("192.168.1.10", "255.255.255.0", "192.168.1.1"))

eng = lab._els[sid].find("ENGINE")                 # direct-XML service authoring
dhcp = eng.find("DHCP_SERVERS/ASSOCIATED_PORTS/ASSOCIATED_PORT/DHCP_SERVER")
dhcp.find("ENABLED").text = "1"
pool = ET.SubElement(dhcp.find("POOLS"), "POOL")
for t, v in [("NAME","LAN"),("NETWORK","192.168.1.0"),("MASK","255.255.255.0"),
             ("DEFAULT_ROUTER","192.168.1.1"),("START_IP","192.168.1.100"),
             ("END_IP","192.168.1.200"),("DNS_SERVER","192.168.1.10"),("MAX_USERS","100")]:
    ET.SubElement(pool, t).text = v

lab.save("out.pkt")                                 # encode -> real .pkt

# read back / validate
from pkt_core import decode
from pkt_core.models import Lab as MLab
from pkt_core.audit import validate_lab
ml = MLab.from_bytes(decode("out.pkt").xml)
print(validate_lab(ml).ok)                          # True once leftovers are stripped
```
