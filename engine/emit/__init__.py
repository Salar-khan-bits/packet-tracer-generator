"""Emission layer: turn a built topology into a configured Packet Tracer lab.

Thin, verified authors on top of ``pkt_core.builder.lab.Lab``:

* :mod:`services` — server-side DHCP/DNS/HTTP/SMTP+POP3 authored directly on the
  device ``<ENGINE>`` (no builder method exists for these; see the audit).
* :mod:`clients`  — end-device IP mode (static/DHCP), DNS client and the
  pre-filled mail client.

Every author operates on the builder's live ElementTree engine
(``lab._els[dev_id]``) and is proven to round-trip through ``encode()``/``decode()``.
"""

from __future__ import annotations

__all__ = ["services", "clients"]
