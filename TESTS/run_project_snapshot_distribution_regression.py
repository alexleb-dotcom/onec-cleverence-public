#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json"
README = ROOT / "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/README.md"
KNOWLEDGE = ROOT / "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_DISTRIBUTION.md"
ORCHESTRATION = ROOT / "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json"
MATERIALIZER = ROOT / "TOOLS/materialize_project_snapshot_collector.py"

EXPECTED_BINARY_SHA256 = "824fb8ccc84fb62d537d56fde67ef07c8395b74319408be7523be95e7932b27e"
EXPECTED_BINARY_BLOB = "7dff9253bfd66cb338fc7ef329687374538cfb31"
EXPECTED_BINARY_SIZE = 15265
EXPECTED_ENCODED_SIZE = 20356
EXPECTED_PAYLOAD_PARTS = {
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part01": "42c7e68b656cb30aa0a0fa36e36ff7d138adad85",
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part02": "5cfb607a345f1a8d54acf7dbf3478b50573e1555",
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part03": "f0c08238488c93f390f2da41a4884f99e52bcf3f",
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part04a": "4386327e1e983d9679a4cc86df12b74cee39efb0",
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part04b": "aa0d41aca48577dc580ceea17b26dbea85acbafd",
    "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD/ProjectSnapshotCollector.epf.b64.part05": "6c68087befa4933c58595e060e2e6819ca8f7bdb",
}
EXPECTED_BUILD_INPUTS = {
    "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector.xml": "bdddb833b92531420a003fcf4228ef2af700b869",
    "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Ext/ObjectModule.bsl": "35c66138f6f86fe36ba7cc15edcf3bfca24ea376",
    "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Forms/MainForm.xml": "3a7234b27d99aa2f6458d9d3bc1e37f84bcf95d4",
    "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Forms/MainForm/Ext/Form.xml": "340cb59c82c5566dbcd862788df5130b25ef070e",
    "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE/ProjectSnapshotCollector/Forms/MainForm/Ext/Form/Module.bsl": "050f78178b0eac894cd726bbb08548ead73147c2",
}


def git_blob_sha1(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {len(data)}\0".encode("ascii"))
    digest.update(data)
    return digest.hexdigest()


def run_materializer(manifest_path: Path, output: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(MATERIALIZER), "--manifest", str(manifest_path)]
    if output is not None:
        command.extend(["--output", str(output)])
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def main() -> int:
    errors: list[str] = []

    required_paths = [MANIFEST, README, KNOWLEDGE, ORCHESTRATION, MATERIALIZER]
    required_paths.extend(ROOT / rel for rel in EXPECTED_PAYLOAD_PARTS)
    for path in required_paths:
        if not path.is_file():
            errors.append(f"missing:{path.relative_to(ROOT)}")

    artifact: dict = {}
    if MANIFEST.is_file():
        try:
            artifact = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"artifact_manifest_parse:{exc}")

        if artifact.get("schema_version") != 1:
            errors.append("artifact_manifest_schema_version")
        if artifact.get("status") != "READY":
            errors.append(f"artifact_not_ready:{artifact.get('status')}")

        binary = artifact.get("binary") or {}
        if binary.get("filename") != "ProjectSnapshotCollector.epf":
            errors.append(f"artifact_binary_filename_drift:{binary.get('filename')}")
        if binary.get("sha256") != EXPECTED_BINARY_SHA256:
            errors.append(f"artifact_sha256_drift:{binary.get('sha256')}")
        if binary.get("size_bytes") != EXPECTED_BINARY_SIZE:
            errors.append(f"artifact_size_drift:{binary.get('size_bytes')}")
        if binary.get("git_blob_sha1") != EXPECTED_BINARY_BLOB:
            errors.append(f"artifact_binary_blob_drift:{binary.get('git_blob_sha1')}")

        payload = artifact.get("payload") or {}
        if payload.get("encoding") != "base64_parts":
            errors.append(f"artifact_payload_encoding_drift:{payload.get('encoding')}")
        if payload.get("encoded_size_chars") != EXPECTED_ENCODED_SIZE:
            errors.append(f"artifact_payload_encoded_size_drift:{payload.get('encoded_size_chars')}")
        payload_parts = {
            row.get("path"): row.get("git_blob_sha1") for row in payload.get("parts") or []
        }
        if payload_parts != EXPECTED_PAYLOAD_PARTS:
            errors.append("artifact_payload_parts_drift")

        source = artifact.get("source") or {}
        if source.get("root") != "COLLECTOR/ONEC_RUNTIME/EPF_SOURCE":
            errors.append(f"artifact_source_root_drift:{source.get('root')}")
        if source.get("source_commit") != "0102e491e6458ee711e705486444983565b9058a":
            errors.append(f"artifact_source_commit_drift:{source.get('source_commit')}")
        if source.get("build_inputs") != EXPECTED_BUILD_INPUTS:
            errors.append("artifact_build_inputs_drift")

        acceptance = artifact.get("build_acceptance") or {}
        if acceptance.get("epf_build_open_proven") is not True:
            errors.append("artifact_epf_build_open_not_proven")
        if acceptance.get("source_export_runtime_accepted") is not True:
            errors.append("artifact_source_export_not_runtime_accepted")
        if acceptance.get("platform_version") != "8.3.27.1688":
            errors.append(f"artifact_platform_acceptance_drift:{acceptance.get('platform_version')}")
        if acceptance.get("acceptance_request_id") != "acceptance-ut-11-5-27-81-source-export-20260916-03":
            errors.append("artifact_acceptance_request_drift")

        policy = artifact.get("distribution_policy") or {}
        if policy.get("ordinary_chat_must_provide_ready_epf") is not True:
            errors.append("artifact_distribution_chat_delivery_not_required")
        if policy.get("developer_build_not_required_for_normal_use") is not True:
            errors.append("artifact_distribution_still_requires_normal_build")
        if policy.get("source_change_invalidates_binary") is not True:
            errors.append("artifact_source_change_must_invalidate_binary")
        if policy.get("integrity_verification_required_before_delivery") is not True:
            errors.append("artifact_integrity_verification_must_be_required")
        if policy.get("repository_payload_is_transport_encoded") is not True:
            errors.append("artifact_transport_encoding_policy_missing")

    if ORCHESTRATION.is_file():
        orchestration = json.loads(ORCHESTRATION.read_text(encoding="utf-8"))
        distribution = orchestration.get("collector_distribution") or {}
        expected = {
            "manifest": "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/ProjectSnapshotCollector.artifact.json",
            "payload_dir": "COLLECTOR/ONEC_RUNTIME/DISTRIBUTION/PAYLOAD",
            "materialized_filename": "ProjectSnapshotCollector.epf",
            "integrity_tool": "TOOLS/materialize_project_snapshot_collector.py",
            "normal_delivery": "CHAT_PROVIDES_VERIFIED_EPF_WITH_PLAN",
        }
        for key, value in expected.items():
            if distribution.get(key) != value:
                errors.append(f"orchestration_distribution_drift:{key}:{distribution.get(key)}")
        if distribution.get("ordinary_developer_build_required") is not False:
            errors.append("orchestration_normal_developer_build_must_be_false")

        responsibilities = set(orchestration.get("chat_responsibilities") or [])
        for required in [
            "retrieve repository-pinned ProjectSnapshotCollector payload",
            "verify collector artifact manifest, payload Git blob identities, reconstructed binary SHA-256/size/blob identity and build-input Git blob binding before delivery",
            "materialize and provide ProjectSnapshotCollector.epf to the developer when collection is required",
            "provide collector and plan together instead of making the developer build or locate the collector",
        ]:
            if required not in responsibilities:
                errors.append(f"orchestration_chat_distribution_responsibility_missing:{required}")

        collector_acceptance = orchestration.get("collector_artifact_acceptance") or {}
        if collector_acceptance.get("manifest_status_must_be") != "READY":
            errors.append("orchestration_collector_manifest_ready_required")
        if collector_acceptance.get("payload_git_blobs_must_match") is not True:
            errors.append("orchestration_collector_payload_identity_required")
        if collector_acceptance.get("reconstructed_binary_sha256_size_and_git_blob_must_match") is not True:
            errors.append("orchestration_collector_binary_identity_required")
        if collector_acceptance.get("declared_build_input_git_blobs_must_match") is not True:
            errors.append("orchestration_collector_build_input_identity_required")

        forbidden = set(orchestration.get("developer_must_not_be_required_to") or [])
        for required in [
            "clone the skill repository merely to obtain the collector",
            "build ProjectSnapshotCollector.epf for ordinary collection",
            "run build_epf.ps1 for ordinary collection",
            "keep a local collector copy between unrelated tasks",
            "understand or reconstruct repository payload encoding",
        ]:
            if required not in forbidden:
                errors.append(f"orchestration_developer_distribution_ux_regression:{required}")

    if MATERIALIZER.is_file() and MANIFEST.is_file():
        proc = run_materializer(MANIFEST)
        if proc.returncode != 0:
            errors.append(f"collector_materializer_failed:{proc.stdout or proc.stderr}")
        else:
            try:
                materialized = json.loads(proc.stdout)
                if materialized.get("result") != "PASS":
                    errors.append("collector_materializer_result_not_pass")
                if materialized.get("sha256") != EXPECTED_BINARY_SHA256:
                    errors.append("collector_materializer_sha_drift")
                if materialized.get("size_bytes") != EXPECTED_BINARY_SIZE:
                    errors.append("collector_materializer_size_drift")
                if materialized.get("git_blob_sha1") != EXPECTED_BINARY_BLOB:
                    errors.append("collector_materializer_blob_drift")
                verified_payload = {
                    row["path"]: row["git_blob_sha1"]
                    for row in materialized.get("verified_payload_parts") or []
                }
                if verified_payload != EXPECTED_PAYLOAD_PARTS:
                    errors.append("collector_materializer_payload_binding_drift")
                verified_inputs = {
                    row["path"]: row["git_blob_sha1"]
                    for row in materialized.get("verified_build_inputs") or []
                }
                if verified_inputs != EXPECTED_BUILD_INPUTS:
                    errors.append("collector_materializer_build_input_drift")
            except Exception as exc:
                errors.append(f"collector_materializer_json:{exc}")

        if artifact:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                output_path = tmp_path / "ProjectSnapshotCollector.epf"
                output_proc = run_materializer(MANIFEST, output_path)
                if output_proc.returncode != 0 or not output_path.is_file():
                    errors.append("collector_materializer_output_failed")
                else:
                    output_bytes = output_path.read_bytes()
                    if len(output_bytes) != EXPECTED_BINARY_SIZE:
                        errors.append("collector_materialized_output_size_drift")
                    if hashlib.sha256(output_bytes).hexdigest() != EXPECTED_BINARY_SHA256:
                        errors.append("collector_materialized_output_sha_drift")
                    if git_blob_sha1(output_bytes) != EXPECTED_BINARY_BLOB:
                        errors.append("collector_materialized_output_blob_drift")

                bad_binary = json.loads(json.dumps(artifact))
                bad_binary["binary"]["sha256"] = "0" * 64
                bad_binary_path = tmp_path / "bad-binary.json"
                bad_binary_path.write_text(json.dumps(bad_binary, ensure_ascii=False), encoding="utf-8")
                if run_materializer(bad_binary_path).returncode == 0:
                    errors.append("collector_materializer_negative_control_bad_binary_not_rejected")

                bad_source = json.loads(json.dumps(artifact))
                first_source = next(iter(bad_source["source"]["build_inputs"]))
                bad_source["source"]["build_inputs"][first_source] = "0" * 40
                bad_source_path = tmp_path / "bad-source.json"
                bad_source_path.write_text(json.dumps(bad_source, ensure_ascii=False), encoding="utf-8")
                if run_materializer(bad_source_path).returncode == 0:
                    errors.append("collector_materializer_negative_control_bad_source_not_rejected")

                bad_payload = json.loads(json.dumps(artifact))
                bad_payload["payload"]["parts"][0]["git_blob_sha1"] = "0" * 40
                bad_payload_path = tmp_path / "bad-payload.json"
                bad_payload_path.write_text(json.dumps(bad_payload, ensure_ascii=False), encoding="utf-8")
                if run_materializer(bad_payload_path).returncode == 0:
                    errors.append("collector_materializer_negative_control_bad_payload_not_rejected")

    if README.is_file():
        readme = README.read_text(encoding="utf-8")
        for anchor in [
            "Canonical machine identity is `ProjectSnapshotCollector.artifact.json`",
            "Normative ownership:",
            "KNOWLEDGE/PROJECT_SNAPSHOT_COLLECTOR_DISTRIBUTION.md",
            "WORKFLOW/PROJECT_SNAPSHOT_CHAT_ORCHESTRATION.json",
        ]:
            if anchor not in readme:
                errors.append(f"distribution_readme_ownership_missing:{anchor}")
        for duplicated_policy_anchor in [
            "The developer must not be required to rebuild the EPF",
            "chat should provide the developer with two ready-to-use files",
        ]:
            if duplicated_policy_anchor in readme:
                errors.append(f"distribution_readme_must_not_duplicate_chat_policy:{duplicated_policy_anchor}")

    if KNOWLEDGE.is_file():
        knowledge = KNOWLEDGE.read_text(encoding="utf-8")
        for anchor in [
            "Ordinary developers must receive a ready `ProjectSnapshotCollector.epf` from chat",
            "treat this as a **skill distribution defect**",
            "build-input Git blob",
        ]:
            if anchor not in knowledge:
                errors.append(f"distribution_knowledge_missing:{anchor}")

    print(json.dumps({"result": "PASS" if not errors else "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
