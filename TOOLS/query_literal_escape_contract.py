#!/usr/bin/env python3
"""Exact identity for query literal-escape blocking findings.

This is a narrow binding helper for the existing QUERY owner. It does not define
an independent rule family or release gate.
"""
from __future__ import annotations

import hashlib
import json

RULE_ID="QUERY"
CHECK_ID="QUERY_LITERAL_ESCAPE_SANITY"
FINDING_TYPE="QUERY_LITERAL_ESCAPE_CORRUPTION"
ANALYZER_TOOL="TOOLS/analyze_onec_bsl.py"
ANALYZER_PROPERTY="STATIC:ONEC_BSL"


def _canon(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def finding_sha256(finding):
    return hashlib.sha256(_canon(finding).encode("utf-8")).hexdigest()


def blocking_finding_id(artifact,candidate_sha256,finding):
    finding_sha=finding_sha256(finding)
    material={
        "rule_id":RULE_ID,
        "check_id":CHECK_ID,
        "finding_type":FINDING_TYPE,
        "artifact":artifact,
        "candidate_sha256":candidate_sha256,
        "finding_sha256":finding_sha,
    }
    digest=hashlib.sha256(_canon(material).encode("utf-8")).hexdigest()
    return f"BLOCKING_FINDING:{RULE_ID}:{CHECK_ID}:{FINDING_TYPE}:{digest[:20]}",finding_sha


def blocking_row(artifact,candidate_sha256,report_id,report_output_sha256,finding):
    finding_id,finding_sha=blocking_finding_id(artifact,candidate_sha256,finding)
    return {
        "id":finding_id,
        "rule_id":RULE_ID,
        "check_id":CHECK_ID,
        "finding_type":FINDING_TYPE,
        "artifact":artifact,
        "candidate_sha256":candidate_sha256,
        "report_id":report_id,
        "report_output_sha256":report_output_sha256,
        "finding_sha256":finding_sha,
        "severity":"HIGH",
        "status":"BLOCKED",
        "line":finding.get("line"),
        "procedure":finding.get("procedure"),
        "function":finding.get("function"),
        "sequence":finding.get("sequence"),
        "fragment":finding.get("fragment"),
        "reason":"Literal escape-like pair remains in exact query-source bytes; fix the candidate and rerun the analyzer.",
    }
