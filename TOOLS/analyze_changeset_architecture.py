#!/usr/bin/env python3
"""Conservative whole-change-set review for 1C BSL artifacts.

The analyzer finds structural duplication *candidates* across distinct files.  It
never labels similarity as a defect: shared ownership, client/server adapters and
vendor/version boundaries remain semantic questions.  The machine result is
therefore REVIEW-only and cannot close the change-set architecture gate.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile


TEXT_EXT = {".bsl", ".os"}
DECL_RE = re.compile(
    r"^\s*(Процедура|Функция)\s+([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\((.*?)\)\s*(Экспорт)?\s*$",
    re.I,
)
END_RE = re.compile(r"^\s*Конец(?:Процедуры|Функции)\b", re.I)
IDENT_RE = re.compile(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*|\d+(?:\.\d+)?|<>|<=|>=|:=|[()\[\],.=+\-*/<>]")
CALL_RE = re.compile(r"(?<![.\wА-Яа-яЁё])([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(")
QUAL_CALL_RE = re.compile(r"\b([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\.([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\s*\(")
FIELD_RE = re.compile(r"\.\s*([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*)\b(?!\s*\()")

KEYWORDS = {x.lower() for x in """
если тогда иначе иначеесли конецесли для каждого из цикл конеццикла пока
попытка исключение конецпопытки возврат продолжить прервать новый
процедура функция конецпроцедуры конецфункции экспорт истина ложь
неопределено и или не по значение в где выбрать поместить соединение
""".split()}
IGNORED_CALLS = {x.lower() for x in {"Если", "Для", "Пока", "Новый", "Тип", "ТипЗнч", "Строка", "Число", "Дата"}}


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def _entries(path: Path):
    if path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.suffix.lower() in TEXT_EXT:
                yield item.relative_to(path).as_posix(), _decode(item.read_bytes())
        return
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if not info.is_dir() and Path(info.filename).suffix.lower() in TEXT_EXT:
                    yield info.filename, _decode(archive.read(info))
        return
    if path.is_file() and path.suffix.lower() in TEXT_EXT:
        yield path.name, _decode(path.read_bytes())
        return
    if not path.exists():
        raise FileNotFoundError(path)


def _strip_comment(line: str) -> str:
    quoted = False
    i = 0
    while i < len(line) - 1:
        if line[i] == '"':
            if quoted and i + 1 < len(line) and line[i + 1] == '"':
                i += 2
                continue
            quoted = not quoted
        if not quoted and line[i:i + 2] == "//":
            return line[:i]
        i += 1
    return line


def _parse(logical_path: str, text: str) -> list[dict]:
    lines = text.splitlines()
    routines = []
    index = 0
    while index < len(lines):
        match = DECL_RE.match(lines[index])
        if not match:
            index += 1
            continue
        kind, name, _params, exported = match.groups()
        start = index + 1
        body = []
        index += 1
        while index < len(lines) and not END_RE.match(lines[index]):
            body.append(lines[index])
            index += 1
        body_text = "\n".join(body)
        routines.append({
            "logical_path": logical_path.replace("\\", "/"),
            "kind": kind.upper(),
            "name": name,
            "export": bool(exported),
            "start_line": start,
            "end_line": index + 1,
            "body": body_text,
        })
        index += 1
    return routines


def _normalize(routine: dict) -> dict:
    clean = "\n".join(_strip_comment(line) for line in routine["body"].splitlines())
    clean = re.sub(r'"(?:""|[^"])*"', ' _STRING_ ', clean)
    calls = {f"{a.lower()}.{b.lower()}" for a, b in QUAL_CALL_RE.findall(clean)}
    calls.update(x.lower() for x in CALL_RE.findall(clean) if x.lower() not in IGNORED_CALLS)
    fields = {x.lower() for x in FIELD_RE.findall(clean)}
    preserved = KEYWORDS | {x.split(".")[-1] for x in calls} | fields
    tokens = []
    for token in IDENT_RE.findall(clean):
        low = token.lower()
        if token[0].isdigit():
            tokens.append("_NUM_")
        elif re.match(r"^[A-Za-zА-Яа-яЁё_]", token):
            tokens.append(low if low in preserved else "_ID_")
        else:
            tokens.append(token)
    controls = tuple(x for x in tokens if x in KEYWORDS)
    routine = {k: v for k, v in routine.items() if k != "body"}
    routine.update({
        "tokens": tokens,
        "calls": sorted(calls),
        "fields": sorted(fields),
        "controls": controls,
        "fingerprint": hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest(),
    })
    return routine



def _internal_pipeline_reconstruction_findings(raw_routines: list[dict]) -> list[dict]:
    """Activate review only for owner-bound reconstruction, not local query shape alone.

    A finding requires two independent classes of evidence:
      1) an owner/private-contract boundary signal; and
      2) a reconstruction/pipeline signal.
    Multiple temporary tables are one pipeline fact, not two independent facts.
    """
    findings=[]
    ident=r'[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*'
    for routine in raw_routines:
        body=routine.get("body","")
        owner_signals=[]
        reconstruction_signals=[]

        temp_tables=sorted(set(
            re.findall(r'(?i)\bПОМЕСТИТЬ\s+([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё]*)',body)
        ))
        if temp_tables:
            reconstruction_signals.append({
                "kind":"TEMP_TABLE_PIPELINE",
                "values":temp_tables[:8],
                "stage_count":len(temp_tables),
            })

        has_boundary_search=bool(
            re.search(r'(?i)\bСтрНайти\s*\(',body)
            and re.search(r'(?i)"[^"]*\b(?:ВЫБРАТЬ|ИЗ|СОЕДИНЕНИЕ|ОБЪЕДИНИТЬ|ПОМЕСТИТЬ)\b[^"]*"',body)
        )
        has_positional_slice=bool(re.search(r'(?i)\b(?:Сред|Лев|Прав)\s*\(',body))
        if has_boundary_search and has_positional_slice:
            reconstruction_signals.append({"kind":"QUERY_TEXT_POSITION_SURGERY"})

        private_named_calls=sorted({
            f"{owner}.{method}"
            for owner,method in QUAL_CALL_RE.findall(body)
            if re.search(r'(?i)(?:Внутр|Служеб|Internal|Private|Подготов|ЗаполнитьВТ|СоздатьВТ)',method)
        })
        if private_named_calls:
            owner_signals.append({
                "kind":"PRIVATE_HELPER_DEPENDENCY",
                "values":private_named_calls[:8],
            })

        # Neutral helper names are not automatically safe when a qualified owner
        # call supplies the text that is then parsed as query grammar.  This signal
        # is behavioral/dataflow-oriented and does not depend on "private" naming.
        owner_result_vars={}
        for match in re.finditer(
            rf'(?im)^\s*({ident})\s*=\s*({ident})\.({ident})\s*\([^;]*\)\s*;?\s*$',
            body,
        ):
            owner_result_vars[match.group(1).lower()]=f"{match.group(2)}.{match.group(3)}"
        parsed_owner_sources=[]
        for variable,call in owner_result_vars.items():
            if re.search(
                rf'(?i)\bСтрНайти\s*\([^;\n]*\b{re.escape(variable)}\b',
                body,
            ) and re.search(
                rf'(?i)\b(?:Сред|Лев|Прав)\s*\([^;\n]*\b{re.escape(variable)}\b',
                body,
            ):
                parsed_owner_sources.append(call)
        if parsed_owner_sources:
            owner_signals.append({
                "kind":"OWNER_QUERY_TEXT_DEPENDENCY",
                "values":sorted(set(parsed_owner_sources))[:8],
            })

        if not owner_signals or not reconstruction_signals:
            continue
        findings.append({
            "type":"INTERNAL_PIPELINE_RECONSTRUCTION_REVIEW",
            "severity":"REVIEW",
            "suggested_reuse_classification":"INTERNAL_PIPELINE_RECONSTRUCTION",
            "classification_required":[
                "PUBLIC_API_REUSE",
                "SUPPORTED_EXTENSION_POINT_REUSE",
                "INTERNAL_IMPLEMENTATION_REUSE",
                "INTERNAL_PIPELINE_RECONSTRUCTION",
            ],
            "routine":{
                "logical_path":routine["logical_path"],
                "name":routine["name"],
                "start_line":routine["start_line"],
                "end_line":routine["end_line"],
            },
            "owner_boundary_signals":owner_signals,
            "reconstruction_signals":reconstruction_signals,
            "signals":[*owner_signals,*reconstruction_signals],
            "detail":"An owner/private boundary is combined with a separate reconstruction/pipeline signal. Local temporary-table shape alone is not treated as proof of private-owner reconstruction; exact-source architecture review is still required for the detected owner-bound dependency.",
        })
    return findings

def _jaccard(left, right) -> float:
    left, right = set(left), set(right)
    if not left and not right:
        return 1.0
    return len(left & right) / len(left | right)


def _candidate_pairs(routines: list[dict]) -> set[tuple[int, int]]:
    """Generate a bounded comparison set instead of an O(n^2) corpus scan."""
    call_inverted = defaultdict(list)
    by_name = defaultdict(list)
    by_fingerprint = defaultdict(list)
    for index, routine in enumerate(routines):
        by_name[routine["name"].lower()].append(index)
        by_fingerprint[routine["fingerprint"]].append(index)
        for call in routine["calls"]:
            call_inverted[call].append(index)
    call_counts = defaultdict(int)
    for indexes in call_inverted.values():
        if len(indexes) > 60:  # ubiquitous platform calls are not discriminating.
            continue
        for pos, left in enumerate(indexes):
            for right in indexes[pos + 1:]:
                if routines[left]["logical_path"] != routines[right]["logical_path"]:
                    call_counts[tuple(sorted((left, right)))] += 1
    # Two shared calls give a useful behavioral anchor. Pure calculations with no
    # calls are still compared when names or fully normalized fingerprints match.
    pairs = {pair for pair, shared in call_counts.items() if shared >= 2}
    for groups in (by_name, by_fingerprint):
        for indexes in groups.values():
            if len(indexes) > 30:
                continue
            for pos, left in enumerate(indexes):
                for right in indexes[pos + 1:]:
                    if routines[left]["logical_path"] != routines[right]["logical_path"]:
                        pairs.add(tuple(sorted((left, right))))
    return pairs


def _scope_review(files, routine_count, finding_type, detail) -> dict:
    return {
        "result": "PASS",
        "analysis_coverage": "SCOPE_REVIEW_REQUIRED",
        "rule": "The analyzer never silently samples or treats incomplete similarity coverage as PASS.",
        "summary": {"files": files, "routines": routine_count, "changed_routines": None, "candidate_pairs": 0},
        "findings": [{"type": finding_type, "severity": "REVIEW", "detail": detail}],
    }


def analyze_sources(sources, baseline_sources=None, threshold: float = 0.80, max_routines: int = 1500, max_pairs: int = 5000) -> dict:
    raw_routines = [r for logical, text in sources for r in _parse(logical, text)]
    file_count=len({r["logical_path"] for r in raw_routines})
    if len(raw_routines) > max_routines:
        return _scope_review(
            file_count, len(raw_routines), "CHANGESET_SIMILARITY_SCOPE_TOO_BROAD",
            f"The supplied corpus has {len(raw_routines)} routines, above the explicit budget {max_routines}. Provide the actual changed BSL closure (preferred) or deliberately raise --max-routines; do not interpret this REVIEW as zero duplication.",
        )
    routines = [_normalize(r) for r in raw_routines]
    baseline_map = {}
    if baseline_sources:
        for logical, text in baseline_sources:
            for routine in _parse(logical, text):
                norm = _normalize(routine)
                baseline_map[(norm["logical_path"].lower(), norm["name"].lower())] = norm["fingerprint"]
    for routine in routines:
        key = (routine["logical_path"].lower(), routine["name"].lower())
        routine["changed"] = not baseline_sources or baseline_map.get(key) != routine["fingerprint"]

    comparison_pairs=_candidate_pairs(routines)
    if len(comparison_pairs) > max_pairs:
        return _scope_review(
            file_count, len(routines), "CHANGESET_SIMILARITY_PAIR_BUDGET_EXCEEDED",
            f"Candidate generation produced {len(comparison_pairs)} pairs, above the explicit budget {max_pairs}. Narrow to the changed dependency closure or deliberately raise --max-pairs; no pairs were silently discarded.",
        )
    findings = _internal_pipeline_reconstruction_findings(raw_routines)
    for left_index, right_index in sorted(comparison_pairs):
        left, right = routines[left_index], routines[right_index]
        if not (left["changed"] or right["changed"]):
            continue
        if min(len(left["tokens"]), len(right["tokens"])) < 12:
            continue
        length_ratio = min(len(left["tokens"]), len(right["tokens"])) / max(len(left["tokens"]), len(right["tokens"]))
        if length_ratio < 0.60:
            continue
        call_similarity = _jaccard(left["calls"], right["calls"])
        field_similarity = _jaccard(left["fields"], right["fields"])
        control_similarity = _jaccard(left["controls"], right["controls"])
        exact_shape=left["fingerprint"] == right["fingerprint"]
        same_name=left["name"].lower() == right["name"].lower()
        if not exact_shape and control_similarity < 0.55:
            continue
        if max(len(left["tokens"]), len(right["tokens"])) > 2000 and not exact_shape:
            continue
        token_similarity = 1.0 if exact_shape else SequenceMatcher(None, left["tokens"], right["tokens"], autojunk=False).ratio()
        score = 0.55 * token_similarity + 0.25 * call_similarity + 0.10 * field_similarity + 0.10 * control_similarity
        strong_structure = token_similarity >= threshold
        strong_contract = call_similarity >= 0.80 and control_similarity >= 0.75 and token_similarity >= 0.68
        if same_name and call_similarity >= 0.60 and token_similarity >= 0.72:
            strong_contract=True
        if score < threshold or not (strong_structure or strong_contract):
            continue
        findings.append({
            "type": "CROSS_OBJECT_DUPLICATION_CANDIDATE",
            "severity": "REVIEW",
            "classification_required": [
                "SAME_RESPONSIBILITY", "SAME_BUSINESS_RULE", "SAME_ALGORITHM",
                "INCIDENTAL_SIMILARITY", "INTENTIONAL_ADAPTER_DUPLICATION",
            ],
            "score": round(score, 4),
            "metrics": {
                "token_similarity": round(token_similarity, 4),
                "call_similarity": round(call_similarity, 4),
                "field_similarity": round(field_similarity, 4),
                "control_similarity": round(control_similarity, 4),
            },
            "left": {k: left[k] for k in ("logical_path", "name", "start_line", "end_line", "changed", "calls", "fields")},
            "right": {k: right[k] for k in ("logical_path", "name", "start_line", "end_line", "changed", "calls", "fields")},
            "detail": "Structural similarity is a review candidate, not proof of a defect. Establish one owner or record a concrete boundary/runtime/version justification.",
        })
    return {
        "result": "PASS",
        "analysis_coverage": "COMPLETE_FOR_SUPPLIED_CHANGESET",
        "rule": "REVIEW candidates never become defects or PASS without semantic/source evidence.",
        "summary": {
            "files": len({r["logical_path"] for r in routines}),
            "routines": len(routines),
            "changed_routines": sum(1 for r in routines if r["changed"]),
            "candidate_pairs": sum(1 for x in findings if x.get("type")=="CROSS_OBJECT_DUPLICATION_CANDIDATE"),
        },
        "findings": findings,
    }


def analyze(paths, baseline=None, threshold: float = 0.80, max_routines: int = 1500, max_pairs: int = 5000) -> dict:
    def collect(input_paths):
        collected=[]; origins={}
        for raw in input_paths:
            path=Path(raw)
            for logical,text in _entries(path):
                logical=logical.replace("\\","/")
                if logical in origins and origins[logical] != str(path):
                    prefix=(path.parent.name or path.stem) if path.is_file() else path.name
                    candidate=f"{prefix}/{logical}"; suffix=2
                    while candidate in origins:
                        candidate=f"{prefix}-{suffix}/{logical}"; suffix+=1
                    logical=candidate
                origins[logical]=str(path)
                collected.append((logical,text))
        return collected
    sources = collect(paths)
    baseline_sources = None
    if baseline:
        baseline_sources = collect(baseline)
    return analyze_sources(sources, baseline_sources, threshold, max_routines, max_pairs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--baseline", action="append", default=[])
    parser.add_argument("--threshold", type=float, default=0.80)
    parser.add_argument("--max-routines", type=int, default=1500)
    parser.add_argument("--max-pairs", type=int, default=5000)
    args = parser.parse_args()
    result = analyze(args.paths, args.baseline or None, args.threshold, args.max_routines, args.max_pairs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
