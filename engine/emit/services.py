"""Server-side service authors (direct XML on the device ``<ENGINE>``).

No `pkt_core.builder` method configures DHCP/DNS/HTTP/SMTP/POP3, so these author
the records into the exact XML locations the audit established
(`generated/service_capabilities.json`). Each takes the builder `Lab` and the
device id returned by `add_device`, and mutates the live ElementTree engine in
place. Call `sanitize_server` first to strip the template's leftover records.

All paths and field orders here are evidence-backed; nothing is invented.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterable, Sequence


def engine_of(lab, dev_id: str) -> ET.Element:
    """The live ElementTree ``<ENGINE>`` of a device added via the builder."""
    el = lab._els[dev_id]
    eng = el.find("ENGINE")
    if eng is None:  # pragma: no cover - every harvested device has one
        raise ValueError(f"{dev_id}: device has no <ENGINE>")
    return eng


def set_version(lab, version: str) -> None:
    """Stamp the document <VERSION> so the file opens on a given PT build.

    Packet Tracer refuses a file whose version is newer than itself. The library
    seed is stamped 9.0.1.0858; set this to the target PT's build (Help → About)
    — equal or older always opens — before ``lab.save(...)``.
    """
    ver = lab.base.find("VERSION")
    if ver is None:
        ver = ET.SubElement(lab.base, "VERSION")
    ver.text = version


def _set(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Set (or create) a direct child's text."""
    child = parent.find(tag)
    if child is None:
        child = ET.SubElement(parent, tag)
    child.text = text
    return child


# Leaf record lists a harvested Server-PT template carries and we don't want in
# the finished lab. Only the *records* are cleared; the parent containers and the
# DHCP ASSOCIATED_PORT bindings are LEFT IN PLACE — Packet Tracer expects that
# structure, and deleting a binding makes PT reject the file as "not compatible".
_LEFTOVER_RECORDS: tuple[tuple[str, str], ...] = (
    ("POOLS", "POOL"),                 # leftover DHCP pools
    ("USERS", "USER"),                 # leftover AAA users
    ("ACS_CLIENTS", "CLIENT"),         # leftover AAA clients
    ("USER_ACCOUNT_MNGR", "ACCOUNT"),  # leftover FTP accounts
    ("DHCP_POOL_LEASES", "*"),         # runtime state
    ("DHCP_RESERVATIONS", "*"),        # runtime state
)


def clean_services(lab, dev_id: str) -> str:
    """Clear the template's leftover service *records*, preserving all structure.

    This is the safe replacement for a blank-slate strip: it empties the record
    lists (so no stray `serverPool`/`cisco`/`user` entries survive) but never
    removes the containers or the ``ASSOCIATED_PORT`` DHCP bindings, so the file
    still opens in Packet Tracer.
    """
    eng = engine_of(lab, dev_id)
    removed = 0
    for container_tag, record_tag in _LEFTOVER_RECORDS:
        for container in eng.iter(container_tag):
            victims = (list(container) if record_tag == "*"
                       else container.findall(record_tag))
            for v in victims:
                container.remove(v)
                removed += 1
    return "cleared %d leftover record(s)" % removed


# --------------------------------------------------------------------------- #
# DHCP  (Server-PT family: DHCP_SERVERS/ASSOCIATED_PORTS/ASSOCIATED_PORT/...)
# --------------------------------------------------------------------------- #
def author_dhcp(
    lab,
    dev_id: str,
    *,
    pool_name: str,
    network: str,
    mask: str,
    start_ip: str,
    end_ip: str,
    dns_server: str = "0.0.0.0",
    default_router: str = "0.0.0.0",
    max_users: int = 100,
    port: str = "FastEthernet0",
) -> None:
    """Author one DHCP pool bound to the server's NIC and enable the service."""
    eng = engine_of(lab, dev_id)
    servers = eng.find("DHCP_SERVERS")
    if servers is None:
        servers = ET.SubElement(eng, "DHCP_SERVERS")
    aps = servers.find("ASSOCIATED_PORTS")
    if aps is None:
        aps = ET.SubElement(servers, "ASSOCIATED_PORTS")

    # Reuse the template's existing binding for this NIC (PT ships one per port);
    # never delete bindings — that is what makes PT reject the file. Prefer the
    # binding already named for our NIC, else the first, else synthesise one.
    ap = None
    for cand in aps.findall("ASSOCIATED_PORT"):
        if (cand.findtext("NAME") or "") == port:
            ap = cand
            break
    if ap is None:
        ap = aps.find("ASSOCIATED_PORT")
    if ap is None:
        ap = ET.SubElement(aps, "ASSOCIATED_PORT")
        _set(ap, "NAME", port)
        ET.SubElement(ap, "DHCP_SERVER")
    _set(ap, "NAME", port)

    srv = ap.find("DHCP_SERVER")
    if srv is None:
        srv = ET.SubElement(ap, "DHCP_SERVER")
    _set(srv, "ENABLED", "1")
    pools = srv.find("POOLS")
    if pools is None:
        pools = ET.SubElement(srv, "POOLS")
    for leftover in pools.findall("POOL"):   # clear leftover pools only
        pools.remove(leftover)
    pool = ET.SubElement(pools, "POOL")
    for tag, val in (
        ("NAME", pool_name),
        ("NETWORK", network),
        ("MASK", mask),
        ("DEFAULT_ROUTER", default_router),
        ("TFTP_ADDRESS", "0.0.0.0"),
        ("START_IP", start_ip),
        ("END_IP", end_ip),
        ("DNS_SERVER", dns_server),
        ("MAX_USERS", str(max_users)),
        ("DOMAIN_NAME", ""),
    ):
        ET.SubElement(pool, tag).text = val
    if srv.find("DHCP_RESERVATIONS") is None:
        ET.SubElement(srv, "DHCP_RESERVATIONS")


# --------------------------------------------------------------------------- #
# DNS  (DNS_SERVER/NAMESERVER-DATABASE/RESOURCE-RECORD)
# --------------------------------------------------------------------------- #
# PT's DNS record TYPE is a short string enum, confirmed from a real save:
# an A record is "A-REC" (NOT the numeric "0" we first guessed, which PT rejected).
A_RECORD = "A-REC"


def author_dns(
    lab,
    dev_id: str,
    records: Sequence[tuple[str, str]],
    *,
    record_type: str = A_RECORD,
    ttl: str = "86400",
) -> None:
    """Enable DNS and author ``(name, ipaddress)`` A records.

    Structure verified from a real Packet Tracer save (SAMPLE.pkt):
    ``DNS_SERVER/NAMESERVER-DATABASE/RESOURCE-RECORD`` with children
    ``TYPE`` (``A-REC``), ``NAME``, ``TTL``, ``IPADDRESS``.
    """
    eng = engine_of(lab, dev_id)
    dns = eng.find("DNS_SERVER")
    if dns is None:
        dns = ET.SubElement(eng, "DNS_SERVER")
    _set(dns, "ENABLED", "1")
    db = dns.find("NAMESERVER-DATABASE")
    if db is None:
        db = ET.SubElement(dns, "NAMESERVER-DATABASE")
    for rr in db.findall("RESOURCE-RECORD"):   # clear any leftover records
        db.remove(rr)
    for name, ip in records:
        rr = ET.SubElement(db, "RESOURCE-RECORD")
        ET.SubElement(rr, "TYPE").text = record_type
        ET.SubElement(rr, "NAME").text = name
        ET.SubElement(rr, "TTL").text = ttl
        ET.SubElement(rr, "IPADDRESS").text = ip


# --------------------------------------------------------------------------- #
# HTTP  (page body lives in the 'http:' filesystem, inside FILE_CONTENT/TEXT)
# --------------------------------------------------------------------------- #
def author_http(lab, dev_id: str, html: str = "", *, filename: str = "index.html") -> int:
    """Enable HTTP/HTTPS and (optionally) set a served page's body.

    Page storage verified from a real save: the body is the text of the ``TEXT``
    child of a page file's ``FILE_CONTENT`` — editing that existing element is
    safe. Server-PT ships two ``FILE_MANAGER`` blocks, so the page is written
    into every ``http:`` copy. Pass ``html=""`` to keep the default page.
    Returns the number of page nodes updated.
    """
    eng = engine_of(lab, dev_id)
    http = eng.find("HTTP_SERVER")
    if http is None:
        http = ET.SubElement(eng, "HTTP_SERVER")
    _set(http, "ENABLED", "1")
    https = eng.find("HTTPS_SERVER")
    if https is not None:
        _set(https, "ENABLED", "1")
    if not html:
        return 0

    updated = 0
    for fm in eng.iter("FILE_MANAGER"):
        for f in fm.iter("FILE"):
            if (f.findtext("NAME") or "") != filename:
                continue
            fc = f.find("FILE_CONTENT")
            if fc is None:
                continue
            text = fc.find("TEXT")
            if text is None:
                text = ET.SubElement(fc, "TEXT")
            text.text = html          # ElementTree escapes the markup on write
            updated += 1
    return updated


# --------------------------------------------------------------------------- #
# Email  (EMAIL_SERVER: SMTP + POP3, with USERS/USER accounts)
# --------------------------------------------------------------------------- #
import re as _re


def author_email(
    lab,
    dev_id: str,
    *,
    domain: str,
    accounts: Iterable[tuple[str, str]] = (),
) -> None:
    """Enable SMTP+POP3, set the domain and author the user accounts.

    Structure verified from a real Packet Tracer save (SAMPLE.pkt): accounts are
    NOT nested in a ``USERS`` block (that invented structure is what PT rejected).
    They are flat, index-suffixed siblings directly under ``EMAIL_SERVER``::

        <NO_OF_USERS>2</NO_OF_USERS>
        <USER0>alice</USER0><PASSWORD0>pw</PASSWORD0><NO_OF_MAILS0>0</NO_OF_MAILS0>
        <USER1>bob</USER1>  <PASSWORD1>pw</PASSWORD1> <NO_OF_MAILS1>0</NO_OF_MAILS1>
    """
    eng = engine_of(lab, dev_id)
    em = eng.find("EMAIL_SERVER")
    if em is None:
        em = ET.SubElement(eng, "EMAIL_SERVER")
    _set(em, "SMTP_ENABLED", "1")
    _set(em, "POP3_ENABLED", "1")
    _set(em, "SMTP_DOMAIN", domain)

    # drop any existing indexed account elements, then rewrite them
    for child in list(em):
        if _re.fullmatch(r"(USER|PASSWORD|NO_OF_MAILS)\d+", child.tag):
            em.remove(child)
    accts = list(accounts)
    _set(em, "NO_OF_USERS", str(len(accts)))
    for i, (user, password) in enumerate(accts):
        ET.SubElement(em, "USER%d" % i).text = user
        ET.SubElement(em, "PASSWORD%d" % i).text = password
        ET.SubElement(em, "NO_OF_MAILS%d" % i).text = "0"
