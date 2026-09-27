#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
results={}; errors=[]

def record(case,ok,details):
    key=f'cold_start:{case}'
    results[key]={"pass":bool(ok),"details":details}
    if not ok:errors.append({"case":key,"details":details})

required_files=['README_FIRST.md','README.md','SKILL.md','PATTERNS/README.md','PATTERNS/INDEX.json','TOOLS/pattern_locator.py','TOOLS/artifact_corpus.py','TOOLS/build_project_bootstrap.py','TOOLS/skill_freshness.py','KNOWLEDGE/PROJECT_BOOTSTRAP.md','KNOWLEDGE/SKILL_FRESHNESS.md','KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md','TESTS/TERMINOLOGY_CONTRACT_CASES.json','TESTS/run_skill_freshness_regression.py']
missing=[x for x in required_files if not (ROOT/x).is_file()]
record('entrypoint_files',not missing,{'missing':missing})

first=(ROOT/'README_FIRST.md').read_text(encoding='utf-8') if (ROOT/'README_FIRST.md').is_file() else ''
readme=(ROOT/'README.md').read_text(encoding='utf-8') if (ROOT/'README.md').is_file() else ''
fresh=(ROOT/'KNOWLEDGE/SKILL_FRESHNESS.md').read_text(encoding='utf-8') if (ROOT/'KNOWLEDGE/SKILL_FRESHNESS.md').is_file() else ''
patterns=(ROOT/'PATTERNS/README.md').read_text(encoding='utf-8') if (ROOT/'PATTERNS/README.md').is_file() else ''
terminology=(ROOT/'KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md').read_text(encoding='utf-8') if (ROOT/'KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md').is_file() else ''
terminology_cases=json.loads((ROOT/'TESTS/TERMINOLOGY_CONTRACT_CASES.json').read_text(encoding='utf-8')) if (ROOT/'TESTS/TERMINOLOGY_CONTRACT_CASES.json').is_file() else {'cases':[]}
low=first.lower()
readme_low=readme.lower()

# A plain skill URL must identify repository role before any project-specific inference.
role_ok='UNIVERSAL_SKILL_REPOSITORY' in first and 'not' in low and 'target' in low and 'project' in low
record('repository_role',role_ok,{'role_marker':'UNIVERSAL_SKILL_REPOSITORY' in first})

# With only the skill URL, the model must not fabricate a project/baseline/context.
no_project_tokens=['target_project_identified = false','project_context_invented = false','next_needed = target project/artifact + task']
no_project_ok=all(token in first for token in no_project_tokens)
record('no_project_invention',no_project_ok,{'missing':[x for x in no_project_tokens if x not in first]})

# Bootstrap should be source-first and ask only after deriving facts.
sequence=['TOOLS/artifact_corpus.py','TOOLS/build_project_bootstrap.py','derive project facts from source','request only material unresolved project contracts','persist PROJECT_CONTEXT']
record('source_first_sequence',all(x in first for x in sequence),{'missing':[x for x in sequence if x not in first]})

# Context-budget defense: evidence stores remain useful, but are never default-recursively loaded.
# Internal-full repositories may describe ARCHIVE as ARCHIVE_ONLY; shareable cores may instead state that
# project-specific history is physically outside the distributed tree. In both forms README_FIRST must
# preserve the on-demand/not-obsolete evidence semantics.
readme_archive_policy=(
    'ARCHIVE_ONLY' in readme
    or ('project-specific historical evidence belongs outside the shareable repository tree' in readme_low and 'ARCHIVE/**' in readme)
)
budget_ok='Do **not** recursively load `ARCHIVE/**`' in first and 'routed/on-demand evidence' in first and readme_archive_policy and 'not default-loaded' in low and 'not needed' in low
record('bounded_context',budget_ok,{'archive_bulk_forbidden':'Do **not** recursively load `ARCHIVE/**`' in first,'readme_archive_policy':readme_archive_policy,'archive_not_obsolete':'not default-loaded' in low and 'not needed' in low})

# Implementation-shape examples are a separate non-evidence layer. Regression fixtures are never precedents.
pattern_tokens=['PATTERNS/**','ILLUSTRATIVE_PATTERN','evidence_role=NONE','copy_policy=ADAPT_ONLY','TESTS/fixtures/**','never implementation precedent','TOOLS/pattern_locator.py','load only the matched good/bad pair']
pattern_haystack=(first+'\n'+patterns).lower()
pattern_ok=all(x.lower() in pattern_haystack for x in pattern_tokens)
record('pattern_layer_isolation',pattern_ok,{'missing':[x for x in pattern_tokens if x.lower() not in pattern_haystack]})

# Strict terminology must be loaded on every normal bootstrap and remain fail-closed.
terminology_tokens=[
    'KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md',
    'firm-1C-authored material',
    'Everything outside that boundary is «доработка»',
]
terminology_loaded=('KNOWLEDGE/ONEC_TERMINOLOGY_CONTRACT.md' in first and 'ONEC_TERMINOLOGY_CONTRACT.md' in (ROOT/'SKILL.md').read_text(encoding='utf-8') and all(x in (first+'\n'+terminology) for x in terminology_tokens))
record('terminology_contract_loaded',terminology_loaded,{'missing':[x for x in terminology_tokens if x not in (first+'\n'+terminology)]})

# Canonical provenance cases prevent chats from broadening «типовой» to partner/vendor/customer code.
def classify_terminology(row):
    kind=row.get('artifact_kind')
    authored=row.get('authored_by_firm_1c')
    released=row.get('present_in_official_1c_release')
    matches=row.get('matches_referenced_release')
    if authored is None or released is None:
        return 'NOT_PROVEN_AS_TYPICAL'
    if kind=='platform_api':
        return 'PLATFORM_NOT_TYPICAL_CODE'
    if kind=='third_party_vendor_stock':
        return 'VENDOR_STOCK_NOT_TYPICAL_1C'
    if kind=='reference_source' and authored and released and not matches:
        return 'REFERENCE_NOT_TARGET_TYPICAL'
    if kind=='configuration' and authored and released and not matches:
        return 'BASED_ON_TYPICAL_WITH_CUSTOMIZATIONS'
    if kind=='modified_typical_module' and authored and released and not matches:
        return 'TYPICAL_WITH_CUSTOMIZATIONS'
    if authored and released and matches:
        return 'TYPICAL_1C'
    return 'CUSTOMIZATION'

term_failures=[]
for row in terminology_cases.get('cases',[]):
    actual=classify_terminology(row)
    if actual!=row.get('expected'):
        term_failures.append({'id':row.get('id'),'expected':row.get('expected'),'actual':actual})
record('terminology_classification_cases',bool(terminology_cases.get('cases')) and not term_failures,{'count':len(terminology_cases.get('cases',[])),'failures':term_failures})

# The normal README must contain the actual executable empty-chat path, not only prose in README_FIRST.
readme_tokens=['## New project / empty chat bootstrap','TOOLS/artifact_corpus.py','TOOLS/build_project_bootstrap.py','PROJECT_CONTEXT']
record('readme_bootstrap_contract',all(x in readme for x in readme_tokens),{'missing':[x for x in readme_tokens if x not in readme]})

# Skill repository conventions must never leak into a target project.
convention_ok='never copy author/company/date/naming conventions from this universal repository into a project' in low
record('project_convention_isolation',convention_ok,{'isolated':convention_ok})

# Missing target evidence is a precise next input, not a generic questionnaire or a skill-maintenance invitation.
next_input_ok='request the target repository/artifact plus the task' in low and 'generic questioning' in low
record('precise_next_input',next_input_ok,{'precise_request':next_input_ok})

# A fresh task may have access to memory, but previous-chat facts are not project evidence unless continuation is explicit.
memory_tokens=['untrusted candidate context','user explicitly asks to continue/reuse','cross_chat_context_used_as_evidence = false']
memory_ok=all(x in low for x in [memory_tokens[0],memory_tokens[1]]) and memory_tokens[2] in first
record('cross_chat_context_isolation',memory_ok,{'missing':[x for x in memory_tokens if x not in (low if x!=memory_tokens[2] else first)]})

# Branch/tag/release/commit namespaces must not be conflated when reporting Git state.
ref_tokens=['branch','tag','release','commit','absence of a branch does not prove absence of a same-named tag or release']
ref_ok=all(x in low for x in ref_tokens)
record('git_ref_namespace_isolation',ref_ok,{'missing':[x for x in ref_tokens if x not in low]})

# A URL-only cold start is not permission to audit repository administration or default into maintaining the skill.
admin_tokens=['do not turn a plain skill-url cold start into repository-administration work','repository_admin_audit_started = false','skill_maintenance_assumed = false','do not audit permissions, branches, tags, releases, ci history or propose changing the skill itself']
admin_ok=all(x in low for x in [admin_tokens[0],admin_tokens[3]]) and all(x in first for x in admin_tokens[1:3])
record('no_repository_admin_scope_drift',admin_ok,{'missing':[x for x in admin_tokens if x not in (first if '=' in x else low)]})

# The first-turn behavioral oracle should be short: identify skill, identify missing target, request target + task.
first_turn_tokens=['## First-response contract for URL-only cold start','Confirm: this is the universal 1C + Cleverence skill repository.','Confirm: no target project has been identified yet.','Request: target project/repository/artifact + concrete task.']
first_turn_ok=all(x in first for x in first_turn_tokens)
record('minimal_first_response_contract',first_turn_ok,{'missing':[x for x in first_turn_tokens if x not in first]})

# New chats establish an exact skill SHA internally; long-lived chats must use diff-first refresh rather than user reminders/full reload.
freshness_tokens=['KNOWLEDGE/SKILL_FRESHNESS.md','loaded_sha','new substantive','current_sha == loaded_sha','SHA check → diff → task-impact reload','skill_freshness_state_recorded = true','reread the repository']
freshness_ok=all(x in first for x in freshness_tokens[:4]) and all(x in (first+fresh) for x in freshness_tokens[4:])
record('skill_freshness_bootstrap',freshness_ok,{'missing':[x for x in freshness_tokens if x not in (first if x in freshness_tokens[:4] else first+fresh)]})

# Freshness bookkeeping must remain invisible on the minimal URL-only first response unless it materially matters.
quiet_freshness='Do not clutter the first response with SHA/Git administration' in first and 'do not report this bookkeeping in the first response unless relevant' in low
record('freshness_does_not_pollute_first_turn',quiet_freshness,{'quiet':quiet_freshness})

expected_behavior={
    'input':'only the universal skill repository URL',
    'expected_first_turn':{
        'identify_repository_as_skill':True,
        'treat_repository_as_target_project':False,
        'invent_project_context':False,
        'use_cross_chat_context_as_project_evidence':False,
        'bulk_load_archive':False,
        'start_repository_admin_audit':False,
        'assume_skill_maintenance_task':False,
        'conflate_branch_tag_release_commit':False,
        'record_exact_loaded_skill_sha_internally':True,
        'report_internal_freshness_bookkeeping_by_default':False,
        'request_next':'target repository/artifact + task'
    },
    'when_target_is_available':[
        'physical inventory',
        'project bootstrap',
        'derive facts',
        'request only material gaps',
        'persist PROJECT_CONTEXT',
        'task requirements',
        'technical review plan'
    ],
    'implementation_guidance':[
        'search PATTERNS by intent when shape guidance is useful',
        'never use TESTS fixtures as implementation precedent',
        'exact source still proves concrete contract'
    ],
    'later_substantive_task':[
        'resolve tracked skill SHA',
        'compare with loaded_sha',
        'if changed inspect diff',
        'reload only task-impacting changes',
        'reroute/revalidate affected proof',
        'advance loaded_sha only after refresh'
    ]
}

out={"result":"PASS" if not errors else "FAIL","errors":errors,"results":results,"behavioral_oracle":expected_behavior,"note":"This is a deterministic cold-start contract test. It does not spawn a second LLM process; literal model behavior must still be sampled after the entrypoint reaches the default branch."}
print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
