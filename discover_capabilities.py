
from __future__ import annotations

import ast
import importlib
import inspect
import json
import pkgutil
import re
import sys
import xml.etree.ElementTree as ET

from collections import Counter
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = PROJECT_DIR / "generated" / "capability_report.json"

SERVICE_KEYWORDS = [
    "DHCP", "DNS", "HTTP", "HTTPS", "SMTP", "POP3",
    "EMAIL", "FTP", "TFTP", "NTP", "SYSLOG", "SNMP",
    "VOIP", "WIRELESS", "IPV6", "ACL", "ROUTING",
]

# XML tags that commonly represent configurable services.
SERVICE_TAGS = {
    "DHCP", "DHCP_SERVER", "DHCP_SERVERS", "DHCP_CLIENT",
    "DNS", "DNS_SERVER", "DNS_CLIENT", "NAMESERVER-DATABASE",
    "HTTP_SERVER", "HTTPS_SERVER", "HTML_CODE", "HTML_TAB",
    "EMAIL_SERVER", "EMAIL_CLIENT", "SMTP_SERVER", "POP3_SERVER",
    "SMTP_ENABLED", "POP3_ENABLED", "SMTP_DOMAIN",
    "FTP_SERVER", "TFTP_SERVER", "NTP_SERVER", "SYSLOG_SERVER",
    "SNMP_MANAGER", "USERS", "USER", "POOLS", "POOL",
    "NETWORK", "MASK", "DEFAULT_ROUTER", "START_IP", "END_IP",
    "MAX_USERS", "FILESYSTEM", "FILES", "FILE", "FILE_CONTENT",
}

report = {
    "environment": {},
    "package": {},
    "lab_api": {},
    "models": {},
    "service_templates": {},
    "source_code_analysis": {},
    "findings": [],
}


def safe_signature(obj):
    try:
        return str(inspect.signature(obj))
    except Exception:
        return None


def xml_element_summary(element, depth=0, max_depth=4):
    """Summarize XML without dumping huge embedded files."""
    if element is None:
        return None

    result = {
        "tag": element.tag,
        "attributes": dict(element.attrib),
        "text": (element.text or "").strip()[:160],
        "children": [],
    }

    if depth >= max_depth:
        result["children_truncated"] = len(list(element)) > 0
        return result

    for child in list(element):
        result["children"].append(
            xml_element_summary(child, depth + 1, max_depth)
        )

    return result


def serialize_model(model):
    """Convert a model template to XML text where possible."""
    if isinstance(model, ET.Element):
        return ET.tostring(model, encoding="unicode")

    if isinstance(model, ET.ElementTree):
        return ET.tostring(model.getroot(), encoding="unicode")

    if isinstance(model, bytes):
        return model.decode("utf-8", errors="replace")

    if isinstance(model, str):
        return model

    return None


def inspect_models(lab):
    models_report = {}
    service_report = {}

    for model_name, model in lab.models.items():
        xml_text = serialize_model(model)

        entry = {
            "python_type": type(model).__name__,
            "xml_available": xml_text is not None,
        }

        if xml_text is not None:
            try:
                root = ET.fromstring(xml_text)

                tags = Counter(node.tag for node in root.iter())
                service_tags = {
                    tag: count
                    for tag, count in sorted(tags.items())
                    if tag.upper() in SERVICE_TAGS
                    or any(keyword in tag.upper()
                           for keyword in SERVICE_KEYWORDS)
                }

                entry["root_tag"] = root.tag
                entry["total_xml_elements"] = sum(tags.values())
                entry["top_level_tags"] = [
                    child.tag for child in list(root)
                ]
                entry["service_tags"] = service_tags

                if service_tags:
                    service_report[model_name] = {
                        "service_tag_counts": service_tags,
                        "service_structures": {},
                    }

                    for node in root.iter():
                        if (
                            node.tag in SERVICE_TAGS
                            or any(k in node.tag.upper()
                                   for k in SERVICE_KEYWORDS)
                        ):
                            service_report[model_name][
                                "service_structures"
                            ].setdefault(
                                node.tag,
                                xml_element_summary(node),
                            )

            except ET.ParseError as exc:
                entry["xml_parse_error"] = str(exc)

        models_report[model_name] = entry

    report["models"] = models_report
    report["service_templates"] = service_report


def inspect_lab_api(lab):
    lab_class = type(lab)

    methods = {}

    for name, member in inspect.getmembers(lab_class):
        if name.startswith("__"):
            continue

        if callable(member):
            methods[name] = {
                "signature": safe_signature(member),
                "docstring": inspect.getdoc(member),
            }

    report["lab_api"] = {
        "class": f"{lab_class.__module__}.{lab_class.__name__}",
        "constructor": safe_signature(lab_class),
        "methods": methods,
        "instance_attributes": sorted(
            name for name in vars(lab).keys()
        ),
    }


def inspect_package_source():
    import pkt_core

    package_dir = Path(pkt_core.__file__).resolve().parent

    source_files = list(package_dir.rglob("*.py"))
    source_report = {
        "package_directory": str(package_dir),
        "python_file_count": len(source_files),
        "files": [],
        "keyword_matches": {},
        "classes": {},
    }

    keyword_matches = {
        keyword: [] for keyword in SERVICE_KEYWORDS
    }

    for source_file in source_files:
        try:
            source = source_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        relative_path = str(source_file.relative_to(package_dir))

        source_report["files"].append(relative_path)

        for keyword in SERVICE_KEYWORDS:
            if keyword.lower() in source.lower():
                lines = source.splitlines()

                matches = []
                for line_number, line in enumerate(lines, start=1):
                    if keyword.lower() in line.lower():
                        matches.append({
                            "line": line_number,
                            "text": line.strip()[:220],
                        })

                    if len(matches) >= 15:
                        break

                if matches:
                    keyword_matches[keyword].append({
                        "file": relative_path,
                        "matches": matches,
                    })

        # AST analysis identifies actual classes and method definitions.
        try:
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_methods = []

                    for child in node.body:
                        if isinstance(
                            child,
                            (ast.FunctionDef, ast.AsyncFunctionDef),
                        ):
                            class_methods.append({
                                "name": child.name,
                                "line": child.lineno,
                                "arguments": [
                                    arg.arg for arg in child.args.args
                                ],
                            })

                    source_report["classes"].setdefault(
                        f"{relative_path}:{node.name}",
                        {
                            "file": relative_path,
                            "class": node.name,
                            "line": node.lineno,
                            "methods": class_methods,
                        },
                    )

        except SyntaxError:
            pass

    source_report["keyword_matches"] = keyword_matches
    report["source_code_analysis"] = source_report


def inspect_package_modules():
    import pkt_core

    modules = []

    for module_info in pkgutil.walk_packages(
        pkt_core.__path__,
        prefix="pkt_core.",
    ):
        modules.append(module_info.name)

    report["package"]["modules"] = modules


def main():
    print("=" * 65)
    print("PACKET TRACER PACKAGE CAPABILITY DISCOVERY")
    print("=" * 65)

    import pkt_core
    from pkt_core import Lab

    report["environment"] = {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": sys.platform,
    }

    report["package"].update({
        "name": "packet-tracer-pkt-format",
        "version": getattr(
            importlib.import_module("importlib.metadata"),
            "version",
        )("packet-tracer-pkt-format"),
        "pkt_core_location": str(
            Path(pkt_core.__file__).resolve()
        ),
    })

    print("\n[1/4] Inspecting Lab API...")
    lab = Lab()
    inspect_lab_api(lab)

    print("[2/4] Inspecting device templates...")
    inspect_models(lab)

    print("[3/4] Inspecting installed Python source...")
    inspect_package_source()

    print("[4/4] Discovering package modules...")
    inspect_package_modules()

    model_names = sorted(lab.models.keys())

    service_models = [
        name for name, data in report["models"].items()
        if data.get("service_tags")
    ]

    service_keyword_files = {
        keyword: len(files)
        for keyword, files in
        report["source_code_analysis"]["keyword_matches"].items()
    }

    report["summary"] = {
        "total_device_models": len(model_names),
        "models_with_service_xml": len(service_models),
        "python_modules": len(report["package"]["modules"]),
        "python_source_files": report[
            "source_code_analysis"
        ]["python_file_count"],
        "models": model_names,
        "models_with_service_xml": service_models,
        "source_files_matching_service_keywords": (
            service_keyword_files
        ),
    }

    report["findings"] = [
        "This report describes the installed package and its templates.",
        "A template containing a service XML element does not prove "
        "that the service is fully configurable through the library.",
        "XML structures and Python source matches must be examined "
        "before implementing service configuration.",
        "Packet Tracer GUI validation is still required for generated "
        "service configurations."
    ]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 65)
    print("DISCOVERY COMPLETE")
    print("=" * 65)
    print(f"Device models found: {len(model_names)}")
    print(f"Models with service XML: {len(service_models)}")
    print(
        "Python source files:",
        report["source_code_analysis"]["python_file_count"],
    )
    print(
        "Python modules:",
        len(report["package"]["modules"]),
    )
    print(f"\nReport saved to:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
