#!/usr/bin/env python3
"""Canonical fail-closed release gate.

All final-verdict trust-boundary policy is enforced inside release_gate_core.evaluate
so importing the core cannot produce a stronger verdict than this CLI wrapper.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json

from release_gate_core import evaluate
from release_intake import load_intake


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--plan",required=True); ap.add_argument("--ledger",required=True); ap.add_argument("--intake"); ap.add_argument("--output")
    a=ap.parse_args(); plan=json.loads(Path(a.plan).read_text(encoding="utf-8-sig")); ledger=json.loads(Path(a.ledger).read_text(encoding="utf-8-sig")); intake=load_intake(a.intake) if a.intake else None; result=evaluate(plan,ledger,external_intake=intake)
    out=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if a.output:Path(a.output).write_text(out,encoding="utf-8")
    print(out,end=""); raise SystemExit(0 if result["result"]=="PASS" else 2)

if __name__=="__main__":main()
