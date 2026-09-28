#!/usr/bin/env python3
"""Build a source-first project bootstrap skeleton for a new repository/project.

This tool does not ask the user a fixed questionnaire. It inventories the supplied
corpus, records structurally proven facts, and emits only the durable project
contracts that still need evidence before implementation.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from artifact_corpus import inventory_paths, summarize, analyzable_entries

STATES=("KNOWN","DERIVED_WITH_EVIDENCE","OPEN","NOT_APPLICABLE")
DECISION_STATUSES=("ACTIVE","TEMPORARY","REVALIDATION_REQUIRED","SUPERSEDED","INVALIDATED")

AUTHOR_MARKER_VALUE_FIELDS=("ФамилияИО","Дата","НомерТЗ","пункты ТЗ")
CANONICAL_ONEC_AUTHOR_MARKER={
    "syntax_source":"SKILL_DEFAULT_1C",
    "field_order":["ФамилияИО","ПервыйБит","Дата","НомерТЗ","пункты ТЗ"],
    "organization_marker":"ПервыйБит",
    "block_open":"// ++ ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ",
    "block_close":"// -- ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ",
    "one_line":"// ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ",
    "metadata_comment":"// ФамилияИО, ПервыйБит, Дата, НомерТЗ, пункты ТЗ",
}


def _default_author_marker_value():
    return {
        "syntax_source":"SKILL_DEFAULT_1C",
        "canonical_shape":dict(CANONICAL_ONEC_AUTHOR_MARKER),
        "explicit_override_syntax":None,
        "values":{name:None for name in AUTHOR_MARKER_VALUE_FIELDS},
    }


def _missing_author_marker_values(row):
    if not isinstance(row,dict):
        return list(AUTHOR_MARKER_VALUE_FIELDS)
    if row.get("status")=="NOT_APPLICABLE":
        return []
    value=row.get("value")
    if not isinstance(value,dict):
        return [] if row.get("status") in {"KNOWN","DERIVED_WITH_EVIDENCE"} else list(AUTHOR_MARKER_VALUE_FIELDS)
    values=value.get("values")
    if not isinstance(values,dict):
        return [] if row.get("status") in {"KNOWN","DERIVED_WITH_EVIDENCE"} else list(AUTHOR_MARKER_VALUE_FIELDS)
    return [name for name in AUTHOR_MARKER_VALUE_FIELDS if not values.get(name)]


def _author_marker_gate_state(fields):
    row=(fields or {}).get("author_marker") or {}
    if row.get("status")=="NOT_APPLICABLE":
        return "AUTHOR_MARKER_READY"
    if row.get("status") in {"KNOWN","DERIVED_WITH_EVIDENCE"} and not _missing_author_marker_values(row):
        return "AUTHOR_MARKER_READY"
    return "AUTHOR_MARKER_BLOCKED"



def field(title,blocking=False,value=None,status="OPEN",evidence=None,reason=""):
    return {
        "title":title,"status":status,"blocking":bool(blocking),"value":value,
        "evidence":evidence or [],"reason":reason,
    }


def _text_corpus(corpus):
    rows=[]
    for semantic,data,origin,_ in analyzable_entries(corpus):
        for enc in ("utf-8-sig","utf-8","cp1251"):
            try:text=data.decode(enc);break
            except UnicodeDecodeError:text=None
        if text is None:text=data.decode("utf-8",errors="replace")
        rows.append((semantic,text,origin))
    return rows


def _candidate_conventions(texts):
    """Return evidence candidates only; never promote syntax to a project contract automatically."""
    author=[]; metadata=[]
    marker_patterns=[
        re.compile(r"(?im)^\s*//\s*[^\r\n]{0,100}\b\d{2}\.\d{2}\.\d{4}\b[^\r\n]*$"),
        re.compile(r"(?im)^\s*//\s*(?:Начало|Конец|Изменено|Добавлено|Доработка)\b[^\r\n]*$"),
    ]
    comment_attr=re.compile(r"(?i)(?:Комментарий|Comment)\s*[=:]\s*[\"']([^\"'\r\n]{1,200})")
    for name,text,origin in texts:
        for pattern in marker_patterns:
            for m in pattern.finditer(text):
                value=m.group(0).strip()
                if value not in {x["value"] for x in author}:author.append({"value":value,"source":origin,"path":name})
                if len(author)>=20:break
        for m in comment_attr.finditer(text):
            value=m.group(1).strip()
            if value not in {x["value"] for x in metadata}:metadata.append({"value":value,"source":origin,"path":name})
            if len(metadata)>=20:break
    return {"author_marker_candidates":author,"metadata_comment_candidates":metadata}


def _requests(fields,artifact_model,candidates):
    requests=[]
    def add(rid,what,why,controls,blocking=True):
        requests.append({"id":rid,"status":"REQUEST_REQUIRED","blocking":blocking,"what":what,"why":why,"controls":controls})
    if fields["actual_deployed_baseline"]["status"]=="OPEN":
        add("DEPLOYED_BASELINE","точный deployed/user baseline или подтверждение, что подключённый commit/архив является им","без этого reference/history нельзя безопасно считать базой изменений","code output, metadata/public-interface change and exact delivery")
    if artifact_model.get("role") in {"UNKNOWN","MIXED_ARTIFACT"}:
        add("ARTIFACT_ROLE","назначение входного артефакта: deployed config/export, runtime database, patch, reference или mixed snapshot","структура сама по себе не доказывает назначение смешанного/неизвестного корпуса","authoritative source root and exact delivery",False)
    if fields["modification_policy"]["status"]=="OPEN":
        add("MODIFICATION_POLICY","какие существующие проектные/сторонние доработки и типовые поверхности разрешено менять","до разрешения действует fail-safe: только минимальная задача, без попутного рефакторинга","code output and changed project surfaces")
    if fields["metadata_attribution"]["status"]=="OPEN":
        evidence="; найденные кандидаты: "+", ".join(x["value"] for x in candidates["metadata_comment_candidates"][:3]) if candidates["metadata_comment_candidates"] else ""
        add("METADATA_ATTRIBUTION","актуальный формат поля Comment/Комментарий для новых метаданных либо подтверждённый пример"+evidence,"формат является проектным контрактом и не должен угадываться","new/changed metadata only",False)
    if _author_marker_gate_state(fields)=="AUTHOR_MARKER_BLOCKED":
        missing=_missing_author_marker_values(fields["author_marker"])
        missing_text=", ".join(missing) if missing else "применимость/явный override"
        add(
            "AUTHOR_MARKER",
            "недостающие значения AUTHOR_MARKER: "+missing_text+". Канонический 1C формат уже задан Skill; ПервыйБит фиксирован и формат повторно не запрашивается",
            "без этих значений нельзя корректно отрендерить обязательный marker; значения нельзя выдумывать, а явный project/user override нужно сохранить дословно",
            "1C implementation/development entry",
        )
    if fields["technical_comment"]["status"]=="OPEN":
        add("TECHNICAL_COMMENT_POLICY","правило новых технических комментариев в коде: когда они обязательны, какой стиль ожидается и какие комментарии считаются избыточными; допустим ответ «специальных требований нет»","без этого модель может молча применить собственный стиль комментариев или не добавить требуемые проектом пояснения","final changed code")
    if fields["existing_comment_policy"]["status"]=="OPEN":
        add("EXISTING_COMMENT_POLICY","можно ли изменять/удалять существующие комментарии и исторические маркеры либо их нужно сохранять дословно","комментарии могут хранить attribution/history и не являются безопасной поверхностью для автоматической нормализации","editing existing code")
    if fields["public_interface_comment"]["status"]=="OPEN":
        add("PUBLIC_INTERFACE_COMMENT_POLICY","если задача создаёт или меняет экспортные/публичные процедуры и функции — нужен ли проектный формат описания параметров, результата, побочных эффектов и контекста; если таких интерфейсов в задаче нет, поле можно отметить NOT_APPLICABLE","это условный контракт: он не должен блокировать нерелевантную задачу, но обязан быть разрешён до изменения публичного интерфейса","new/changed public interfaces",False)
    if fields["delivery_contract"]["status"]=="OPEN":
        add("DELIVERY_CONTRACT","ожидаемая форма поставки и точный смысл FULL_COMPARE/PATCH для проекта","одинаковая логика может поставляться в разных штатных layout","exact final artifact/delivery only",False)
    return requests


def _capability_gates(fields):
    """Return action-specific fail-closed gates instead of one global questionnaire gate.

    An unresolved metadata or delivery convention must not block a code-only output,
    while it still blocks the capability it actually controls. This keeps bootstrap
    fail-closed without turning every future task into an all-fields prerequisite.
    """
    requirements={
        "code_output_allowed":[
            "actual_deployed_baseline","modification_policy","author_marker",
            "technical_comment","existing_comment_policy",
        ],
        "metadata_change_allowed":[
            "actual_deployed_baseline","modification_policy","metadata_attribution",
            "author_marker","technical_comment","existing_comment_policy",
        ],
        "public_interface_change_allowed":[
            "actual_deployed_baseline","modification_policy","author_marker",
            "technical_comment","existing_comment_policy","public_interface_comment",
        ],
        "delivery_allowed":[
            "artifact_role","actual_deployed_baseline","delivery_contract",
        ],
    }
    result={}
    for capability,field_ids in requirements.items():
        open_fields=[]
        for fid in field_ids:
            if fid=="author_marker":
                if _author_marker_gate_state(fields)=="AUTHOR_MARKER_BLOCKED":
                    open_fields.append(fid)
                continue
            if fields.get(fid,{}).get("status")=="OPEN":
                open_fields.append(fid)
        result[capability]={
            "allowed":not open_fields,
            "blocking_open_fields":open_fields,
            "requires":field_ids,
        }
    return result


def build(paths):
    corpus=inventory_paths(paths); inv=summarize(corpus); model=inv["artifact_model"]; texts=_text_corpus(corpus); candidates=_candidate_conventions(texts)
    source_fingerprint=hashlib.sha256(json.dumps([(x.physical_path,x.size,x.sha256) for x in corpus["entries"]],ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()
    fields={
        "source_inventory":field("Physical/container inventory",False,inv,"DERIVED_WITH_EVIDENCE",[{"kind":"MACHINE","ref":"artifact_corpus inventory"}]),
        "artifact_role":field("Artifact family/role/layout",model.get("role") in {"UNKNOWN","MIXED_ARTIFACT"},model, "DERIVED_WITH_EVIDENCE" if model.get("confidence")=="PROVEN_BY_STRUCTURE" else "OPEN",[{"kind":"MACHINE","ref":"artifact structural classification"}]),
        "actual_deployed_baseline":field("Actual deployed/user baseline identity",True),
        "modification_policy":field("Allowed/protected surfaces and unrelated-refactor policy",True),
        "metadata_attribution":field("Metadata Comment/Комментарий attribution contract",False),
        "author_marker":field("1C AUTHOR_MARKER values / explicit override",True,_default_author_marker_value(),"OPEN",reason="Canonical Skill syntax is known; task/project values remain unresolved until bound"),
        "technical_comment":field("Technical why/invariant/constraint comment policy",True),
        "public_interface_comment":field("Public interface documentation contract",False),
        "existing_comment_policy":field("Existing comments/history marker preservation policy",True),
        "delivery_contract":field("1C/Cleverence delivery shape and compare/patch semantics",False),
        "runtime_capabilities":field("Available runtime/configurator/designer/emulator/device evidence",False),
    }
    requests=_requests(fields,model,candidates)
    capability_gates=_capability_gates(fields)
    code_gate=capability_gates["code_output_allowed"]
    blocking_open=[rid for rid,row in fields.items() if row["blocking"] and row["status"]=="OPEN"]
    return {
        "schema_version":4,
        "result":"PROJECT_BOOTSTRAP_CREATED",
        "source_fingerprint":source_fingerprint,
        "rule":"Mine repository/artifact evidence first. Ask only unresolved material project contracts. Repository access is evidence, not proof that deployed/project truth is complete. For applicable 1C work the Skill-owned AUTHOR_MARKER shape is already known: reuse bound values and ask only missing values before implementation starts. Metadata/public-interface/delivery contracts block only the capabilities they control.",
        "artifact_model":model,
        "fields":fields,
        "decision_lifecycle":{
            "contract":"KNOWLEDGE/PROJECT_CONTEXT_LIFECYCLE.md",
            "validator":"TOOLS/project_context_lifecycle.py",
            "statuses":list(DECISION_STATUSES),
            "rule":"Mutable durable project decisions require stable decision_key/status/evidence dependencies. Newer conflicting evidence or explicit project decisions supersede/invalidate/revalidate older context instead of coexisting as current truth.",
            "decisions":[],
        },
        "discovery_candidates":candidates,
        "evidence_requests":requests,
        "capability_gates":capability_gates,
        "gate":{
            "status":"BLOCKED" if not code_gate["allowed"] else ("READY_WITH_CAPABILITY_GAPS" if any(not x["allowed"] for x in capability_gates.values()) else "READY"),
            "blocking_open_fields":blocking_open,
            "author_marker_state":_author_marker_gate_state(fields),
            "implementation_allowed":code_gate["allowed"],
            "rule":"Legacy implementation_allowed mirrors code_output_allowed only. AUTHOR_MARKER_BLOCKED forbids applicable 1C implementation/development entry but still permits analysis, requirements clarification, source inspection and evidence acquisition. Metadata, public-interface and exact-delivery gaps remain capability-scoped."
        },
        "next_sequence":["inspect evidence candidates semantically","resolve/request only project fields required by the task's affected capabilities","reuse bound AUTHOR_MARKER values and request only missing values before applicable 1C implementation","persist PROJECT_CONTEXT","record/revalidate/supersede mutable project decisions","build task requirements contract","perform task-specific evidence acquisition","build technical review plan"]
    }


def compact_summary(result):
    fields=result.get("fields") or {}
    return {
        "result":result.get("result"),
        "source_fingerprint":result.get("source_fingerprint"),
        "artifact_model":result.get("artifact_model"),
        "blocking_open_fields":[fid for fid,row in fields.items() if isinstance(row,dict) and row.get("blocking") and row.get("status")=="OPEN"],
        "evidence_requests":result.get("evidence_requests") or [],
        "capability_gates":result.get("capability_gates"),
        "gate":result.get("gate"),
        "next_sequence":result.get("next_sequence"),
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="+"); ap.add_argument("--output"); ap.add_argument("--summary",action="store_true"); ap.add_argument("--full-json",action="store_true")
    a=ap.parse_args(); result=build(a.paths); out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    shown=compact_summary(result) if a.summary or (a.output and not a.full_json) else result
    print(json.dumps(shown,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
