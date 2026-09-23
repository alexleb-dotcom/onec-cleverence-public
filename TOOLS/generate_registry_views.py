#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, json, sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rule_registry import ROOT, load_registry, generated_profile_index, generated_detailed_profiles, generated_semantic_markdown, generated_requirements_index, generated_requirements_semantic_markdown, generated_proof_policy_index

TARGETS = {
    "PROFILES/INDEX.json": lambda r: json.dumps(generated_profile_index(r), ensure_ascii=False, indent=2)+"\n",
    "KNOWLEDGE/MECHANISM_REVIEW_PROFILES.json": lambda r: json.dumps(generated_detailed_profiles(r), ensure_ascii=False, indent=2)+"\n",
    "TESTS/SEMANTIC_REGRESSION_CLASSES.md": generated_semantic_markdown,
    "REQUIREMENTS/INDEX.json": lambda r: json.dumps(generated_requirements_index(r), ensure_ascii=False, indent=2)+"\n",
    "TESTS/REQUIREMENTS_SEMANTIC_CLASSES.md": generated_requirements_semantic_markdown,
    "KNOWLEDGE/PROOF_POLICY_INDEX.json": lambda r: json.dumps(generated_proof_policy_index(r), ensure_ascii=False, indent=2)+"\n",
}


def render(registry):
    return {rel:fn(registry) for rel,fn in TARGETS.items()}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args=ap.parse_args()
    registry=load_registry()
    outputs=render(registry)
    drift=[]
    for rel,text in outputs.items():
        path=ROOT/rel
        if args.check:
            actual=path.read_text(encoding="utf-8-sig") if path.exists() else None
            if actual != text:
                drift.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    if args.check:
        print(json.dumps({"result":"PASS" if not drift else "FAIL","drift":drift}, ensure_ascii=False, indent=2))
        raise SystemExit(0 if not drift else 2)
    print(json.dumps({"result":"PASS","written":sorted(outputs)}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
