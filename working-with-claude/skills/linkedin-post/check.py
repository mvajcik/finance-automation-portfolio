#!/usr/bin/env python3
"""check.py — linkedin-post, the step before a draft is saved. READ-ONLY. Exit 0 = PASS, 1 = FAIL.

Usage: python3 check.py <draft.md> [--records <dir_or_file> ...] [--places <file>] [--blocklist <file>]

  --records    private records. Any 3+ digit number found both in the draft and in the
               records is treated as a confidential figure (C1).
  --places     one place name per line (C3).
  --blocklist  one name per line (people, organisations); '#' starts a comment (C4).
All three live outside this repository on purpose: the list of what must not leak is itself private.
A missing or empty list is a FAIL ("NOT CHECKED"), never a silent pass.
"""
import argparse
import re
import sys
from pathlib import Path

BUZZ = [r"thrilled", r"excited to (share|announce)", r"game[- ]changer", r"revolutioni[sz]", r"\btransformed\b"]
CURRENCY = r"(€|\beur\b|\beuros?\b|\busd\b|\bdollars?\b|\bgbp\b|\bchf\b|\$)"


def numbers(text):
    """Numbers with 3+ digits, normalised (thousand separators removed, decimal comma -> dot). Years skipped."""
    out = set()
    # a space counts only as a thousands separator ("48 213,40"), never after a comma ("Supplier 1, 48")
    for m in re.finditer(r"\d(?:[\d.,]|\s(?=\d{3}\b))*\d|\d", text):
        s = m.group(0).strip(" .,").replace(" ", "")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
            s = s.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        if sum(c.isdigit() for c in s) >= 3 and not re.fullmatch(r"20[2-3]\d", s):
            out.add(s)
    return out


def read_list(path):
    if not path or not Path(path).exists():
        return []
    return [n.strip() for n in Path(path).read_text(encoding="utf-8").splitlines()
            if n.strip() and not n.startswith("#")]


def sections(md):
    """Sections by heading. Nothing is dropped: front matter and text before the first heading are kept under
    "", and a repeated heading is appended to the first one instead of replacing it."""
    parts = re.split(r"(?m)^## ", md)
    out = {"": parts[0]}
    for p in parts[1:]:
        head, _, body = p.partition("\n")
        key = head.strip().upper()
        out[key] = out.get(key, "") + "\n" + body
    return out


def whole_and_rounded(nums):
    """Also the integer part and thousands-rounded forms: a rounded confidential figure is still confidential."""
    out = set(nums)
    for n in nums:
        whole = n.split(".")[0]
        if len(whole) >= 3:
            out.add(whole)
        if len(whole) >= 5:
            out.add(str(round(int(whole), -3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    ap.add_argument("--records", nargs="*", default=[])
    ap.add_argument("--places")
    ap.add_argument("--blocklist")
    a = ap.parse_args()

    sec = sections(Path(a.draft).read_text(encoding="utf-8"))
    sec.pop("CHECK", None)   # the previous run's own output; everything else in the file is scanned
    post = next((v for k, v in sec.items() if k.startswith("POST")), "")
    visual = "\n".join(v for k, v in sec.items() if k.startswith("VISUAL"))
    text = "\n".join(sec.values())
    low = re.sub(r"\s+", " ", text.lower())   # a name split by a line break or two spaces is still the name
    bad, ok = [], []

    corpus = set()
    for r in a.records:
        for f in ([Path(r)] if Path(r).is_file() else sorted(Path(r).rglob("*.md"))):
            corpus |= numbers(f.read_text(errors="replace"))
    hits = sorted(numbers(text) & whole_and_rounded(corpus))
    if not corpus:
        bad.append("C1 company numbers: NOT CHECKED — no records given (--records) or no number in them")
    else:
        (bad if hits else ok).append(f"C1 company numbers: {', '.join(hits) or 'none found in records'}")

    if re.search(rf"\d\s?{CURRENCY}|{CURRENCY}\s?\d", post.lower()):
        bad.append("C2 amount with currency in the post itself")
    elif re.search(rf"\d\s?{CURRENCY}|{CURRENCY}\s?\d", visual.lower()) and "mock" not in visual.lower():
        bad.append("C2 visual has amounts but is not labelled MOCK")
    else:
        ok.append("C2 amounts: none in post, visual is MOCK")

    places = read_list(a.places)
    c = sorted({p for p in places if re.search(rf"\b{re.escape(p.lower())}\b", low)})
    if not places:
        bad.append("C3 places: NOT CHECKED — list missing or empty (--places)")
    else:
        (bad if c else ok).append(f"C3 places: {', '.join(c) or f'none (list of {len(places)})'}")

    names = read_list(a.blocklist)
    found = sorted({n for n in names if re.search(rf"\b{re.escape(n.lower())}", low)})
    if not names:
        bad.append("C4 names: NOT CHECKED — blocklist missing or empty (--blocklist)")
    else:
        (bad if found else ok).append(f"C4 names: {', '.join(found) or f'none (list of {len(names)})'}")

    words = len(re.findall(r"[A-Za-z0-9][\w'-]*", re.sub(r"#\w+", "", post)))
    tags = len(re.findall(r"#\w+", post))
    bz = [p for p in BUZZ if re.search(p, post.lower())]
    shape = ([f"{words} words (80-150)"] if not 80 <= words <= 150 else []) + \
            ([f"{tags} hashtags (max 4)"] if tags > 4 else []) + ([f"buzzwords {bz}"] if bz else [])
    (bad if shape else ok).append(f"C5 shape: {'; '.join(shape) or f'{words} words, {tags} hashtags'}")

    for r in ok:
        print("  PASS " + r)
    for r in bad:
        print("  FAIL " + r)
    print(f"CHECK: {'FAIL' if bad else 'PASS'} ({len(ok)}/{len(ok) + len(bad)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
