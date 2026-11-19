"""Author a Packet Tracer **Activity Wizard** file (.pka) that wraps a generated
network with a step-by-step instructions guide.

Tier 1 (this module): a *guide* activity.  The learner opens ONE ``.pka`` and
sees the full generated network PLUS an instructions pane that walks them
through it, page by page.  Grading is left as the template's own tree (Tier 1
does not score the learner); Tier 2 will author real assessment checks.

Method = **template transplant** (the only safe way, see memory
``pka-activity-schema``): carry a real ``.pka`` shell authored by Packet Tracer
itself, swap its embedded network snapshots for our generated network, and
rewrite the instruction pages.  We never invent Activity-Wizard XML from
scratch, so Packet Tracer keeps accepting the file.

A ``.pka`` is the same encrypted/zlib container as a ``.pkt`` (``pkt_core``
reads and writes both); only the XML root differs
(``PACKETTRACER5_ACTIVITY`` vs ``PACKETTRACER5``).
"""
from __future__ import annotations

import copy
import html as _html
import xml.etree.ElementTree as ET
from pathlib import Path

from pkt_core.builder.lab import decode, encode

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[2]
DEFAULT_TEMPLATE = _ROOT / "templates" / "activity_template.pka"


def _network_root(pkt_path: str | Path) -> ET.Element:
    """Return the ``<PACKETTRACER5>`` root element of a generated network file."""
    container = decode(str(pkt_path))
    root = ET.fromstring(container.xml)
    if root.tag != "PACKETTRACER5":
        raise ValueError(
            "expected a plain network .pkt (root PACKETTRACER5), got %r" % root.tag
        )
    return root


def build_activity_xml(
    network_root: ET.Element,
    template_xml: bytes,
    pages: list[tuple[str, str]],
    *,
    version: str | None = None,
) -> bytes:
    """Transplant ``network_root`` + ``pages`` into an activity ``template_xml``.

    ``pages`` is a list of ``(title, html)`` instruction pages.  ``html`` may use
    the limited tag subset Packet Tracer's instructions support (``<b>``,
    ``<br>``, ``<ul>/<li>``, ``<font color=...>`` ...).
    """
    act = ET.fromstring(template_xml)
    if act.tag != "PACKETTRACER5_ACTIVITY":
        raise ValueError("template is not an activity (.pka): root %r" % act.tag)

    # 1) Replace every embedded network snapshot (base / initial / answer) with
    #    our generated network so the learner sees the full topology on open.
    blocks = act.findall("PACKETTRACER5")
    if not blocks:
        raise ValueError("activity template has no embedded PACKETTRACER5 network")
    for blk in blocks:
        idx = list(act).index(blk)
        clone = copy.deepcopy(network_root)
        clone.tail = blk.tail  # keep the template's indentation between siblings
        act.remove(blk)
        act.insert(idx, clone)

    # 2) Rewrite the instructions pages.
    instr = act.find("ACTIVITY/INSTRUCTIONS")
    if instr is None:
        raise ValueError("activity template has no ACTIVITY/INSTRUCTIONS node")
    instr.set("enable_tab", "true" if len(pages) > 1 else "false")
    instr.set("layout", "0")
    for pg in instr.findall("PAGE"):
        instr.remove(pg)
    for title, body in pages:
        pg = ET.SubElement(instr, "PAGE")
        pg.set("tabify", "0")
        pg.set("title", title)
        pg.set("translate", "true")
        pg.text = body  # ElementTree escapes <>&; PT unescapes back to HTML

    # 3) Stamp versions so the file opens on the target Packet Tracer build.
    if version:
        v = act.find("VERSION")
        if v is not None:
            v.text = version
        # each embedded network carries its own VERSION (already stamped by the
        # generator); stamp any that are newer than the target just in case.
        for pt5 in act.findall("PACKETTRACER5"):
            vv = pt5.find("VERSION")
            if vv is not None:
                vv.text = version

    return ET.tostring(act, encoding="utf-8", xml_declaration=False)


def author_activity(
    network_pkt: str | Path,
    out_pka: str | Path,
    pages: list[tuple[str, str]],
    *,
    template: str | Path | None = None,
    version: str | None = None,
) -> Path:
    """Build a guide ``.pka`` from a generated network ``.pkt`` and write it."""
    template = Path(template) if template else DEFAULT_TEMPLATE
    if not template.exists():
        raise FileNotFoundError("activity template not found: %s" % template)
    net = _network_root(network_pkt)
    # the template is itself an encrypted .pka container -> decode to get its XML
    template_xml = decode(str(template)).xml
    xml = build_activity_xml(net, template_xml, pages, version=version)
    out_pka = Path(out_pka)
    out_pka.parent.mkdir(parents=True, exist_ok=True)
    encode(str(out_pka), xml, "pkt")
    return out_pka
