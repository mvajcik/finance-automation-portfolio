#!/usr/bin/env python3
"""Podpis zmluvy reportu: zapíše odtlačok obsahu zmluvy a kotiev do poľa `signed`.

Každá neskoršia zmena zmluvy alebo kotvy podpis zneplatní a motor odoslanie
nepovolí, kým sa zmluva znova nepodpíše. V ukážke je podpis „demo" — v praxi
ho spúšťa človek, ktorý za čísla ručí.

Použitie: python3 tools/sign_contract.py [--profile profiles/papiernictvo2] [--check]
"""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=str(ROOT / "profiles" / "papiernictvo2"))
    ap.add_argument("--check", action="store_true", help="only verify that the signature is valid (exit 1 = invalid)")
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("engine_sign", ROOT / "pipeline" / "engine.py")
    eng = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eng)
    pdir = Path(a.profile)
    profile = json.loads((pdir / "profile.json").read_text(encoding="utf-8"))
    path = pdir / profile["contract"]
    contract = json.loads(path.read_text(encoding="utf-8"))
    sha = eng.contract_signature(pdir, contract)
    if a.check:
        ok = contract.get("signed", {}).get("sha256") == sha
        print(f"SIGNATURE: {'VALID' if ok else 'INVALID'} ({sha[:12]}…)")
        return 0 if ok else 1
    contract.setdefault("signed", {})["sha256"] = sha
    path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SIGNATURE written: {sha[:12]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
