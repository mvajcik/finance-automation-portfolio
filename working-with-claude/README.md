# Working with Claude

How a finance controller with no software background runs AI as a team of
assistants, without losing control of the numbers.

## The division of labour

| I do (the manager) | Claude does (the executor) |
|---|---|
| Decide what problem is worth solving and when it must be done | Read the project files and propose the technical approach |
| Approve the contract: what "done" means, what must never happen | Build, test, and break its own work on purpose (tamper tests) |
| Look at one preview before the full build | Show the preview with real (or clearly marked mock) numbers |
| Accept or reject the result | Prove the result with evidence: a test run, a file, a log line |

The rule that makes this work: **"done" is never a word, it is evidence.**
Every status update names the commit, the test count or the file.

## The workflow

```
goal (1 sentence)
  -> task brief, 5 fields                     task-brief-template.md
  -> agreement: max 3 questions + preview      (I say "yes, this")
  -> build in its own branch, with tamper tests
  -> independent read-only auditor tries to break the claims
  -> I accept by opening the output myself
  -> merge, then a short status entry for the next session
```

## What is in this folder

| File | What it is |
|---|---|
| [`CLAUDE.md.template`](CLAUDE.md.template) | The project memory every session reads first: identity, rules, what needs my approval |
| [`task-brief-template.md`](task-brief-template.md) | The 5-field brief: goal, scope, context, definition of done, STOP |
| [`skills/morning-coordinator/`](skills/morning-coordinator/) | Runs every weekday at 6:00: reads all project status files and gives me one page of yes/no decisions |
| [`skills/check-and-tamper/`](skills/check-and-tamper/) | The pattern behind every tool in this repository: a check, plus a test that proves the check can fail |
| [`skills/linkedin-post/`](skills/linkedin-post/) | Drafts a post from real work, then a script blocks what it can recognise as confidential (figures from my records, also rounded; listed names and places; amounts) before I even read it — I still read every draft |

A *skill* is a short instruction file (plus small scripts) that Claude loads
when a task matches. They are the reusable part of how I work.

The originals are written in Slovak and point to my own projects. The versions
here are translated and stripped of every private name, path and number.

## Lessons that cost me time

- **An agent that says "done" without evidence is not done.** Ask for the
  commit hash or the terminal output, every time.
- **A check that has never failed has not been tested.** Write the tamper first.
- **One preview saves a week.** The first full build is always the wrong shape
  if nobody looked at a sample page first.
- **Memory is a file, not a feeling.** If the status file is older than two
  weeks, the project lost its memory, whatever the chat history says.
- **Anything shown outside the company runs on generated data.** Demos, posts
  and this repository are built on fictional companies, and a script checks
  for real names and numbers before anything is published.
