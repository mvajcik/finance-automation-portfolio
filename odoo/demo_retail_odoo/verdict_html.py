#!/usr/bin/env python3
"""One HTML page for the week: verdict, the checks, the bills due, the bank open items.

    python3 -m demo_retail_odoo.verdict_html out/weekly-pack-2026-W39-checks.json [out/weekly-verdict-2026-W39.html]

Reads only the checks JSON written by weekly_pack.py (no Odoo connection), so the page shows
exactly what was checked on the finished file. Standard library only.
"""
import html
import json
import sys
from pathlib import Path

CSS = """
body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1b1b1b}
h1{font-size:1.5rem;margin-bottom:.2rem} h2{font-size:1.1rem;margin-top:1.6rem;border-bottom:1px solid #ddd;padding-bottom:.2rem}
.verdict{display:inline-block;padding:.35rem .9rem;border-radius:4px;font-weight:700;color:#fff}
.RELEASED{background:#1a7f37} .BLOCKED{background:#b42318}
table{border-collapse:collapse;width:100%;font-size:.92rem} th,td{border:1px solid #e3e3e3;padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#f6f6f6} td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.pass{color:#1a7f37;font-weight:700} .fail{color:#b42318;font-weight:700} .muted{color:#666;font-size:.85rem}
"""


def esc(x):
    return html.escape(str(x))


def render(d):
    v = d["verdict"]
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Weekly verdict {esc(d['week'])}</title>"
           f"<style>{CSS}</style></head><body>",
           f"<h1>Demo Retail s.r.o. — payment week {esc(d['week'])}</h1>",
           f"<p><span class='verdict {v}'>{v}</span> &nbsp; <span class='muted'>weekly pack <code>{esc(d['file'])}</code>, "
           f"read back from the saved file and tied to Odoo</span></p>"]
    if d.get("tamper"):
        out.append(f"<p class='fail'>Tamper applied to the finished file: {esc(d['tamper'])}</p>")
    out.append("<h2>Checks on the finished file</h2><table><tr><th>Check</th><th>Result</th></tr>")
    for c in d["checks"]:
        cls = "pass" if c["pass"] else "fail"
        detail = "" if c["pass"] else f"<div class='muted'>{esc(c['detail'])}</div>"
        out.append(f"<tr><td>{esc(c['name'])}{detail}</td><td class='{cls}'>{'PASS' if c['pass'] else 'FAIL'}</td></tr>")
    out.append("</table>")
    out.append("<h2>Bills due this week</h2><table><tr><th>Reference</th><th>Vendor</th><th>Due</th><th>Store</th>"
               "<th class='n'>Gross EUR</th><th class='n'>Open EUR</th><th>State</th></tr>")
    for b in d["week_bills"]:
        out.append(f"<tr><td>{esc(b['ref'])}</td><td>{esc(b['vendor'])}</td><td>{esc(b['due'])}</td><td>{esc(', '.join(b['stores']))}</td>"
                   f"<td class='n'>{esc(b['total'])}</td><td class='n'>{esc(b['open'])}</td><td>{esc(b['state'])}</td></tr>")
    tot = sum(float(b["total"]) for b in d["week_bills"]); op = sum(float(b["open"]) for b in d["week_bills"])
    out.append(f"<tr><th colspan='4'>Total</th><th class='n'>{tot:.2f}</th><th class='n'>{op:.2f}</th><th></th></tr></table>")
    out.append(f"<p>Open payables, all weeks: <b>{esc(d['open_payables_total'])} EUR</b></p>")
    out.append("<h2>Bank</h2>")
    for s in d["statements"]:
        out.append(f"<p><b>{esc(s['name'])}</b>: opening {esc(s['opening'])} → closing {esc(s['closing'])} EUR · "
                   f"{s['lines']} lines, {s['reconciled']} matched to bills, {len(s['open_items'])} open items</p>")
        if s["open_items"]:
            out.append("<table><tr><th>Date</th><th class='n'>Amount EUR</th><th>Bank text</th><th>Reason (proposed, a person accepts it)</th></tr>")
            for i in s["open_items"]:
                out.append(f"<tr><td>{esc(i['date'])}</td><td class='n'>{esc(i['amount'])}</td><td>{esc(i['text'])}</td><td>{esc(i['reason'])}</td></tr>")
            out.append("</table>")
    out.append("<h2>Cost per store (net, from the analytic lines)</h2><table><tr><th>Month / store</th><th class='n'>EUR</th></tr>")
    for k, v in d["stores"].items():
        out.append(f"<tr><td>{esc(k)}</td><td class='n'>{esc(v)}</td></tr>")
    out.append(f"<tr><th>Ledger expense, all lines</th><th class='n'>{esc(d['ledger_expense'])}</th></tr></table>")
    out.append("<p class='muted'>Fictional company and generated data. Odoo 17 Community; the CAMT import and the matching "
               "are the repository's own scripts over the ORM.</p></body></html>")
    return "\n".join(out)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    src = Path(argv[0] if argv else "out/weekly-pack-2026-W39-checks.json")
    d = json.loads(src.read_text(encoding="utf-8"))
    dest = Path(argv[1]) if len(argv) > 1 else src.with_name(f"weekly-verdict-{d['week']}.html")
    dest.write_text(render(d), encoding="utf-8")
    print(f"{dest}: {d['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
