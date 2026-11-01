"""Read-only capability-discovery tools for the pkt_core / Packet Tracer stack.

These modules inspect the *installed* ``pkt_core`` package and its bundled data
(``device_templates.json``, ``network_seed.xml``) and emit focused,
machine-readable reports. Nothing here modifies the package, the environment, or
any existing project artifact.

Modules
-------
* :mod:`package_inspector` — public API surface (classes, functions, signatures).
* :mod:`model_inspector`   — the device-template catalog (models, ports, modules).
* :mod:`service_inspector` — the service XML structures under ``<ENGINE>``.

Run :mod:`engine.discovery.run_all` (``python -m engine.discovery.run_all``) to
regenerate ``generated/device_catalog.json`` and
``generated/service_capabilities.json``.
"""

from __future__ import annotations

__all__ = ["package_inspector", "model_inspector", "service_inspector"]
