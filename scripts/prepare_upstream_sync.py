"""Prepare an upstream merge; publishing happens only after CI has passed.

Run in a clean checkout of codex/personal. The optional upstream URL supports
local integration tests; the workflow always supplies the official repository.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

BRANCH = "codex/personal"
UPSTREAM = "https://github.com/shengjidaguai-china/BossHunter.git"


def git(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], check=True, text=True, capture_output=capture)


def prepare(upstream_url: str = UPSTREAM) -> bool:
    branch = git("branch", "--show-current", capture=True).stdout.strip()
    if branch != BRANCH:
        raise RuntimeError(f"Expected {BRANCH}, got {branch!r}; refusing to modify checkout")
    if git("status", "--porcelain", capture=True).stdout.strip():
        raise RuntimeError("Checkout must be clean before syncing")
    git("fetch", "--no-tags", upstream_url, "+refs/heads/main:refs/remotes/upstream/main")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", "upstream/main", "HEAD"], check=False)
    if ancestor.returncode == 0:
        print("Upstream main is already included; nothing to sync.")
        return False
    if ancestor.returncode != 1:
        raise RuntimeError("Could not determine upstream ancestry")
    # No commit or push yet. Conflicts fail the job; the target branch stays intact.
    git("merge", "--no-ff", "--no-commit", "upstream/main")
    print("Merge prepared; run validation before committing and pushing.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-url", default=UPSTREAM)
    args = parser.parse_args()
    changed = prepare(args.upstream_url)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(f"changed={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
