#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from reference_locator import load_catalogs, locate
from build_local_bsl_reference_index import build_index
from validate_distribution_privacy import select_distribution_files

results = {}
errors = []
NAME = r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*"


def record(case: str, ok: bool, details) -> None:
    key = f"reference_discovery:{case}"
    results[key] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": key, "details": details})


def normalized(value: str | None) -> str:
    return (value or "").strip().casefold()


PRIVATE_REFERENCE_PREFIXES = ("REFERENCE/INDEXES/", "REFERENCE/SOURCES/")
EXPECTED_PRIVATE_REFERENCE_PATHS = {
    "REFERENCE/INDEXES/bsp_public_api.csv",
    "REFERENCE/INDEXES/dynamic_list_analog_index.csv",
    "REFERENCE/INDEXES/README.md",
    "REFERENCE/SOURCES/BSP_COMMON_MODULES.zip",
    "REFERENCE/SOURCES/TYPICAL_DYNAMIC_LIST_ANALOGS.zip",
}


def reference_distribution_boundary(root: Path, selection: dict) -> dict:
    manifest_kind = selection.get("manifest_kind")
    selected = set(selection.get("selected") or [])
    excluded = {row.get("path") for row in selection.get("excluded") or [] if isinstance(row, dict)}
    selected_private = sorted(
        rel for rel in selected if any(rel.startswith(prefix) for prefix in PRIVATE_REFERENCE_PREFIXES)
    )

    if manifest_kind == "manifest.txt":
        missing_expected_exclusions = sorted(EXPECTED_PRIVATE_REFERENCE_PATHS - excluded)
        return {
            "pass": not missing_expected_exclusions and not selected_private,
            "mode": "INTERNAL_SOURCE",
            "missing_expected_exclusions": missing_expected_exclusions,
            "selected_private_reference": selected_private,
            "excluded_reference": sorted(
                rel for rel in excluded if rel and any(rel.startswith(prefix) for prefix in PRIVATE_REFERENCE_PREFIXES)
            ),
        }

    if manifest_kind == "DISTRIBUTION_MANIFEST.json":
        manifest_path = root / "DISTRIBUTION_MANIFEST.json"
        manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
        manifest_disclosures = sorted(prefix for prefix in PRIVATE_REFERENCE_PREFIXES if prefix in manifest_text)
        actual_private_files = []
        for prefix in PRIVATE_REFERENCE_PREFIXES:
            private_root = root / prefix.rstrip("/")
            if private_root.exists():
                actual_private_files.extend(
                    str(path.relative_to(root)).replace("\\", "/")
                    for path in private_root.rglob("*")
                    if path.is_file()
                )
        actual_private_files = sorted(actual_private_files)
        return {
            "pass": not selected_private and not actual_private_files and not manifest_disclosures,
            "mode": "SHAREABLE_SNAPSHOT",
            "selected_private_reference": selected_private,
            "actual_private_reference_files": actual_private_files,
            "manifest_private_reference_disclosures": manifest_disclosures,
        }

    return {
        "pass": False,
        "mode": "UNKNOWN_MANIFEST_KIND",
        "manifest_kind": manifest_kind,
        "selected_private_reference": selected_private,
    }


def run_reference_boundary_negative_controls(root: Path, selection: dict) -> None:
    manifest_kind = selection.get("manifest_kind")
    if manifest_kind == "manifest.txt":
        source_manifest = root / "manifest.txt"
        lines = source_manifest.read_text(encoding="utf-8-sig").splitlines()
        removed = sorted(EXPECTED_PRIVATE_REFERENCE_PATHS)[0]
        with tempfile.TemporaryDirectory() as td:
            mutated_manifest = Path(td) / "manifest.txt"
            mutated_manifest.write_text(
                "\n".join(line for line in lines if line.strip().replace("\\", "/") != removed) + "\n",
                encoding="utf-8",
            )
            mutated_selection = select_distribution_files(root, mutated_manifest)
            negative = reference_distribution_boundary(root, mutated_selection)
        record(
            "private_side_exclusion_violation_is_rejected",
            not negative["pass"] and removed in negative.get("missing_expected_exclusions", []),
            {"removed_expected_exclusion": removed, "boundary": negative},
        )
        return

    if manifest_kind == "DISTRIBUTION_MANIFEST.json":
        with tempfile.TemporaryDirectory() as td:
            injected_root = Path(td) / "shareable"
            shutil.copytree(root, injected_root)
            injected = injected_root / "REFERENCE/SOURCES/INJECTED_PRIVATE_SOURCE.txt"
            injected.parent.mkdir(parents=True, exist_ok=True)
            injected.write_text("private-source-negative-control\n", encoding="utf-8")
            injected_selection = select_distribution_files(injected_root)
            injected_boundary = reference_distribution_boundary(injected_root, injected_selection)
        record(
            "public_private_reference_file_injection_is_rejected",
            not injected_boundary["pass"]
            and "REFERENCE/SOURCES/INJECTED_PRIVATE_SOURCE.txt" in injected_boundary.get("actual_private_reference_files", []),
            injected_boundary,
        )

        with tempfile.TemporaryDirectory() as td:
            disclosed_root = Path(td) / "shareable"
            shutil.copytree(root, disclosed_root)
            manifest_path = disclosed_root / "DISTRIBUTION_MANIFEST.json"
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["negative_control_private_disclosure"] = "REFERENCE/INDEXES/PRIVATE_CACHE.csv"
            manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            disclosed_selection = select_distribution_files(disclosed_root)
            disclosed_boundary = reference_distribution_boundary(disclosed_root, disclosed_selection)
        record(
            "public_manifest_private_reference_disclosure_is_rejected",
            not disclosed_boundary["pass"]
            and "REFERENCE/INDEXES/" in disclosed_boundary.get("manifest_private_reference_disclosures", []),
            disclosed_boundary,
        )
        return

    record(
        "reference_boundary_negative_control_context_known",
        False,
        {"manifest_kind": manifest_kind},
    )


def oracle_decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def oracle_module_from_path(path: str) -> str | None:
    match = re.search(r"(?:^|/)CommonModules/([^/]+)/Ext/Module\.bsl$", path.replace("\\", "/"), re.IGNORECASE)
    return match.group(1) if match else None


def oracle_modules_from_zip(source_zip: Path) -> set[str]:
    modules = set()
    with zipfile.ZipFile(source_zip, "r") as archive:
        for entry in archive.namelist():
            module = oracle_module_from_path(entry)
            if module:
                modules.add(module)
    return modules


def oracle_close_paren(text: str, open_pos: int) -> int | None:
    depth = 0
    in_string = False
    i = open_pos
    while i < len(text):
        char = text[i]
        if char == '"':
            if in_string and i + 1 < len(text) and text[i + 1] == '"':
                i += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return None


def oracle_exported_api(source_zip: Path) -> tuple[set[tuple[str, str, str]], Counter, dict[str, str]]:
    """Independent lexical oracle for the one property under migration: exported declarations.

    It intentionally does not call the production signature parser. The oracle knows
    nothing about parameters/comments; it only proves module/name/kind + declaration
    Export modifier directly from raw BSL bytes.
    """
    api = set()
    counts = Counter()
    hashes = {}
    declaration_rx = re.compile(rf"(?im)^\s*(Процедура|Функция)\s+({NAME})\s*\(")
    with zipfile.ZipFile(source_zip, "r") as archive:
        for entry in archive.namelist():
            module = oracle_module_from_path(entry)
            if not module or not entry.lower().endswith(".bsl"):
                continue
            data = archive.read(entry)
            hashes[normalized(module)] = hashlib.sha256(data).hexdigest()
            text = oracle_decode(data)
            for match in declaration_rx.finditer(text):
                open_pos = text.find('(', match.start())
                close_pos = oracle_close_paren(text, open_pos)
                if close_pos is None:
                    continue
                line_end_positions = [pos for pos in (text.find('\r', close_pos + 1), text.find('\n', close_pos + 1)) if pos >= 0]
                line_end = min(line_end_positions) if line_end_positions else len(text)
                suffix = text[close_pos + 1:line_end].split('//', 1)[0]
                if not re.match(r"^[ \t]*Экспорт\b", suffix, re.IGNORECASE):
                    continue
                key = (normalized(module), normalized(match.group(2)), normalized(match.group(1)))
                api.add(key)
                counts[normalized(module)] += 1
    return api, counts, hashes


catalogs = load_catalogs(ROOT / "REFERENCE/CATALOGS")
catalog_ids = {x.get("catalog_id") for x in catalogs}
record(
    "catalog_present",
    {"BSP_DISCOVERY", "TYPICAL_ONEC_DISCOVERY"} <= catalog_ids,
    {"catalogs": sorted(x for x in catalog_ids if x)},
)

long_ops = locate("длительная операция", catalogs, 5)
long_modules = {m for row in long_ops.get("matches", []) for m in row.get("candidate_modules", [])}
record("long_operation_locator", "ДлительныеОперации" in long_modules, long_ops)

printing = locate("печать", catalogs, 5)
print_modules = {m for row in printing.get("matches", []) for m in row.get("candidate_modules", [])}
record("printing_locator", "УправлениеПечатью" in print_modules, printing)

typical_effective = locate("эффективный запрос динамического списка", catalogs, 5)
typical_matches = [row for row in typical_effective.get("matches", []) if row.get("catalog_id") == "TYPICAL_ONEC_DISCOVERY"]
typical_modules = {m for row in typical_matches for m in row.get("candidate_modules", [])}
typical_request_types = {
    candidate.get("object_type")
    for row in typical_matches
    for candidate in row.get("request_candidates", [])
}
record(
    "typical_dynamic_list_locator",
    "КонтрольВеденияУчета" in typical_modules and "CommonModule" in typical_request_types,
    typical_effective,
)

# Public catalogs are locators, not copied API/source indexes.
forbidden_keys = {"signature", "summary", "sha256", "exports", "source_code", "body", "interface_comment", "function", "procedure", "has_export"}
catalog_violations = []
public_bsp_modules = set()
public_typical_modules = set()
for catalog in catalogs:
    if catalog.get("role") != "DISCOVERY_ONLY":
        catalog_violations.append({"catalog": catalog.get("catalog_id"), "reason": "role_not_discovery_only"})
    for entry in catalog.get("entries", []):
        overlap = forbidden_keys & set(entry)
        if overlap:
            catalog_violations.append({"entry": entry.get("id"), "forbidden_keys": sorted(overlap)})
        if catalog.get("source_family") == "BSP":
            public_bsp_modules.update(entry.get("candidate_modules", []))
        if catalog.get("source_family") == "TYPICAL_ONEC":
            public_typical_modules.update(entry.get("candidate_modules", []))
record("catalog_contains_locators_not_api_contract", not catalog_violations, catalog_violations)
record("bsp_locator_has_broad_module_recall", len(public_bsp_modules) >= 59, {"unique_candidate_modules": len(public_bsp_modules)})
record(
    "typical_locator_is_mechanism_bounded",
    1 <= len(public_typical_modules) <= 20,
    {"unique_candidate_modules": len(public_typical_modules), "modules": sorted(public_typical_modules)},
)

# Exact API/signature/comment knowledge is reconstructed only from supplied source.
fixture = ROOT / "TESTS/fixtures/TestApi_Module.bsl"
local_index = build_index([], [fixture])
defs = {(x["module"], x["name"]): x for x in local_index.get("definitions", [])}
foo = defs.get(("TestApi", "Foo"))
bar = defs.get(("TestApi", "Bar"))
hidden = defs.get(("TestApi", "Hidden"))
record(
    "local_exact_index_from_source",
    bool(
        local_index.get("schema_version") == 2
        and foo and bar and not hidden
        and foo["required_params"] == 2 and foo["total_params"] == 2
        and bar["required_params"] == 1 and bar["total_params"] == 2
        and "Складывает два обязательных параметра" in foo.get("interface_comment", "")
    ),
    local_index,
)
record(
    "export_token_must_belong_to_declaration",
    hidden is None,
    {"indexed_names": sorted(name for module, name in defs if module == "TestApi"), "rule": "The word Экспорт inside a private routine body/comment/string must not promote it to public API."},
)

private_module_catalog = ROOT / "REFERENCE/INDEXES/bsp_module_catalog.csv"
private_api_index = ROOT / "REFERENCE/INDEXES/bsp_public_api.csv"
private_dynamic_index = ROOT / "REFERENCE/INDEXES/dynamic_list_analog_index.csv"
private_index_policy = ROOT / "REFERENCE/INDEXES/README.md"
private_bsp_source = ROOT / "REFERENCE/SOURCES/BSP_COMMON_MODULES.zip"
private_typical_source = ROOT / "REFERENCE/SOURCES/TYPICAL_DYNAMIC_LIST_ANALOGS.zip"

if private_module_catalog.is_file():
    with private_module_catalog.open("r", encoding="utf-8-sig", newline="") as fh:
        private_module_rows = list(csv.DictReader(fh))
    known_modules = {row.get("module") for row in private_module_rows if row.get("module")}
    missing_from_locator = sorted(known_modules - public_bsp_modules)
    ungrounded_locator = sorted(public_bsp_modules - known_modules)
    record(
        "internal_bsp_locator_grounding",
        not missing_from_locator and not ungrounded_locator,
        {
            "public_modules": len(public_bsp_modules),
            "internal_snapshot_modules": len(known_modules),
            "missing_from_locator": missing_from_locator,
            "ungrounded_locator": ungrounded_locator,
        },
    )
else:
    private_module_rows = []
    record("internal_bsp_locator_grounding", True, {"status": "NOT_AVAILABLE_IN_SHAREABLE_CORE", "rule": "absence does not invalidate public locator; exact target source is still required"})

# Typical locator grounding must be checked against raw retained source, not only a derived CSV.
if private_typical_source.is_file():
    raw_typical_modules = oracle_modules_from_zip(private_typical_source)
    ungrounded_typical = sorted(public_typical_modules - raw_typical_modules)
    record(
        "internal_typical_locator_raw_source_grounding",
        not ungrounded_typical,
        {
            "public_typical_modules": len(public_typical_modules),
            "raw_source_modules": len(raw_typical_modules),
            "ungrounded_locator": ungrounded_typical,
            "rule": "A public typical-configuration locator hint must be grounded in retained raw source during INTERNAL_FULL regression; a derived analog CSV is not the oracle.",
        },
    )
else:
    record(
        "internal_typical_locator_raw_source_grounding",
        True,
        {
            "status": "NOT_AVAILABLE_IN_SHAREABLE_CORE",
            "rule": "Shareable core keeps discovery hints but still requires exact target/user-authorized source before implementation claims.",
        },
    )

if private_dynamic_index.is_file():
    with private_dynamic_index.open("r", encoding="utf-8-sig", newline="") as fh:
        dynamic_rows = list(csv.DictReader(fh))
    dynamic_modules = {row.get("module") for row in dynamic_rows if row.get("module")}
    cache_missing = sorted(public_typical_modules - dynamic_modules)
    policy_text = private_index_policy.read_text(encoding="utf-8") if private_index_policy.is_file() else ""
    policy_ok = "NON_AUTHORITATIVE_DERIVED_CACHE" in policy_text and "dynamic_list_analog_index.csv" in policy_text
    record(
        "internal_typical_derived_index_is_non_authoritative",
        not cache_missing and policy_ok,
        {
            "derived_index_modules": len(dynamic_modules),
            "public_typical_modules": len(public_typical_modules),
            "public_modules_missing_from_cache": cache_missing,
            "policy_present": policy_ok,
            "rule": "The derived CSV may support inventory/migration diagnostics, but retained raw source and current target source remain stronger evidence.",
        },
    )
else:
    record("internal_typical_derived_index_is_non_authoritative", True, {"status": "NOT_AVAILABLE_IN_SHAREABLE_CORE"})

# Quality-critical proof: the public/local parser is validated against an independent
# lexical oracle built directly from the retained raw source. A historical prebuilt API
# index is diagnostic/cache evidence only and is never the oracle for exact API semantics.
if private_module_catalog.is_file() and private_bsp_source.is_file():
    source_api, source_counts, source_hashes = oracle_exported_api(private_bsp_source)
    rebuilt = build_index([private_bsp_source], [])
    rebuilt_defs = rebuilt.get("definitions", [])
    rebuilt_api = {
        (normalized(row.get("module")), normalized(row.get("name")), normalized(row.get("kind")))
        for row in rebuilt_defs
        if row.get("module") and row.get("name") and row.get("kind")
    }
    missing_api = sorted(source_api - rebuilt_api)
    unexpected_api = sorted(rebuilt_api - source_api)

    catalog_count_mismatches = []
    catalog_hash_mismatches = []
    for row in private_module_rows:
        module = normalized(row.get("module"))
        try:
            expected_count = int((row.get("exports") or "0").strip())
        except ValueError:
            expected_count = -1
        if source_counts.get(module, 0) != expected_count:
            catalog_count_mismatches.append({"module": module, "catalog": expected_count, "source": source_counts.get(module, 0)})
        expected_hash = (row.get("sha256") or "").strip().lower()
        if expected_hash and source_hashes.get(module) != expected_hash:
            catalog_hash_mismatches.append({"module": module, "catalog": expected_hash, "source": source_hashes.get(module)})

    record(
        "internal_bsp_local_index_exact_source_parity",
        not missing_api and not unexpected_api and not catalog_count_mismatches and not catalog_hash_mismatches,
        {
            "source_exported_api": len(source_api),
            "rebuilt_exported_api": len(rebuilt_api),
            "source_modules": len(source_counts),
            "missing_api": missing_api[:30],
            "unexpected_api": unexpected_api[:30],
            "catalog_count_mismatches": catalog_count_mismatches[:30],
            "catalog_hash_mismatches": catalog_hash_mismatches[:30],
            "rule": "Replacement quality is proven against raw exact-source export semantics, not against a historical prebuilt API CSV."
        },
    )

    if private_api_index.is_file():
        with private_api_index.open("r", encoding="utf-8-sig", newline="") as fh:
            private_api_rows = list(csv.DictReader(fh))
        historical_api = {
            (normalized(row.get("module")), normalized(row.get("name")), normalized(row.get("kind")))
            for row in private_api_rows
            if row.get("module") and row.get("name") and row.get("kind")
        }
        historical_only = sorted(historical_api - source_api)
        source_only = sorted(source_api - historical_api)
        policy_text = private_index_policy.read_text(encoding="utf-8") if private_index_policy.is_file() else ""
        policy_ok = "NON_AUTHORITATIVE_DERIVED_CACHE" in policy_text and "bsp_public_api.csv" in policy_text
        record(
            "internal_prebuilt_bsp_index_is_non_authoritative",
            policy_ok,
            {
                "historical_rows": len(historical_api),
                "exact_source_rows": len(source_api),
                "historical_only": len(historical_only),
                "source_only": len(source_only),
                "sample_historical_only": historical_only[:10],
                "sample_source_only": source_only[:10],
                "policy_present": policy_ok,
                "rule": "A derived cache may be retained for forensics, but exact source/local rebuild wins on contradiction."
            },
        )
else:
    record(
        "internal_bsp_local_index_exact_source_parity",
        True,
        {
            "status": "NOT_AVAILABLE_IN_SHAREABLE_CORE",
            "missing": [
                str(path.relative_to(ROOT))
                for path in (private_module_catalog, private_bsp_source)
                if not path.is_file()
            ],
            "rule": "Shareable core cannot run retained-private-source parity; INTERNAL_FULL CI must run it before the internal BSP corpus is removed."
        },
    )
    record("internal_prebuilt_bsp_index_is_non_authoritative", True, {"status": "NOT_AVAILABLE_IN_SHAREABLE_CORE"})

# Distribution must include public catalogs/tools/knowledge. The private source build proves
# expected private reference paths are actively excluded; an unpacked public snapshot instead
# proves those paths are physically absent and are not disclosed by its public manifest.
selection = select_distribution_files(ROOT)
selected = set(selection.get("selected") or [])
record(
    "shareable_selection_keeps_discovery_layer",
    "REFERENCE/CATALOGS/bsp_discovery.json" in selected
    and "REFERENCE/CATALOGS/typical_onec_discovery.json" in selected
    and "TOOLS/reference_locator.py" in selected
    and "TOOLS/build_local_bsl_reference_index.py" in selected
    and "KNOWLEDGE/REFERENCE_SOURCE_ARCHITECTURE.md" in selected,
    {"selected_discovery": sorted(x for x in selected if x.startswith("REFERENCE/CATALOGS/") or x.endswith("reference_locator.py") or x.endswith("build_local_bsl_reference_index.py") or x.endswith("REFERENCE_SOURCE_ARCHITECTURE.md"))},
)
reference_boundary = reference_distribution_boundary(ROOT, selection)
record(
    "shareable_selection_excludes_private_reference",
    reference_boundary["pass"],
    reference_boundary,
)
run_reference_boundary_negative_controls(ROOT, selection)

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
