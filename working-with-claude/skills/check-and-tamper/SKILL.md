---
name: check-and-tamper
description: >
  Use whenever a task produces a number, file or report someone will rely on. Every output gets
  (1) a readback check against an independent source and (2) a tamper test that breaks the data
  on purpose and proves the check catches it. A check without a tamper does not count as a check.
---

# Check and tamper

**Problem it solves:** an AI agent (or a person) writes a check, the check is
green, everybody relaxes — and the check could never have failed. Typical
reasons: it compares the output with the same code that produced it, it reads
a cached value instead of the file, or the condition is accidentally always true.

## The three rules

1. **Read back the finished file, not the model.** The check opens the Excel /
   XML / CSV that will actually be sent and compares it with the *source*
   (ledger, bank statement, approved list), never with the in-memory result.
2. **Compare with an independent source.** Two numbers produced by the same
   query agreeing with each other proves nothing.
3. **Every check has a tamper.** The tamper changes the finished output the way
   reality would break it — one cent, one missing row, a swapped IBAN, a value
   typed over a cell — and the test asserts that *this specific check* turns red.

## Recipe

```
for each check C:
    write the clean test:   clean data          -> C passes
    write the tamper:       data broken for C   -> C fails (and says why)
    if the tamper passes:   C is theatre. Fix C before anything else.
```

Good tampers are small and realistic: 0.01 EUR, half an hour, a row deleted,
a date moved to a Sunday, the same payment twice. Large obvious breaks prove little.

## Status words, not colours

A tool ends with a verdict a manager can act on, e.g. `RELEASED` / `BLOCKED`,
`RECONCILED` / `NOT RECONCILED`, `APPROVE` / `HOLD`. A failed check blocks the
output; it is not a warning in a footnote.

## Example in this repository

`finance-ops-toolkit/tests/` — 42 tests, most of them tampers. `make demo`
also runs one tamper live per tool and prints which check caught it:

```
TAMPER  +0.01 EUR on one payment in the finished XML -> caught by R2, R3
TAMPER  100 EUR typed over one cell in the finished Excel -> caught by M1, M2
```
