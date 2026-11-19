#!/usr/bin/env python3
"""Build a whole class of UNIQUE labs from one spec, plus an answer key.

This is the v1 "lab factory" for instructors: give it one lab spec and a roster
(or just a count), and it produces one personalised, working ``.pkt`` per
student -- different subnet, email domain and layout each -- so no two answers
match. It also writes an **answer key** (CSV + JSON) listing the values each
student was given, so grading is a lookup, not a hunt.

    # 30 students named student01..student30
    python classroom.py specifications/example_lan.json --count 30

    # a real roster (one id per line; blank lines and #comments ignored)
    python classroom.py specifications/example_lan.json --roster class.txt

    # also build each student's guided Activity (.pka)
    python classroom.py specifications/example_lan.json --count 30 --guide

Options:
    --out DIR         output root (default generated/classroom/<name>)
    --guide           also emit a <name>_guide.pka per student
    --pt-version V    stamp <VERSION> for an older PT (e.g. 8.2.2.0400)
    --keep-ip         keep the task's exact subnet (don't vary per student)
    --keep-mail       keep the task's exact email domain
    --prefix P        name prefix for --count mode (default "student")

Each student's files land in ``<out>/<student>/``; the answer key is written to
``<out>/answer_key.csv`` and ``<out>/answer_key.json``.

Note: this builds and personalises the files -- it does not grade submissions.
Live grading (driving Packet Tracer to verify each one) is the companion step in
``agent/`` and arrives next; see agent/walkthrough.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from genlab import build, vary_spec
from validators.check import check_pkt

_ROOT = Path(__file__).resolve().parent


def read_roster(path: Path) -> list[str]:
    """One student id per line; blank lines and ``#`` comments ignored."""
    ids: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            ids.append(s)
    return ids


def lab_facts(spec: dict) -> dict[str, str]:
    """Pull the values an instructor needs to grade, from a (varied) spec."""
    services = spec.get("services") or {}
    devices = spec.get("devices", [])
    server = services.get("server")
    server_ip = next((d.get("ip", "") for d in devices
                      if d.get("name") == server), "")

    dhcp = services.get("dhcp") or {}
    pool = ("%s - %s" % (dhcp.get("start", ""), dhcp.get("end", ""))
            if dhcp else "")
    network = dhcp.get("network", "")

    dns = services.get("dns") or []
    dns_str = "; ".join("%s -> %s" % (r[0], r[1]) for r in dns)

    email = services.get("email") or {}
    domain = email.get("domain", "")
    accounts = "; ".join("%s@%s" % (a[0], domain)
                         for a in email.get("accounts", []))

    return {
        "server_ip": server_ip,
        "network": network,
        "dhcp_pool": pool,
        "dns": dns_str,
        "email_domain": domain,
        "accounts": accounts,
    }


def build_one(base_spec: dict, student: str, out_dir: Path, *,
              pt_version: str | None, keep_ip: bool, keep_mail: bool,
              guide: bool) -> dict:
    """Build one student's personalised lab (+ optional guide). Returns a row."""
    vary_ip = not keep_ip
    vary_mail = not keep_mail
    spec = base_spec
    changed: dict[str, str] = {}
    if vary_ip or vary_mail:
        spec, changed = vary_spec(base_spec, student,
                                  vary_ip=vary_ip, vary_mail=vary_mail)

    lab, name = build(spec, pt_version, seed=student)
    out_dir.mkdir(parents=True, exist_ok=True)
    pkt = out_dir / ("%s.pkt" % name)
    lab.save(str(pkt))
    report = check_pkt(str(pkt))

    if guide:
        # imported lazily so a plain build run doesn't need the activity layer
        from genactivity import walkthrough_pages
        from engine.emit.activity import author_activity
        pages = walkthrough_pages(spec)
        author_activity(pkt, out_dir / ("%s_guide.pka" % name), pages,
                        version=pt_version)

    facts = lab_facts(spec)
    row = {
        "student": student,
        "seed": student,
        "subnet": changed.get("subnet", facts["network"]),
        **facts,
        "pkt": str(pkt.relative_to(out_dir.parent)),
        "validate_ok": bool(report.get("validate_ok")),
    }
    return row


def write_answer_key(rows: list[dict], out_root: Path) -> tuple[Path, Path]:
    """Write answer_key.csv and answer_key.json; return their paths."""
    cols = ["student", "seed", "subnet", "server_ip", "dhcp_pool", "dns",
            "email_domain", "accounts", "pkt", "validate_ok"]
    csv_path = out_root / "answer_key.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    json_path = out_root / "answer_key.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return csv_path, json_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a class of unique labs from one spec, plus an answer key.")
    ap.add_argument("spec", type=Path, help="lab spec .json")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--roster", type=Path, help="file of student ids, one per line")
    g.add_argument("--count", type=int, help="generate N students (student01..)")
    ap.add_argument("--prefix", default="student",
                    help="name prefix for --count mode (default 'student')")
    ap.add_argument("--out", type=Path, default=None,
                    help="output root (default generated/classroom/<name>)")
    ap.add_argument("--guide", action="store_true",
                    help="also build each student's guided Activity (.pka)")
    ap.add_argument("--pt-version", default=os.environ.get("PT_VERSION"),
                    help="stamp <VERSION> for an older PT (e.g. 8.2.2.0400)")
    ap.add_argument("--keep-ip", action="store_true",
                    help="keep the task's exact subnet (don't vary per student)")
    ap.add_argument("--keep-mail", action="store_true",
                    help="keep the task's exact email domain")
    args = ap.parse_args(argv)

    base_spec = json.loads(args.spec.read_text(encoding="utf-8"))
    name = base_spec.get("name", "lab")

    if args.roster:
        students = read_roster(args.roster)
        if not students:
            print("roster is empty:", args.roster, file=sys.stderr)
            return 2
    else:
        if args.count < 1:
            print("--count must be >= 1", file=sys.stderr)
            return 2
        width = max(2, len(str(args.count)))
        students = ["%s%0*d" % (args.prefix, width, i)
                    for i in range(1, args.count + 1)]

    out_root = args.out or (_ROOT / "generated" / "classroom" / name)
    out_root.mkdir(parents=True, exist_ok=True)

    print("=== Classroom build: %s (%d students) ===" % (name, len(students)))
    rows: list[dict] = []
    failures = 0
    for i, student in enumerate(students, 1):
        try:
            row = build_one(base_spec, student, out_root / student,
                            pt_version=args.pt_version,
                            keep_ip=args.keep_ip, keep_mail=args.keep_mail,
                            guide=args.guide)
        except Exception as e:                      # one bad build never stops the class
            print("[FAIL] %-12s %s" % (student, e))
            failures += 1
            continue
        ok = "ok " if row["validate_ok"] else "BAD"
        extra = (" subnet=%s" % row["subnet"]) if row["subnet"] else ""
        print("[%s] %3d/%d %-12s%s" % (ok, i, len(students), student, extra))
        if not row["validate_ok"]:
            failures += 1
        rows.append(row)

    if rows:
        csv_path, json_path = write_answer_key(rows, out_root)
        print("\nanswer key:", csv_path)
        print("           ", json_path)
    print("=== %d built, %d problem(s); files under %s ==="
          % (len(rows), failures, out_root))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
