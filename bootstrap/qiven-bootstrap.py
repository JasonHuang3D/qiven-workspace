"""Workspace bootstrap (WR-1, ADR-0052; architecture doc 01 section 2.1).

Standard-library only. One narrow job: locate the workspace control root,
validate the lock's bootstrap subset, identity-check the locked Devkit
checkout BEFORE any Devkit import, then execute only the locked Devkit
resolver in preflight mode and emit its release receipt. It never resolves
graphs, never selects a newer Devkit, never falls back to a sibling Devkit,
and never mutates the lock. Until the owner-accepted control trust policy
admits this control revision, only shadow mode is available.

Exit codes: 0 released / 1 typed failure / 2 usage or environment error.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GIT_TIMEOUT = 15
PREFLIGHT_TIMEOUT = 120


class Typed(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind


def _no_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise Typed("DuplicateKey", f'duplicate key "{key}"')
        seen.add(key)
    return dict(pairs)


def _git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise Typed("RevisionUnavailable", f"git {args[0]} failed: {error}") from error
    if result.returncode != 0:
        raise Typed("RevisionUnavailable", f"git {args[0]}: {result.stderr.strip()}")
    return result.stdout.strip()


def _control_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
    elif os.environ.get("QIVEN_WORKSPACE_CONTROL"):
        root = Path(os.environ["QIVEN_WORKSPACE_CONTROL"]).resolve()
    else:
        root = Path(__file__).resolve().parent.parent
    if not (root / "workspace.json").is_file() or not (root / "workspace.lock.json").is_file():
        raise Typed("WorkspaceNotFound", f"no workspace control data at {root}")
    return root


def _lock_bootstrap_subset(control: Path) -> dict:
    try:
        lock = json.loads(
            (control / "workspace.lock.json").read_text(encoding="utf-8-sig"),
            object_pairs_hook=_no_duplicate_keys,
        )
    except Typed:
        raise
    except (OSError, json.JSONDecodeError) as error:
        raise Typed("WorkspaceNotFound", f"lock unreadable: {error}") from error
    if lock.get("schema") != "qiven-workspace-lock-v1":
        raise Typed("WorkspaceNotFound", f"unknown lock schema {lock.get('schema')!r}")
    devkit = lock.get("nodes", {}).get("qiven-devkit")
    if not isinstance(devkit, dict) or len(devkit.get("commit", "")) != 40:
        raise Typed("MissingDeclaration", "lock has no qiven-devkit node with a commit")
    return lock


def _devkit_checkout(control: Path, explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    local = control / ".qiven-workspace.local.json"
    if local.is_file():
        try:
            mapping = json.loads(local.read_text(encoding="utf-8-sig"))
            path = mapping.get("checkouts", {}).get("qiven-devkit")
        except (OSError, json.JSONDecodeError) as error:
            raise Typed("RevisionUnavailable", f"bad checkout mapping: {error}") from error
        if path:
            return Path(path).resolve()
    raise Typed("RevisionUnavailable", "no Devkit checkout: pass --devkit or register "
                                      ".qiven-workspace.local.json checkouts")


def _identity_check(checkout: Path, node: dict, strict_clean: bool) -> list[str]:
    notes: list[str] = []
    head = _git(["rev-parse", "HEAD"], checkout)
    tree = _git(["rev-parse", "HEAD^{tree}"], checkout)
    if head != node["commit"] or tree != node.get("tree"):
        raise Typed("BootstrapDevkitMismatch",
                    f"devkit checkout is {head}/{tree}, lock wants {node['commit']}/{node.get('tree')}")
    dirty = _git(["status", "--porcelain"], checkout)
    if dirty:
        if strict_clean:
            raise Typed("DirtyDependency", "authoritative bootstrap requires a clean Devkit")
        notes.append("devkit checkout dirty (labeled, shadow mode)")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="qiven workspace bootstrap")
    parser.add_argument("--control", help="explicit workspace control checkout")
    parser.add_argument("--devkit", help="explicit locked-Devkit checkout (a locator, not a selector)")
    parser.add_argument("--mode", choices=["shadow", "authoritative"], default="shadow")
    parser.add_argument("--trust-policy", help="admitted control revisions (authoritative mode)")
    args = parser.parse_args(argv)

    try:
        control = _control_root(args.control)
        lock = _lock_bootstrap_subset(control)
        checkout = _devkit_checkout(control, args.devkit)
        notes = _identity_check(checkout, lock["nodes"]["qiven-devkit"],
                                strict_clean=(args.mode == "authoritative"))
        preflight = [sys.executable, str(checkout / "tools" / "workspace_resolver.py"),
                     "preflight", "--control", str(control), "--devkit", str(checkout),
                     "--mode", args.mode, "--json"]
        if args.trust_policy:
            preflight += ["--trust-policy", args.trust_policy]
        result = subprocess.run(preflight, capture_output=True, text=True,
                                timeout=PREFLIGHT_TIMEOUT, encoding="utf-8", errors="replace")
    except Typed as error:
        print(json.dumps({"schema": "qiven-workspace-bootstrap-error-v1",
                          "error": {"type": error.kind, "message": str(error)}}, indent=2))
        return 1
    if result.returncode != 0:
        print(result.stdout.strip() or result.stderr.strip())
        return 1
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("[FAIL] resolver preflight emitted no receipt", file=sys.stderr)
        return 1
    if receipt.get("workspace_generation") != lock.get("generation"):
        print("[FAIL] preflight generation does not match the lock", file=sys.stderr)
        return 1
    receipt["bootstrap_notes"] = notes
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
