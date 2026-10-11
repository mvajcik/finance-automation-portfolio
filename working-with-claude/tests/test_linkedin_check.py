"""check.py must pass a clean draft and fail each red line (tamper per check)."""
import subprocess
import sys
from pathlib import Path

CHECK = Path(__file__).parents[1] / "skills/linkedin-post/check.py"
WORDS = " ".join(["Every payment run used to mean retyping a list into the bank."] * 9)
CLEAN = f"""---
stage: DRAFT
---
## POST (EN)
{WORDS}
#finance #automation

## VISUAL (MOCK)
MOCK DATA: Supplier 1, 1 250.00 EUR
"""


def run(tmp_path, text, *args, lists=True):
    """Runs check.py; by default with a records file, a place list and a blocklist that hit nothing."""
    d = tmp_path / "draft.md"
    d.write_text(text, encoding="utf-8")
    default = []
    if lists:
        for flag, content in (("--records", "month closed at 77 777,77"), ("--places", "Nowhereville\n"),
                              ("--blocklist", "Nobody Ltd\n")):
            if flag not in args:
                f = tmp_path / f"default{flag.strip('-')}.md"
                f.write_text(content, encoding="utf-8")
                default += [flag, str(f)]
    r = subprocess.run([sys.executable, str(CHECK), str(d), *args, *default], capture_output=True, text=True)
    return r.returncode, r.stdout


def test_clean_passes(tmp_path):
    code, out = run(tmp_path, CLEAN)
    assert code == 0, out


def test_nothing_configured_is_not_a_pass(tmp_path):
    """No records, no place list, no blocklist = nothing was checked. That must not print PASS."""
    code, out = run(tmp_path, CLEAN, lists=False)
    assert code == 1 and all(f"FAIL {c}" in out for c in ("C1", "C3", "C4")) and "NOT CHECKED" in out


def test_empty_blocklist_is_not_a_pass(tmp_path):
    bl = tmp_path / "blocklist.txt"
    bl.write_text("# private\n", encoding="utf-8")
    code, out = run(tmp_path, CLEAN, "--blocklist", str(bl))
    assert code == 1 and "FAIL C4" in out


def test_company_number_blocked(tmp_path):
    rec = tmp_path / "records.md"
    rec.write_text("month closed at 48 213,40", encoding="utf-8")
    code, out = run(tmp_path, CLEAN.replace("Supplier 1, 1 250.00", "Supplier 1, 48 213,40"), "--records", str(rec))
    assert code == 1 and "FAIL C1" in out


def test_amount_in_post_blocked(tmp_path):
    code, out = run(tmp_path, CLEAN.replace("into the bank.", "into the bank for 500 EUR.", 1))
    assert code == 1 and "FAIL C2" in out


def test_place_blocked(tmp_path):
    pl = tmp_path / "places.txt"
    pl.write_text("Atlantis\n", encoding="utf-8")
    code, out = run(tmp_path, CLEAN.replace("into the bank.", "into the bank in Atlantis.", 1), "--places", str(pl))
    assert code == 1 and "FAIL C3" in out


def test_blocklisted_name_blocked(tmp_path):
    bl = tmp_path / "blocklist.txt"
    bl.write_text("# private\nAcme Holding\n", encoding="utf-8")
    code, out = run(tmp_path, CLEAN.replace("Supplier 1", "Acme Holding"), "--blocklist", str(bl))
    assert code == 1 and "FAIL C4" in out


def test_too_long_blocked(tmp_path):
    code, out = run(tmp_path, CLEAN.replace(WORDS, WORDS + " " + WORDS))
    assert code == 1 and "FAIL C5" in out


# --- ways around the check that an audit found; each must stay closed ---------

def test_rounded_company_number_blocked(tmp_path):
    rec = tmp_path / "records.md"
    rec.write_text("month closed at 48 213,40", encoding="utf-8")
    for shown in ("48,213", "48 000"):
        code, out = run(tmp_path, CLEAN.replace("Supplier 1, 1 250.00", f"Supplier 1, {shown}"), "--records", str(rec))
        assert code == 1 and "FAIL C1" in out, shown


def test_amount_in_words_currency_blocked(tmp_path):
    code, out = run(tmp_path, CLEAN.replace("into the bank.", "into the bank for 500 euros.", 1))
    assert code == 1 and "FAIL C2" in out


def test_name_split_by_whitespace_blocked(tmp_path):
    bl = tmp_path / "blocklist.txt"
    bl.write_text("Acme Holding\n", encoding="utf-8")
    for split in ("Acme  Holding", "Acme\nHolding"):
        code, out = run(tmp_path, CLEAN.replace("Supplier 1", split), "--blocklist", str(bl))
        assert code == 1 and "FAIL C4" in out, repr(split)


def test_repeated_heading_and_preamble_are_scanned(tmp_path):
    bl = tmp_path / "blocklist.txt"
    bl.write_text("Acme Holding\n", encoding="utf-8")
    hidden_first = CLEAN.replace("## POST (EN)", "## POST (EN)\nWe work with Acme Holding.\n\n## POST (EN)", 1)
    in_title = CLEAN.replace("## POST (EN)", "# Notes on Acme Holding\n\n## POST (EN)", 1)
    in_front_matter = CLEAN.replace("stage: DRAFT", "stage: DRAFT\nclient: Acme Holding", 1)
    for draft in (hidden_first, in_title, in_front_matter):
        code, out = run(tmp_path, draft, "--blocklist", str(bl))
        assert code == 1 and "FAIL C4" in out, draft[:80]
