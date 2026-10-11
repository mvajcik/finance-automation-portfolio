---
name: linkedin-post
description: >
  Writes ONE LinkedIn draft (EN, 80–150 words: hook, practical example, mock-data visual, close)
  about a method used in finance work, then runs check.py, which blocks confidential names and
  figures before the author even reads the draft. Never publishes.
---

# linkedin-post

**Goal:** a post costs at most 10 minutes of my time; there are always 3 finished
drafts in the queue. The skill writes, I read, edit and publish by hand.

## STOP

- Anything that needs access to LinkedIn, scheduling or sending → stop and ask.
- No real figures in the post or the visual, not even rounded. Mock data only.

## Steps

1. Read the style guide (voice, hook patterns, closing patterns) and the content plan.
2. If 3 drafts are already queued and no specific topic was asked for, say so and stop.
3. Pick the next topic from the content plan.
4. Write the draft:
   - hook: contrarian idea / personal anecdote / callback to an earlier post;
   - a practical example — **the method and the decision, not the numbers**;
   - visual proposal with **MOCK data** (Company A/B, Supplier 1/2, example IBANs, round invented amounts),
     labelled "MOCK DATA" inside the visual;
   - close: teaser / question / punchline. 80–150 words, at most 4 hashtags.
5. **Honest status:** if something runs only as a trial, the post says so.
6. Run `check.py <draft.md>`. FAIL → fix and rerun. Paste the result into the draft.
   The script is a safety net, not a substitute for reading the draft once more.
7. Save the draft and report three lines: title · first line of the post · what I must decide.

## check.py — red lines

| | Blocks |
|---|---|
| C1 | any number with 3+ digits that also appears in private records (likely a confidential figure) |
| C2 | amounts with a currency outside the visual, or a visual with amounts not labelled MOCK |
| C3 | place names from a private list |
| C4 | names of people and organisations from a private blocklist |
| C5 | shape: 80–150 words, at most 4 hashtags, banned buzzwords |

The records, the place list and the blocklist are configured locally and are
not part of this repository: the list of what must not leak is itself private.
If one of them is missing or empty, the check fails with `NOT CHECKED` — a check
that had nothing to compare against must not report PASS.
