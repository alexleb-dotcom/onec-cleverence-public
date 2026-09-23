#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import base64
import json
import re
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOOLS"))

from validate_distribution_privacy import normalize_rel, select_distribution_files, validate_distribution_paths, validate_repository_distribution_state
from build_distribution_snapshot import build_distribution
from validate_distribution_snapshot import (
    SNAPSHOT_DIGEST_ALGORITHM,
    SNAPSHOT_MANIFEST_KEYS,
    SNAPSHOT_SCHEMA_VERSION,
    build_distribution_manifest,
    compute_snapshot_digest,
    validate_snapshot_root,
)

results = {}
errors = []


def record(case: str, ok: bool, details) -> None:
    key = f"distribution_privacy:{case}"
    results[key] = {"pass": bool(ok), "details": details}
    if not ok:
        errors.append({"case": key, "details": details})


def finding_types(report: dict) -> set[str]:
    return {row.get("type") for row in report.get("errors", [])}


# Empirical regression: relative-path normalization must preserve leading dots in real dotfiles/directories.
dotfile_cases = {
    ".gitignore": ".gitignore",
    ".gitattributes": ".gitattributes",
    "./.github/workflows/x.yml": ".github/workflows/x.yml",
}
record("dotfile_normalization", all(normalize_rel(src) == expected for src, expected in dotfile_cases.items()), {src: normalize_rel(src) for src in dotfile_cases})

# Exact snapshot validator: clean tree passes; byte drift, extra/missing files, duplicate and unsafe paths fail closed.
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "sub").mkdir()
    (root / "a.txt").write_bytes(b"alpha")
    (root / "sub" / "b.bin").write_bytes(b"\x00beta\x01")
    public_workflow = root / ".github" / "workflows" / "shareable-validation.yml"
    public_workflow.parent.mkdir(parents=True)
    public_workflow.write_text("name: Shareable validation\n", encoding="utf-8")

    def row(rel: str) -> dict:
        data = (root / rel).read_bytes()
        import hashlib
        return {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    clean_rows = [row("a.txt"), row("sub/b.bin"), row(".github/workflows/shareable-validation.yml")]
    clean_manifest = build_distribution_manifest(clean_rows)
    manifest_path = root / "DISTRIBUTION_MANIFEST.json"
    manifest_path.write_text(json.dumps(clean_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record("exact_snapshot_clean_passes", report["result"] == "PASS" and report["checked_files"] == 3, report)

    baseline_snapshot_digest = clean_manifest["snapshot_digest"]
    permuted_manifest = dict(clean_manifest)
    permuted_manifest["files"] = list(reversed(clean_rows))
    manifest_path.write_text(json.dumps(permuted_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record(
        "canonical_snapshot_digest_is_inventory_order_independent",
        report["result"] == "PASS"
        and compute_snapshot_digest(permuted_manifest["files"]) == baseline_snapshot_digest,
        report,
    )

    tampered_digest_manifest = dict(clean_manifest)
    tampered_digest_manifest["snapshot_digest"] = "0" * 64
    manifest_path.write_text(json.dumps(tampered_digest_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record(
        "canonical_snapshot_digest_tamper_blocks",
        "SNAPSHOT_DIGEST_MISMATCH" in finding_types(report),
        report,
    )

    (root / "a.txt").write_bytes(b"alphb")
    mutated_rows = [row("a.txt"), row("sub/b.bin"), row(".github/workflows/shareable-validation.yml")]
    record(
        "canonical_snapshot_digest_changes_on_one_byte",
        compute_snapshot_digest(mutated_rows) != baseline_snapshot_digest,
        {
            "before": baseline_snapshot_digest,
            "after": compute_snapshot_digest(mutated_rows),
        },
    )
    (root / "a.txt").write_bytes(b"alpha")
    manifest_path.write_text(json.dumps(clean_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record(
        "exact_snapshot_public_checkout_git_metadata_is_ignored",
        report["result"] == "PASS" and report["actual_files"] == 3,
        report,
    )

    undeclared_hidden = root / ".unexpected"
    undeclared_hidden.write_text("must still block", encoding="utf-8")
    report = validate_snapshot_root(root)
    record(
        "exact_snapshot_other_hidden_files_still_block",
        "SNAPSHOT_UNDECLARED_FILE_PRESENT" in finding_types(report),
        report,
    )
    undeclared_hidden.unlink()

    (root / "a.txt").write_bytes(b"tampered")
    report = validate_snapshot_root(root)
    record("exact_snapshot_byte_drift_blocks", "SNAPSHOT_FILE_SIZE_MISMATCH" in finding_types(report) or "SNAPSHOT_FILE_SHA256_MISMATCH" in finding_types(report), report)
    (root / "a.txt").write_bytes(b"alpha")

    (root / "extra.txt").write_text("extra", encoding="utf-8")
    report = validate_snapshot_root(root)
    record("exact_snapshot_extra_file_blocks", "SNAPSHOT_UNDECLARED_FILE_PRESENT" in finding_types(report), report)
    (root / "extra.txt").unlink()

    (root / "sub" / "b.bin").unlink()
    report = validate_snapshot_root(root)
    record("exact_snapshot_missing_file_blocks", "SNAPSHOT_DECLARED_FILE_MISSING" in finding_types(report), report)
    (root / "sub" / "b.bin").write_bytes(b"\x00beta\x01")

    duplicate_manifest = dict(clean_manifest)
    duplicate_manifest["files"] = clean_rows + [dict(clean_rows[0])]
    duplicate_manifest["file_count"] = len(duplicate_manifest["files"])
    manifest_path.write_text(json.dumps(duplicate_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record("exact_snapshot_duplicate_path_blocks", "SNAPSHOT_DUPLICATE_FILE_PATH" in finding_types(report), report)

    unsafe_manifest = dict(clean_manifest)
    unsafe_manifest["files"] = [dict(clean_rows[0], path="../escape.txt"), clean_rows[1]]
    manifest_path.write_text(json.dumps(unsafe_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_snapshot_root(root)
    record("exact_snapshot_unsafe_path_blocks", "SNAPSHOT_UNSAFE_FILE_PATH" in finding_types(report), report)

with tempfile.TemporaryDirectory() as td:
    root = Path(td)

    # A clean generic file is shareable.
    (root / "SKILL.md").write_text("# Generic skill\nNo project identity here.\n", encoding="utf-8")
    report = validate_distribution_paths(root, ["SKILL.md"])
    record("generic_text_passes", report["result"] == "PASS", report)

    # Public locator catalogs are allowed: they contain discovery metadata, not raw vendor/project source.
    catalog = root / "REFERENCE" / "CATALOGS" / "locator.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text('{"role":"DISCOVERY_ONLY","entries":[]}', encoding="utf-8")
    report = validate_distribution_paths(root, ["REFERENCE/CATALOGS/locator.json"])
    record("public_reference_catalog_passes", report["result"] == "PASS", report)

    # Project/history surfaces are blocked by path even if their content looks harmless.
    private_path = root / "ARCHIVE" / "DEVELOPER_PACK" / "CURRENT_WORK" / "state.json"
    private_path.parent.mkdir(parents=True)
    private_path.write_text("{}", encoding="utf-8")
    report = validate_distribution_paths(root, ["ARCHIVE/DEVELOPER_PACK/CURRENT_WORK/state.json"])
    record("project_archive_path_blocks", "DISTRIBUTION_RESTRICTED_PATH" in finding_types(report), report)

    # Raw reference packs are not public/shareable by default when redistribution rights are unresolved.
    reference = root / "REFERENCE" / "SOURCES" / "VendorReference.zip"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"reference")
    report = validate_distribution_paths(root, ["REFERENCE/SOURCES/VendorReference.zip"])
    record("raw_reference_pack_blocks", "DISTRIBUTION_RESTRICTED_PATH" in finding_types(report), report)

    # PII/local-path/secret patterns are constructed at runtime so the regression source itself remains shareable.
    email_value = "person" + "@" + "example.org"
    pii = root / "notes.txt"; pii.write_text(f"contact={email_value}\n", encoding="utf-8")
    report = validate_distribution_paths(root, ["notes.txt"])
    record("email_blocks", "PERSONAL_EMAIL" in finding_types(report), report)

    local_path = "C:" + "\\" + "Users" + "\\" + "developer" + "\\" + "project"
    local = root / "local.txt"; local.write_text(local_path, encoding="utf-8")
    report = validate_distribution_paths(root, ["local.txt"])
    record("local_user_path_blocks", "LOCAL_WINDOWS_USER_PATH" in finding_types(report), report)

    token_value = "ghp_" + ("A" * 24)
    token = root / "token.txt"; token.write_text(token_value, encoding="utf-8")
    report = validate_distribution_paths(root, ["token.txt"])
    record("token_blocks", "HIGH_CONFIDENCE_ACCESS_TOKEN" in finding_types(report), report)

    binary_token = root / "fixture.bin"
    binary_token.write_bytes(b"\x00\x01prefix-" + token_value.encode("ascii") + b"-suffix\x00")
    report = validate_distribution_paths(root, ["fixture.bin"])
    record("binary_token_blocks", "HIGH_CONFIDENCE_ACCESS_TOKEN" in finding_types(report), report)

    third_party = root / "THIRD_PARTY" / "vendor" / "NOTICE.md"
    third_party.parent.mkdir(parents=True)
    attribution_email = "contact" + "@" + "example.org"
    third_party.write_text("Copyright " + attribution_email + "\n" + token_value + "\n", encoding="utf-8")
    import hashlib
    policy_path = root / "TOOLS" / "SHAREABLE_BINARY_REVIEW_POLICY.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(json.dumps({
        "schema_version": 1,
        "policy_id": "shareable-binary-review-v1",
        "reviewed_binary_files": [],
        "third_party_attribution_files": [{
            "path": "THIRD_PARTY/vendor/NOTICE.md",
            "policy_id": "shareable-binary-review-v1",
            "sha256": hashlib.sha256(third_party.read_bytes()).hexdigest(),
            "reason": "regression fixture for exact third-party attribution bytes",
        }],
    }, indent=2) + "\n", encoding="utf-8")
    report = validate_distribution_paths(root, ["THIRD_PARTY/vendor/NOTICE.md"])
    record(
        "third_party_attribution_email_allowed_but_secret_blocks",
        "PERSONAL_EMAIL" not in finding_types(report)
        and "HIGH_CONFIDENCE_ACCESS_TOKEN" in finding_types(report),
        report,
    )

    private_ip = ".".join(["10", "23", "45", "67"])
    private_ip_file = root / "private-ip.txt"
    private_ip_file.write_text("endpoint=http://" + private_ip + ":8080/service", encoding="utf-8")
    report = validate_distribution_paths(root, ["private-ip.txt"])
    record("private_network_ipv4_blocks", "PRIVATE_NETWORK_IPV4" in finding_types(report), report)

    private_host = "build" + "." + "corp" + "." + "internal"
    private_host_file = root / "private-host.txt"
    private_host_file.write_text("endpoint=https://" + private_host + "/api", encoding="utf-8")
    report = validate_distribution_paths(root, ["private-host.txt"])
    record("private_network_hostname_blocks", "PRIVATE_NETWORK_HOSTNAME" in finding_types(report), report)

    secret_assignment = "Password" + "=" + "actual-secret-value"
    secret_file = root / "connection.txt"
    secret_file.write_text("Server=db.example.com;" + secret_assignment + ";", encoding="utf-8")
    report = validate_distribution_paths(root, ["connection.txt"])
    record("connection_secret_assignment_blocks", "CONNECTION_SECRET_ASSIGNMENT" in finding_types(report), report)

    placeholder_file = root / "connection-placeholder.txt"
    placeholder_file.write_text("Server=db.example.com;" + "Password" + "=" + "<redacted>;", encoding="utf-8")
    report = validate_distribution_paths(root, ["connection-placeholder.txt"])
    record("redacted_connection_secret_passes", "CONNECTION_SECRET_ASSIGNMENT" not in finding_types(report), report)

    public_url = root / "public-url.txt"
    public_url.write_text("docs=https://example.com/reference", encoding="utf-8")
    report = validate_distribution_paths(root, ["public-url.txt"])
    record(
        "public_url_is_not_private_locator",
        "PRIVATE_NETWORK_IPV4" not in finding_types(report)
        and "PRIVATE_NETWORK_HOSTNAME" not in finding_types(report),
        report,
    )

    encoded_dir = root / "PAYLOAD"
    encoded_dir.mkdir()
    hidden_token = ("ghp_" + ("B" * 24)).encode("ascii")
    encoded = base64.b64encode(b"binary-prefix-" + hidden_token + b"-binary-suffix").decode("ascii")
    split_at = len(encoded) // 2
    part1 = encoded_dir / "artifact.bin.b64.part01"
    part2 = encoded_dir / "artifact.bin.b64.part02"
    part1.write_text(encoded[:split_at], encoding="ascii")
    part2.write_text(encoded[split_at:], encoding="ascii")
    report = validate_distribution_paths(
        root,
        ["PAYLOAD/artifact.bin.b64.part01", "PAYLOAD/artifact.bin.b64.part02"],
    )
    record(
        "base64_transport_decoded_secret_blocks",
        "HIGH_CONFIDENCE_ACCESS_TOKEN" in finding_types(report)
        and report.get("checked_base64_payloads") == 1,
        report,
    )

    safe_encoded = base64.b64encode(b"portable-public-artifact").decode("ascii")
    safe_part = encoded_dir / "safe.bin.b64.part01"
    safe_part.write_text(safe_encoded, encoding="ascii")
    report = validate_distribution_paths(root, ["PAYLOAD/safe.bin.b64.part01"])
    record(
        "base64_transport_clean_payload_passes",
        report["result"] == "PASS" and report.get("checked_base64_payloads") == 1,
        report,
    )

    # Selector keeps public catalogs while excluding raw/derived private reference and internal manifest surfaces.
    (root / "TOOLS").mkdir(exist_ok=True)
    (root / "TOOLS" / "x.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "manifest.txt").write_text("SKILL.md\nTOOLS/x.py\nREFERENCE/CATALOGS/locator.json\nREFERENCE/SOURCES/VendorReference.zip\nREFERENCE/INDEXES/vendor.csv\nmanifest.txt\n", encoding="utf-8")
    index = root / "REFERENCE" / "INDEXES" / "vendor.csv"; index.parent.mkdir(parents=True, exist_ok=True); index.write_text("x", encoding="utf-8")
    selection = select_distribution_files(root)
    record(
        "selector_excludes_restricted_surfaces",
        selection["selected"] == ["SKILL.md", "TOOLS/x.py", "REFERENCE/CATALOGS/locator.json"] and {x["path"] for x in selection["excluded"]} == {"REFERENCE/SOURCES/VendorReference.zip", "REFERENCE/INDEXES/vendor.csv", "manifest.txt"} and not selection.get("unsafe"),
        selection,
    )

    outside = root.parent / "outside-secret.txt"
    outside.write_text("must never enter snapshot", encoding="utf-8")
    (root / "manifest.txt").write_text("../outside-secret.txt\n", encoding="utf-8")
    traversal = select_distribution_files(root)
    record(
        "selector_blocks_parent_traversal",
        not traversal["selected"]
        and any(row.get("reason") == "path_traversal" for row in traversal.get("unsafe", [])),
        traversal,
    )

    (root / "manifest.txt").write_text(str(outside.resolve()) + "\n", encoding="utf-8")
    absolute = select_distribution_files(root)
    record(
        "selector_blocks_absolute_path",
        not absolute["selected"]
        and any(row.get("reason") == "absolute_or_empty_path" for row in absolute.get("unsafe", [])),
        absolute,
    )

    symlink_supported = True
    link = root / "outside-link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        symlink_supported = False
    if symlink_supported:
        (root / "manifest.txt").write_text("outside-link.txt\n", encoding="utf-8")
        linked = select_distribution_files(root)
        record(
            "selector_blocks_symlink_input",
            not linked["selected"]
            and any(row.get("reason") == "symlink_input" for row in linked.get("unsafe", [])),
            linked,
        )
        link.unlink()
    else:
        record("selector_blocks_symlink_input", True, {"skipped_platform_without_symlink": True})
    # Builder must fail closed on unsafe manifest rows rather than silently omitting them.
    (root / "manifest.txt").write_text("../outside-again.txt\n", encoding="utf-8")
    outside_again = root.parent / "outside-again.txt"
    outside_again.write_text("must never enter snapshot", encoding="utf-8")
    unsafe_output = root / "unsafe.zip"
    unsafe_build = build_distribution(unsafe_output, root)
    record(
        "builder_fails_closed_on_unsafe_manifest_path",
        unsafe_build.get("result") == "FAIL"
        and any(row.get("type") == "MANIFEST_UNSAFE_SELECTED_PATH" for row in unsafe_build.get("errors", []))
        and not unsafe_output.exists(),
        unsafe_build,
    )
    outside_again.unlink()

# Distribution contract must preserve the explicit clean-history warning and internal/shareable split.
distribution_contract = (ROOT / "DISTRIBUTION.md").read_text(encoding="utf-8")
contract_tokens = [
    "INTERNAL_FULL",
    "SHAREABLE_CORE",
    "Git history",
    "one-commit README-only public bootstrap",
    "REFERENCE/SOURCES/**",
    "REFERENCE/INDEXES/**",
    "CLEAN_SNAPSHOT_ONLY",
    "Public Fast",
    "Public Full",
    "private source commit",
]
missing_contract_tokens = [token for token in contract_tokens if token not in distribution_contract]
record("distribution_contract_tokens", not missing_contract_tokens, {"missing": missing_contract_tokens})

# The actual feature/current tree must have no retained private project archive and its exact shareable selection must pass privacy checks.
actual = validate_repository_distribution_state(ROOT)
record("actual_repository_shareable_selection", actual["result"] == "PASS", actual)
selection = actual.get("selection") or {}
selected = set(selection.get("selected") or [])
record("actual_selection_has_no_archive", not any(x.startswith("ARCHIVE/") for x in selected), sorted(x for x in selected if x.startswith("ARCHIVE/")))
record(
    "actual_selection_excludes_owner_decided_collector",
    not any(x.startswith("COLLECTOR/") for x in selected),
    sorted(x for x in selected if x.startswith("COLLECTOR/")),
)
record(
    "actual_selection_keeps_root_rights_notice",
    "RIGHTS_NOTICE.md" in selected,
    "RIGHTS_NOTICE.md" in selected,
)
selected_workflows = {
    x for x in selected
    if x.startswith(".github/workflows/")
}
expected_public_workflows = {
    ".github/workflows/shareable-validation.yml"
}
record(
    "actual_selection_keeps_only_public_workflow",
    selected_workflows == expected_public_workflows,
    sorted(selected_workflows),
)
record(
    "actual_selection_has_no_private_reference_corpus",
    not any(x.startswith("REFERENCE/SOURCES/") or x.startswith("REFERENCE/INDEXES/") for x in selected),
    sorted(x for x in selected if x.startswith("REFERENCE/"))[:50],
)
record(
    "actual_selection_keeps_public_reference_catalogs",
    "REFERENCE/CATALOGS/bsp_discovery.json" in selected,
    sorted(x for x in selected if x.startswith("REFERENCE/CATALOGS/")),
)
record("private_archive_removed_from_current_tree", not (ROOT / "ARCHIVE/DEVELOPER_PACK").exists() and not (ROOT / "ARCHIVE/EXTERNAL_METHODS").exists(), {"developer_pack": (ROOT / "ARCHIVE/DEVELOPER_PACK").exists(), "external_methods": (ROOT / "ARCHIVE/EXTERNAL_METHODS").exists()})

# Operational public entrypoints must route discovery through public catalogs and
# exact supplied source instead of instructing a weak model to open excluded files.
skill_contract = (ROOT / "SKILL.md").read_text(encoding="utf-8")
cleverence_contract = (ROOT / "KNOWLEDGE/CLEVERENCE_RUNTIME_INTEGRATION.md").read_text(encoding="utf-8")
public_discovery_tokens = [
    "REFERENCE/CATALOGS/bsp_discovery.json",
    "REFERENCE/CATALOGS/typical_onec_discovery.json",
    "REFERENCE/CATALOGS/cleverence_discovery.json",
    "TOOLS/build_local_bsl_reference_index.py",
    "TOOLS/build_local_cleverence_reference_index.py",
]
missing_public_discovery = [token for token in public_discovery_tokens if token not in skill_contract + cleverence_contract]
restricted_operational_refs = [
    token
    for token in ("REFERENCE/SOURCES/", "REFERENCE/INDEXES/", "MAINTENANCE/INTERNAL/")
    if token in skill_contract or token in cleverence_contract
]
record(
    "public_discovery_entrypoints_are_self_contained",
    not missing_public_discovery and not restricted_operational_refs,
    {"missing": missing_public_discovery, "restricted_refs": restricted_operational_refs},
)

public_workflow = (ROOT / ".github/workflows/shareable-validation.yml").read_text(encoding="utf-8")
private_workflow_inputs = [
    token
    for token in ("REFERENCE/SOURCES/", "REFERENCE/INDEXES/", "MAINTENANCE/INTERNAL/")
    if token in public_workflow
]
workflow_tokens = [
    "DISTRIBUTION_MANIFEST.json",
    "build_distribution_snapshot.py",
    "validate_distribution_snapshot.py --root .",
    "run_public_ci.py --mode FAST",
    "run_public_ci.py --mode FULL",
    "persist-credentials: false",
]
missing_workflow_tokens = [token for token in workflow_tokens if token not in public_workflow]
record(
    "public_workflow_is_snapshot_self_contained",
    not private_workflow_inputs and not missing_workflow_tokens,
    {"private_inputs": private_workflow_inputs, "missing": missing_workflow_tokens},
)

expected_action_pins = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
}
action_pin_errors = []
for action, sha in expected_action_pins.items():
    expected_token = f"uses: {action}@{sha}"
    if expected_token not in public_workflow:
        action_pin_errors.append({"action": action, "expected_sha": sha})
mutable_action_uses = [
    line.strip()
    for line in public_workflow.splitlines()
    if line.strip().startswith("uses: actions/")
    and not re.search(r"@[0-9a-f]{40}(?:\s|$)", line.strip())
]
record(
    "public_workflow_actions_are_immutable_sha_pinned",
    not action_pin_errors and not mutable_action_uses,
    {"missing_pins": action_pin_errors, "mutable_uses": mutable_action_uses},
)

unsafe_workflow_tokens = [
    token
    for token in ("pull_request_target", "secrets.", "write-all", "contents: write")
    if token in public_workflow
]
record(
    "public_workflow_has_read_only_untrusted_pr_boundary",
    not unsafe_workflow_tokens
    and public_workflow.count("persist-credentials: false") == 2
    and "permissions:\n  contents: read" in public_workflow,
    {
        "unsafe_tokens": unsafe_workflow_tokens,
        "persist_credentials_false_count": public_workflow.count("persist-credentials: false"),
    },
)
record(
    "public_workflow_exposes_fast_and_full_contexts",
    "name: Public Fast" in public_workflow
    and "name: Public Full" in public_workflow
    and "needs: public-fast" in public_workflow,
    {
        "fast": "name: Public Fast" in public_workflow,
        "full": "name: Public Full" in public_workflow,
        "dependency": "needs: public-fast" in public_workflow,
    },
)

# Build the exact shareable ZIP and inspect names; restricted paths must be absent, public catalogs must survive, and a distribution manifest must exist.
with tempfile.TemporaryDirectory() as td:
    output = Path(td) / "shareable.zip"
    output_second = Path(td) / "shareable-second.zip"
    built = build_distribution(output, ROOT)
    built_second = build_distribution(output_second, ROOT)
    deterministic = (
        built.get("result") == "PASS"
        and built_second.get("result") == "PASS"
        and built.get("snapshot_digest") == built_second.get("snapshot_digest")
        and built.get("archive_sha256") == built_second.get("archive_sha256")
        and output.read_bytes() == output_second.read_bytes()
    )
    record(
        "shareable_zip_is_byte_deterministic",
        deterministic,
        {
            "first_snapshot_digest": built.get("snapshot_digest"),
            "second_snapshot_digest": built_second.get("snapshot_digest"),
            "first_zip_sha256": built.get("archive_sha256"),
            "second_zip_sha256": built_second.get("archive_sha256"),
        },
    )
    names = []
    manifest_payload = {}
    if built.get("result") == "PASS":
        with zipfile.ZipFile(output, "r") as archive:
            names = archive.namelist()
            archive_infos = archive.infolist()
            manifest_name = "onec-cleverence/DISTRIBUTION_MANIFEST.json"
            if manifest_name in names:
                manifest_payload = json.loads(archive.read(manifest_name).decode("utf-8"))
        metadata_is_deterministic = all(
            info.date_time == (1980, 1, 1, 0, 0, 0)
            and info.create_system == 3
            and ((info.external_attr >> 16) & 0xFFFF) == 0o100644
            for info in archive_infos
        )
        record(
            "shareable_zip_metadata_is_deterministic",
            metadata_is_deterministic,
            [
                {
                    "name": info.filename,
                    "date_time": info.date_time,
                    "create_system": info.create_system,
                    "mode": (info.external_attr >> 16) & 0xFFFF,
                }
                for info in archive_infos[:5]
            ],
        )
    restricted_absent = all(
        not name.startswith("onec-cleverence/ARCHIVE/")
        and not name.startswith("onec-cleverence/REFERENCE/SOURCES/")
        and not name.startswith("onec-cleverence/REFERENCE/INDEXES/")
        and not name.startswith("onec-cleverence/COLLECTOR/")
        for name in names
    )
    record("shareable_zip_builds", built.get("result") == "PASS" and output.is_file(), built)
    record("shareable_zip_has_no_restricted_paths", restricted_absent, names[:80])
    record("shareable_zip_keeps_public_catalog", "onec-cleverence/REFERENCE/CATALOGS/bsp_discovery.json" in names, [x for x in names if "/REFERENCE/" in x])
    record("shareable_zip_has_distribution_manifest", "onec-cleverence/DISTRIBUTION_MANIFEST.json" in names, names[-10:])
    record(
        "shareable_zip_keeps_root_rights_notice",
        "onec-cleverence/RIGHTS_NOTICE.md" in names,
        [x for x in names if x.endswith("RIGHTS_NOTICE.md")],
    )
    record(
        "shareable_zip_excludes_owner_decided_collector",
        not any(name.startswith("onec-cleverence/COLLECTOR/") for name in names),
        [x for x in names if x.startswith("onec-cleverence/COLLECTOR/")][:20],
    )

    if built.get("result") == "PASS":
        extracted = Path(td) / "extracted"
        with zipfile.ZipFile(output, "r") as archive:
            archive.extractall(extracted)
        exact_report = validate_snapshot_root(extracted / "onec-cleverence")
        record("built_shareable_zip_exact_tree_passes", exact_report["result"] == "PASS", exact_report)

    expected_manifest_keys = set(SNAPSHOT_MANIFEST_KEYS)
    manifest_keys = set(manifest_payload) if isinstance(manifest_payload, dict) else set()
    manifest_rows = manifest_payload.get("files", []) if isinstance(manifest_payload, dict) else []
    manifest_rows_public_only = all(
        isinstance(row, dict) and set(row) == {"path", "size", "sha256"}
        for row in manifest_rows
    )
    record(
        "shareable_manifest_is_public_inventory_only",
        manifest_payload.get("schema_version") == SNAPSHOT_SCHEMA_VERSION
        and manifest_payload.get("distribution_profile") == "SHAREABLE_CORE"
        and manifest_payload.get("snapshot_digest_algorithm") == SNAPSHOT_DIGEST_ALGORITHM
        and manifest_payload.get("snapshot_digest") == built.get("snapshot_digest")
        and manifest_keys == expected_manifest_keys
        and manifest_rows_public_only,
        {
            "keys": sorted(manifest_keys),
            "schema_version": manifest_payload.get("schema_version"),
            "row_count": len(manifest_rows),
        },
    )
    forbidden_manifest_keys = {
        "source_commit",
        "excluded_prefixes",
        "excluded_exact",
        "excluded_from_internal_manifest",
    }
    manifest_text = json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True)
    forbidden_manifest_tokens = [
        "MAINTENANCE/INTERNAL/",
        "REFERENCE/SOURCES/",
        "REFERENCE/INDEXES/",
    ]
    record(
        "shareable_manifest_does_not_leak_private_metadata",
        not (manifest_keys & forbidden_manifest_keys)
        and not any(token in manifest_text for token in forbidden_manifest_tokens),
        {
            "forbidden_keys_present": sorted(manifest_keys & forbidden_manifest_keys),
            "forbidden_tokens_present": [token for token in forbidden_manifest_tokens if token in manifest_text],
        },
    )
    shareable_workflows = {
        name for name in names
        if name.startswith("onec-cleverence/.github/workflows/")
    }
    expected_shareable_workflows = {
        "onec-cleverence/.github/workflows/shareable-validation.yml"
    }
    record(
        "shareable_zip_keeps_only_public_workflow",
        shareable_workflows == expected_shareable_workflows,
        sorted(shareable_workflows),
    )

out = {"result": "PASS" if not errors else "FAIL", "errors": errors, "results": results}
print(json.dumps(out, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
