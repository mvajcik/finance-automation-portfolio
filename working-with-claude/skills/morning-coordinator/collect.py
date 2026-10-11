#!/usr/bin/env python3
"""collect.py — morning coordinator, step 1: collect raw facts from every project. READ-ONLY.

Reads the first entry of each project's STATUS file and its git state (no network:
no fetch, no push). Prints plain text for the model. Configure PROJECTS below.
"""
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
PROJECTS = {
    # name: (repository path, status file inside it)
    "project-a": (HOME / "Projects/project-a", "STATUS.md"),
    "project-b": (HOME / "Projects/project-b", "STATUS.md"),
    "project-c": (HOME / "Projects/project-c", "STATUS.md"),
}


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def first_entry(path: Path, max_lines=15):
    """First STATUS entry = from the first '### ' heading to the second."""
    if not path.exists():
        return "(STATUS missing)"
    out, headings = [], 0
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("### "):
            headings += 1
            if headings == 2:
                break
        if headings and line.strip():
            out.append(line[:400])
        if len(out) >= max_lines:
            break
    return "\n".join(out) or "(empty)"


def git_facts(repo: Path):
    if not (repo / ".git").exists():
        return "(not a git repository)"
    main = "master" if git(repo, "rev-parse", "--verify", "-q", "master") else "main"
    lines = [f"main branch={main} · last commit: {git(repo, 'log', main, '-1', '--format=%as %h %s')[:120]}",
             f"commits not backed up to the remote: {git(repo, 'rev-list', '--count', f'origin/{main}..{main}') or 'unknown'}",
             f"uncommitted files: {len(git(repo, 'status', '--short').splitlines())}"]
    for b in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").splitlines():
        if b != main:
            ahead = git(repo, "rev-list", "--count", f"{main}..{b}")
            lines.append(f"branch {b} | {ahead} commits not in {main} | last: {git(repo, 'log', '-1', '--format=%as %s', b)[:100]}")
    return "\n".join(lines)


def main():
    now = datetime.now()
    print(f"# FACTS · {now:%Y-%m-%d %H:%M} · yesterday = {now - timedelta(days=1):%Y-%m-%d} · "
          f"'stuck' threshold = {now - timedelta(days=14):%Y-%m-%d}")
    for name, (repo, status) in PROJECTS.items():
        print(f"\n\n==================== {name} ====================")
        print("## GIT\n" + git_facts(repo))
        print(f"\n## STATUS first entry ({status})\n" + first_entry(repo / status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
