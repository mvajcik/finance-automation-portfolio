---
name: morning-coordinator
description: >
  Every weekday at 6:00, reads the status file and git state of every project and writes ONE page:
  which decisions wait for the manager (as yes/no questions), what was finished since yesterday,
  what has been stuck for more than 14 days. Read-only: it never changes a project.
---

# Morning coordinator

**Problem it solves:** with several projects running, the first 30 minutes of the
day went into opening status files and asking "where are we?". Now one page is
waiting, and every item on it is a decision I can answer yes or no.

## How it runs

```
launchd (macOS scheduler), Mon–Fri 6:00, and again at wake-up if the Mac was off
  -> collect.py        reads STATUS.md + git state of each project (read-only)
  -> claude -p         no tools, no file access: it only sees the collected facts
  -> a dated page in a local archive folder + a notification on the Mac
```

If Claude fails, the raw facts are saved instead, so the morning never starts empty.
A run is skipped on weekends and when today's page already exists.

## Rules given to the model (RULES.md, abridged)

- Business language, no IT jargon. "Not merged" becomes "finished work not yet
  taken into the main version".
- Every "waiting for you" item is a real decision with consequences:
  **"Approve the corrected forecast file? YES -> … NO -> …"**.
  Forbidden: "Will you work on this today?".
- Facts only from the supplied text. Unknown = "not in the records". No guessing of dates.
- Maximum 5 decisions, money and deadlines first. One page, under 35 lines.
- The last line is machine-readable, used for the notification and for the trend
  of the queue: `NOTIFICATION: N decisions waiting · M done since yesterday · K stuck`.

## Output shape

```markdown
# Morning coordinator — 2026-10-09
**Verdict:** 6 decisions waiting (yesterday 8 -> today 6), 2 tasks finished, 1 stuck.
The most important today: the month-end report check that failed last night.

## Waiting for you (max 5)
1. **Month-end report — failed check** — Let Claude find the cause and rerun?
   YES -> rerun tonight, result tomorrow. NO -> report stays a draft.

## Done since yesterday
- Payment file generator: two clean runs in a row (commit a1b2c3d)

## Stuck (over 14 days)
- Data dictionary update: waiting for a decision on naming
```

## Files

- `collect.py` — collects the facts (read-only; git without network).
- Scheduler definition and the shell wrapper are machine-specific and not included.
