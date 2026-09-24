"""Workspace bootstrap (WR-1, ADR-0052; architecture doc 01 section 2.1).

Standard-library only. One narrow job: locate the workspace control root,
validate the lock's bootstrap subset, identity-check the locked Devkit
checkout BEFORE any Devkit import, then execute only the locked Devkit
resolver in preflight mode and emit its release receipt. It never resolves
graphs, never selects a newer Devkit, never falls back to a sibling Devkit,
and never mutates the lock. Until the owner-accepted control trust policy
admits this control revision, only shadow mode is available.

WR-3 extension (doc 02 stage WR-3): `gate-configure` runs the locked
resolver's adapter operation for one target repository and then executes
the approved CMake configure preset with QIVEN_RESOLUTION_FILE pointing at
the emitted adapter (architecture doc 01 section 4: CMake receives the
resolved roots; the governed entry stays cmake --preset).

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
ADAPTER_TIMEOUT = 120
CONFIGURE_TIMEOUT = 900


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
    raise Typed("RevisionUnavailable", "no Devkit checkout: pass --devkit (an explicit locator, "
                                      "never a selector) or register .qiven-workspace.local.json "
                                      "checkouts")


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


def _gate_configure(args, control: Path, lock: dict) -> int:
    """WR-3: emit the target's adapter via the LOCKED resolver, then run the
    approved CMake configure preset with QIVEN_RESOLUTION_FILE set (doc 01
    section 4). The bootstrap never resolves the graph itself."""
    checkout = _devkit_checkout(control, args.devkit)
    notes = _identity_check(checkout, lock["nodes"]["qiven-devkit"],
                            strict_clean=(args.mode == "authoritative"))
    repo_root = Path(args.repo_root).resolve()
    adapter_cmd = [
        sys.executable, str(checkout / "tools" / "workspace_resolver.py"),
        "adapter", "--control", str(control),
        "--repo", args.repo, "--repo-checkout", str(repo_root),
        "--workspace-root", str(control.parent),
        "--mode", args.mode, "--json",
    ]
    if args.trust_policy:
        adapter_cmd += ["--trust-policy", args.trust_policy]
    try:
        result = subprocess.run(adapter_cmd, capture_output=True, text=True,
                                timeout=ADAPTER_TIMEOUT, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as error:
        raise Typed("RevisionUnavailable", f"resolver adapter timed out: {error}") from error
    if result.returncode != 0:
        print(result.stdout.strip() or result.stderr.strip())
        return 1
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("[FAIL] resolver adapter emitted no receipt", file=sys.stderr)
        return 1
    if receipt.get("workspace_generation") != lock.get("generation"):
        print("[FAIL] adapter generation does not match the lock", file=sys.stderr)
        return 1
    adapter_path = receipt.get("adapter_path", "")
    if not adapter_path or not Path(adapter_path).is_file():
        print("[FAIL] adapter receipt names no adapter file", file=sys.stderr)
        return 1
    receipt["bootstrap_notes"] = notes

    configure_cmd = [args.cmake, "--preset", args.preset]
    env = dict(os.environ)
    env["QIVEN_RESOLUTION_FILE"] = adapter_path
    print(f"[qiven-workspace] adapter {receipt['adapter_sha256'][:19]} "
          f"generation {receipt['workspace_generation'][:19]} mode {args.mode}")
    configure = subprocess.run(configure_cmd, cwd=str(repo_root), env=env)
    if configure.returncode != 0:
        print(f"[FAIL] cmake --preset {args.preset} rc={configure.returncode}", file=sys.stderr)
        return configure.returncode if configure.returncode > 0 else 1
    receipt_path = Path(adapter_path).parent / "gate-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8", newline="\n")
    print(f"[ OK ] gate-configure {args.repo} @ {receipt['target_revision'][:9]} "
          f"(receipt: {receipt_path})")
    return 0


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--control", help="explicit workspace control checkout")
    common.add_argument("--devkit", help="explicit locked-Devkit checkout (a locator, not a selector)")
    common.add_argument("--mode", choices=["shadow", "authoritative"], default="shadow")
    common.add_argument("--trust-policy", help="admitted control revisions (authoritative mode)")

    parser = argparse.ArgumentParser(
        description="qiven workspace bootstrap",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", parents=[common],
                   help="identity-check + locked resolver preflight (default)")

    gate_cmd = sub.add_parser("gate-configure", parents=[common],
                              help="WR-3: adapter + cmake --preset")
    gate_cmd.add_argument("--repo", required=True, help="target repository id")
    gate_cmd.add_argument("--repo-root", required=True, help="target repository checkout")
    gate_cmd.add_argument("--preset", required=True, help="approved configure preset name")
    gate_cmd.add_argument("--cmake", default="cmake", help="cmake executable (a locator)")

    args = parser.parse_args(argv)

    try:
        control = _control_root(args.control)
        lock = _lock_bootstrap_subset(control)
        if args.command == "gate-configure":
            return _gate_configure(args, control, lock)
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
