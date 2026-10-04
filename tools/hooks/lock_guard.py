#!/usr/bin/env python
"""Lock-movement blocking for qiven-workspace (ADR-0062 c4).

The git hooks in this directory deny (exit 1) any transaction that
mutates workspace.lock.json while ANY node in the NEW lock names a
commit that is not yet PUBLISHED - not reachable from that node
repository's main on its remote, verified fail-closed against the
sibling checkout's refs/remotes/origin/main. Lock movement happens
only after accepted publication; everything else passes untouched.

Node checkout resolution mirrors the bootstrap locator law: explicit
.qiven-workspace.local.json checkouts entry > the control checkout's
sibling directory named after the node. An undeclared node, an
ambiguous mapping, or a missing sibling checkout fails closed with a
named error.

Entry points (invoked by the sh wrappers next to this file):
  lock_guard.py commit   <- pre-commit hook (staged lock, index version)
  lock_guard.py merge    <- pre-merge-commit hook (merge result lock)
  lock_guard.py push     <- pre-push hook (every lock-mutating commit
                             in each pushed range)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = "workspace.lock.json"
GIT_TIMEOUT = 15
ZERO_SHA = "0" * 40
REMEDIATION = (
    "NEXT action: FIX - publish the referenced repository head first (push "
    "its main), fetch in that checkout so refs/remotes/origin/main is fresh, "
    "then re-advance the lock"
)


class GuardError(Exception):
    """Indeterminate input or unpublished node; the operation is denied."""


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError(f"git {args[0]} failed in {cwd}: {exc}") from exc
    if result.returncode != 0:
        raise GuardError(
            f"git {' '.join(args)} in {cwd} rc={result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _git_exit_code(args: list[str], cwd: Path) -> int:
    """Exit code for probes where rc=1 is an answer, not an error."""
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError(f"git {args[0]} failed in {cwd}: {exc}") from exc
    if result.returncode not in (0, 1):
        raise GuardError(
            f"git {' '.join(args)} in {cwd} rc={result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.returncode


def _load_control(root: Path) -> tuple[dict, dict]:
    try:
        workspace = json.loads(
            (root / "workspace.json").read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardError(f"workspace.json unreadable at {root}: {exc}") from exc
    if workspace.get("schema") != "qiven-workspace-v1":
        raise GuardError(f"unknown workspace schema {workspace.get('schema')!r}")
    checkouts: dict = {}
    local = root / ".qiven-workspace.local.json"
    if local.is_file():
        try:
            mapping = json.loads(local.read_text(encoding="utf-8-sig"))
            checkouts = mapping.get("checkouts", {})
        except (OSError, json.JSONDecodeError) as exc:
            raise GuardError(f"bad checkout mapping in {local}: {exc}") from exc
        if not isinstance(checkouts, dict):
            raise GuardError(f"checkouts mapping in {local} is not an object")
    return workspace, checkouts


def _node_checkout(root: Path, workspace: dict, checkouts: dict, node: str) -> Path:
    if node not in workspace.get("repositories", {}):
        raise GuardError(
            f"node {node!r} has no repository declaration in workspace.json; "
            "sibling mapping is unresolved (fail closed)")
    if node in checkouts:
        path = Path(checkouts[node]).resolve()
    else:
        path = (root.parent / node).resolve()
    if not path.is_dir():
        raise GuardError(f"missing sibling checkout for node {node!r}: {path}")
    _git(["rev-parse", "--absolute-git-dir"], path)  # must be a git repo
    return path


def _no_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise GuardError(f'duplicate key "{key}" in workspace.lock.json')
        seen.add(key)
    return dict(pairs)


def _lock_node_commits(lock_text: str) -> dict[str, str]:
    try:
        lock = json.loads(lock_text, object_pairs_hook=_no_duplicate_keys)
    except GuardError:
        raise
    except json.JSONDecodeError as exc:
        raise GuardError(f"new workspace.lock.json is unparseable: {exc}") from exc
    if lock.get("schema") != "qiven-workspace-lock-v1":
        raise GuardError(f"unknown lock schema {lock.get('schema')!r}")
    nodes = lock.get("nodes", {})
    if not isinstance(nodes, dict):
        raise GuardError("lock nodes is not an object")
    commits: dict[str, str] = {}
    for name, node in nodes.items():
        commit = node.get("commit") if isinstance(node, dict) else None
        if not isinstance(commit, str) or len(commit) != 40 or \
                any(ch not in "0123456789abcdef" for ch in commit):
            raise GuardError(f"node {name!r} carries no valid full commit sha")
        commits[name] = commit
    return commits


def _require_published(root: Path, workspace: dict, checkouts: dict,
                       node: str, commit: str) -> None:
    checkout = _node_checkout(root, workspace, checkouts, node)
    if _git_exit_code(
            ["rev-parse", "--verify", "--quiet",
             "refs/remotes/origin/main^{commit}"], checkout) != 0:
        raise GuardError(
            f"node {node!r}: checkout {checkout} has no remote-tracking "
            "origin/main (fetch before lock movement; fail closed)")
    tip = _git(["rev-parse", "--verify", "refs/remotes/origin/main^{commit}"],
               checkout)
    if _git_exit_code(["merge-base", "--is-ancestor", commit, tip],
                      checkout) != 0:
        raise GuardError(
            f"node {node!r}: commit {commit} is not published "
            f"(not reachable from origin/main {tip} in {checkout})")


def _check_lock_text(lock_text: str) -> int:
    nodes = _lock_node_commits(lock_text)
    workspace, checkouts = _load_control(ROOT)
    for node, commit in sorted(nodes.items()):
        _require_published(ROOT, workspace, checkouts, node, commit)
    print(f"[ OK ] lock guard: {len(nodes)} node commit(s) verified published "
          "against refs/remotes/origin/main")
    return 0


def _staged_lock_text() -> str | None:
    staged = _git(["diff", "--cached", "--name-only"], ROOT).splitlines()
    if LOCK not in staged:
        return None
    return _git(["show", f":{LOCK}"], ROOT)


def guard_commit() -> int:
    """pre-commit: the staged (index) lock version is the NEW lock."""
    lock_text = _staged_lock_text()
    return 0 if lock_text is None else _check_lock_text(lock_text)


def guard_merge() -> int:
    """pre-merge-commit: the index already holds the merge result; check it
    when the merge changes the lock versus HEAD."""
    lock_text = _staged_lock_text()
    return 0 if lock_text is None else _check_lock_text(lock_text)


def _blob_or_none(revision: str) -> str | None:
    if _git_exit_code(["rev-parse", "--verify", "--quiet", revision], ROOT) != 0:
        return None
    return _git(["rev-parse", revision], ROOT)


def _commit_mutates_lock(commit: str) -> bool:
    new_blob = _blob_or_none(f"{commit}:{LOCK}")
    parent = None
    if _git_exit_code(["rev-parse", "--verify", "--quiet", f"{commit}^"], ROOT) == 0:
        parent = _git(["rev-parse", f"{commit}^"], ROOT)
    old_blob = _blob_or_none(f"{parent}:{LOCK}") if parent else None
    return new_blob != old_blob


def guard_push() -> int:
    """pre-push: every lock-mutating commit in each pushed range must name
    only nodes published per the CURRENT remote-tracking refs."""
    try:
        lines = sys.stdin.read().splitlines()
    except OSError as exc:
        raise GuardError(f"cannot read pre-push stdin: {exc}") from exc
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4:
            raise GuardError(f"indeterminate pre-push input line: {line!r}")
        _local_ref, local_sha, _remote_ref, remote_sha = parts
        if local_sha == ZERO_SHA:
            continue  # deletion adds no commits
        try:
            if remote_sha == ZERO_SHA:
                commits = _git(["rev-list", local_sha], ROOT).splitlines()
            else:
                commits = _git(
                    ["rev-list", f"{remote_sha}..{local_sha}"], ROOT).splitlines()
        except GuardError as exc:
            raise GuardError(f"pushed range is indeterminate: {exc}") from exc
        for commit in commits:
            if not _commit_mutates_lock(commit):
                continue
            if _blob_or_none(f"{commit}:{LOCK}") is None:
                raise GuardError(
                    f"commit {commit} deletes {LOCK}; lock deletion is denied")
            _check_lock_text(_git(["show", f"{commit}:{LOCK}"], ROOT))
    return 0


def _deny(message: str) -> int:
    print(f"[FAIL] lock guard: {message}")
    print(REMEDIATION)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"commit", "merge", "push"}:
        print("usage: lock_guard.py {commit|merge|push}", file=sys.stderr)
        return 2
    try:
        if args[0] == "commit":
            return guard_commit()
        if args[0] == "merge":
            return guard_merge()
        return guard_push()
    except GuardError as exc:
        return _deny(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
