"""Shared check result: a named list of PASS/FAIL lines with evidence."""
from dataclasses import dataclass, field


@dataclass
class Check:
    code: str
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Result:
    checks: list = field(default_factory=list)

    @property
    def ok(self):
        return all(c.ok for c in self.checks)

    def add(self, code, name, problems):
        self.checks.append(Check(code, name, not problems, "; ".join(problems[:5])))

    def failed(self):
        return {c.code for c in self.checks if not c.ok}


def print_report(title, status, *results):
    print(f"\n== {title} ==")
    for res in results:
        if res is None:
            continue
        for c in res.checks:
            print(f"  {'PASS' if c.ok else 'FAIL'}  {c.code}  {c.name}" + (f"  -> {c.detail}" if c.detail else ""))
    print(f"  STATUS: {status}")
