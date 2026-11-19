#!/usr/bin/env python3
"""Grade a class of Packet Tracer submissions against an answer key.

Reads the ``answer_key.json`` written by ``classroom.py`` and checks each
student's ``.pkt`` against the values they were supposed to configure -- DHCP
pool range + DNS handed to clients, and the DNS A-records on the server. It does
this by DECODING the file (no Packet Tracer needed), so one instructor can grade
a whole class in seconds.

    # grade the generated reference labs themselves (a self-check)
    python grade.py generated/classroom/example_lan/answer_key.json

    # grade real submissions: a folder with <student>.pkt (or <student>/*.pkt)
    python grade.py generated/classroom/example_lan/answer_key.json ^
        --submissions path/to/collected

Output: a per-student score to the console and a ``grades.csv`` beside the
answer key (or in --submissions).

Honest scope: this checks what the student CONFIGURED (read from the file). It is
the fast, scalable layer. Proving the network actually BEHAVES (DHCP leases, DNS
resolves, pings) is the live layer -- agent/walkthrough.py -- which drives PT.
The two together are the full story; this one answers "did they set it up right".
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from pkt_core.builder.lab import decode


# --- expected values, parsed from an answer_key.json row -------------------- #
def parse_expected(row: dict) -> dict:
    start = end = ""
    pool = row.get("dhcp_pool", "")
    if " - " in pool:
        start, end = (s.strip() for s in pool.split(" - ", 1))
    dns = set()
    for part in (row.get("dns", "") or "").split(";"):
        part = part.strip()
        if " -> " in part:
            name, ip = (s.strip() for s in part.split(" -> ", 1))
            dns.add((name, ip))
    return {
        "start": start,
        "end": end,
        "client_dns": row.get("server_ip", ""),   # DHCP hands the server as DNS
        "dns": dns,
    }


# --- actual values, read from the student's .pkt ---------------------------- #
def read_actual(pkt_path: Path) -> dict:
    root = ET.fromstring(decode(str(pkt_path)).xml)

    pools = root.findall(".//DHCP_SERVER/POOLS/POOL")
    pool = None
    for p in pools:                      # prefer the primary 'serverPool'
        if (p.findtext("NAME") or "") == "serverPool":
            pool = p
            break
    if pool is None and pools:
        pool = pools[0]

    dns = set()
    for rr in root.findall(".//DNS_SERVER/NAMESERVER-DATABASE/RESOURCE-RECORD"):
        name, ip = rr.findtext("NAME"), rr.findtext("IPADDRESS")
        if name and ip:
            dns.add((name, ip))

    return {
        "pool_name": (pool.findtext("NAME") if pool is not None else None),
        "start": (pool.findtext("START_IP") if pool is not None else None),
        "end": (pool.findtext("END_IP") if pool is not None else None),
        "client_dns": (pool.findtext("DNS_SERVER") if pool is not None else None),
        "dns": dns,
    }


def grade_one(expected: dict, actual: dict) -> list[tuple[str, bool, str]]:
    """Return a list of (check_name, passed, detail)."""
    checks: list[tuple[str, bool, str]] = []

    ok = actual["pool_name"] == "serverPool"
    checks.append(("DHCP pool is the primary 'serverPool'", ok,
                   "got %r (PT serves a default .0 pool otherwise)"
                   % actual["pool_name"] if not ok else ""))

    ok = actual["start"] == expected["start"]
    checks.append(("DHCP start IP", ok,
                   "expected %s, got %s" % (expected["start"], actual["start"])
                   if not ok else ""))

    ok = actual["end"] == expected["end"]
    checks.append(("DHCP end IP", ok,
                   "expected %s, got %s" % (expected["end"], actual["end"])
                   if not ok else ""))

    ok = bool(expected["client_dns"]) and actual["client_dns"] == expected["client_dns"]
    checks.append(("DHCP hands out DNS = server", ok,
                   "expected %s, got %s" % (expected["client_dns"], actual["client_dns"])
                   if not ok else ""))

    if expected["dns"]:
        missing = expected["dns"] - actual["dns"]
        ok = not missing
        checks.append(("DNS A-records present", ok,
                       "missing " + ", ".join("%s->%s" % m for m in sorted(missing))
                       if not ok else ""))
    return checks


def find_submission(row: dict, answer_dir: Path, sub_dir: Path | None) -> Path | None:
    student = row["student"]
    if sub_dir is None:
        p = answer_dir / row.get("pkt", "")        # the generated reference
        return p if p.exists() else None
    for cand in (sub_dir / ("%s.pkt" % student),
                 sub_dir / student / ("%s.pkt" % student)):
        if cand.exists():
            return cand
    hits = list((sub_dir / student).glob("*.pkt")) if (sub_dir / student).is_dir() else []
    return hits[0] if hits else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Grade a class of PT submissions against an answer key.")
    ap.add_argument("answer_key", type=Path, help="answer_key.json from classroom.py")
    ap.add_argument("--submissions", type=Path, default=None,
                    help="folder of collected submissions (<student>.pkt or "
                         "<student>/*.pkt); omit to grade the generated labs")
    ap.add_argument("--pass-mark", type=float, default=1.0,
                    help="fraction of checks to count as a pass (default 1.0 = all)")
    args = ap.parse_args(argv)

    rows = json.loads(args.answer_key.read_text(encoding="utf-8"))
    answer_dir = args.answer_key.parent
    out_dir = args.submissions or answer_dir

    print("=== Grading %d submission(s) ===" % len(rows))
    report: list[dict] = []
    passed_students = 0
    for row in rows:
        student = row["student"]
        sub = find_submission(row, answer_dir, args.submissions)
        if sub is None:
            print("[MISS] %-12s no submission found" % student)
            report.append({"student": student, "score": "", "passed": False,
                           "detail": "no submission found"})
            continue
        try:
            checks = grade_one(parse_expected(row), read_actual(sub))
        except Exception as e:
            print("[ERR ] %-12s %s" % (student, e))
            report.append({"student": student, "score": "", "passed": False,
                           "detail": "unreadable: %s" % e})
            continue

        n_ok = sum(1 for _, ok, _ in checks if ok)
        n = len(checks)
        frac = n_ok / n if n else 0.0
        is_pass = frac >= args.pass_mark
        passed_students += int(is_pass)
        fails = "; ".join("%s (%s)" % (name, detail)
                          for name, ok, detail in checks if not ok)
        tag = "PASS" if is_pass else "FAIL"
        print("[%s] %-12s %d/%d%s" % (tag, student, n_ok, n,
              ("  -- " + fails) if fails else ""))
        report.append({"student": student, "score": "%d/%d" % (n_ok, n),
                       "passed": is_pass, "detail": fails})

    csv_path = out_dir / "grades.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["student", "score", "passed", "detail"])
        w.writeheader()
        w.writerows(report)
    print("\ngrades: %s" % csv_path)
    print("=== %d/%d passed ===" % (passed_students, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
