"""Behavior test for the lock-blocking git hooks (ADR-0062 c4).

Builds a disposable sandbox - a node repository with a LOCAL bare
remote plus this control repository with the REAL tracked hooks
installed - and proves the lock-movement blocking matrix:
  (i)   lock advance to a remote-main-published SHA passes
  (ii)  advance to a local-only unpushed SHA is denied
  (iii) non-lock commits are unaffected
  (iv)  a pushed lock-mutating commit referencing an unpublished node
        commit is denied at push time
  (v)   the same push passes once the node head is published
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOKS_SRC = Path(__file__).resolve().parents[2] / "tools" / "hooks"
GIT_TIMEOUT = 60
BASE_GIT_ARGS = ["-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
                 "-c", "core.autocrlf=false"]


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *BASE_GIT_ARGS, *args], cwd=str(repo), capture_output=True,
        text=True, timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace",
        env={**os.environ, "QIVEN_HOOK_PYTHON": sys.executable.replace("\\", "/")},
    )


def _must(repo: Path, args: list[str], what: str) -> subprocess.CompletedProcess:
    result = _git(repo, args)
    assert result.returncode == 0, f"{what} failed: {result.stderr}"
    return result


def _commit_file(repo: Path, name: str, content: str, message: str,
                 extra: list[str] | None = None) -> str:
    (repo / name).write_text(content, encoding="utf-8", newline="\n")
    _must(repo, ["add", name], f"add {name}")
    _must(repo, ["commit", "-m", message, *(extra or [])], f"commit {name}")
    return _must(repo, ["rev-parse", "HEAD"], "rev-parse").stdout.strip()


def _write_lock(control: Path, node: str, commit: str) -> None:
    lock = {
        "schema": "qiven-workspace-lock-v1",
        "workspace_id": "sbx",
        "generation": "sha256:" + "a" * 64,
        "nodes": {node: {"commit": commit}},
    }
    (control / "workspace.lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8", newline="\n")


class LockHookTests(unittest.TestCase):
    node: Path
    control: Path
    published_sha: str
    unpushed_sha: str

    @classmethod
    def setUpClass(cls) -> None:
        temp = Path(tempfile.mkdtemp(prefix="qiven-lock-hooks-sandbox-"))
        cls.addClassCleanup(lambda: shutil.rmtree(temp, ignore_errors=True))
        # node repository with a local bare remote
        cls.node = temp / "node-a"
        cls.node.mkdir()
        node_remote = temp / "remotes" / "node-a.git"
        node_remote.parent.mkdir()
        _must(cls.node, ["init", "-b", "main"], "node init")
        _must(cls.node, ["config", "user.email", "sandbox@example.invalid"], "cfg")
        _must(cls.node, ["config", "user.name", "sandbox"], "cfg")
        cls.published_sha = _commit_file(cls.node, "base.txt", "base\n", "node base")
        _must(temp, ["init", "--bare", str(node_remote)], "node remote init")
        _must(cls.node, ["remote", "add", "origin", str(node_remote)], "node remote add")
        _must(cls.node, ["push", "-u", "origin", "main"], "node bootstrap push")
        # control repository with the real hooks installed
        cls.control = temp / "qiven-workspace"
        (cls.control / "tools" / "hooks").mkdir(parents=True)
        _must(cls.control, ["init", "-b", "main"], "control init")
        _must(cls.control, ["config", "user.email", "sandbox@example.invalid"], "cfg")
        _must(cls.control, ["config", "user.name", "sandbox"], "cfg")
        for name in ("pre-commit", "pre-merge-commit", "pre-push", "lock_guard.py"):
            shutil.copy2(HOOKS_SRC / name, cls.control / "tools" / "hooks" / name)
        workspace = {
            "schema": "qiven-workspace-v1",
            "workspace_id": "sbx",
            "repositories": {"node-a": {"url": "https://example.invalid/node-a.git"}},
        }
        (cls.control / "workspace.json").write_text(
            json.dumps(workspace, indent=2) + "\n", encoding="utf-8", newline="\n")
        _must(cls.control, ["config", "core.hooksPath", "tools/hooks"], "activate hooks")
        _commit_file(cls.control, "NOTES.md", "control base\n", "control base")
        # a local-only node commit: published nowhere yet
        cls.unpushed_sha = _commit_file(cls.node, "work.txt", "work\n", "node work")

    def _output(self, result: subprocess.CompletedProcess) -> str:
        return (result.stdout + "\n" + result.stderr).lower()

    def test_01_lock_advance_to_published_sha_passes(self):
        _write_lock(self.control, "node-a", self.published_sha)
        _must(self.control, ["add", "workspace.lock.json"], "stage lock")
        result = _git(self.control, ["commit", "-m", "advance lock to published head"])
        self.assertEqual(result.returncode, 0,
                         f"published lock advance must pass: {result.stderr}")

    def test_02_lock_advance_to_unpushed_sha_is_denied(self):
        _write_lock(self.control, "node-a", self.unpushed_sha)
        _must(self.control, ["add", "workspace.lock.json"], "stage lock")
        result = _git(self.control, ["commit", "-m", "advance lock to unpushed head"])
        self.assertNotEqual(result.returncode, 0,
                            "unpushed lock advance must be denied")
        combined = self._output(result)
        self.assertIn("node-a", combined)
        self.assertIn(self.unpushed_sha[:8], combined)
        self.assertIn("not published", combined)
        # unstage the denied lock change so later scenarios start clean
        # (a denied lock left staged would correctly ride along any commit)
        _must(self.control, ["reset"], "unstage denied lock")

    def test_03_non_lock_commit_is_unaffected(self):
        result = _git(self.control, [
            "commit", "--allow-empty", "-m", "documentation-only change"])
        self.assertEqual(result.returncode, 0,
                         f"non-lock commits must pass untouched: {result.stderr}")

    def test_04_push_with_unpublished_lock_commit_is_denied(self):
        # fixture: force the denied commit into history (--no-verify
        # simulates a bypassed pre-commit; the push hook must catch it)
        _must(self.control, ["add", "workspace.lock.json"], "stage lock")
        _must(self.control, ["commit", "--no-verify", "-m",
                             "bypassed lock advance"], "bypassed commit")
        control_remote = self.control.parent / "remotes" / "control.git"
        _must(self.control.parent, ["init", "--bare", str(control_remote)],
              "control remote init")
        _must(self.control, ["remote", "add", "origin", str(control_remote)],
              "control remote add")
        result = _git(self.control, ["push", "-u", "origin", "main"])
        self.assertNotEqual(result.returncode, 0,
                            "push of an unpublished lock commit must be denied")
        combined = self._output(result)
        self.assertIn("node-a", combined)
        self.assertIn("not published", combined)

    def test_05_push_passes_once_node_head_is_published(self):
        _must(self.node, ["push", "origin", "main"], "publish node head")
        result = _git(self.control, ["push", "-u", "origin", "main"])
        self.assertEqual(result.returncode, 0,
                         f"published lock push must pass: {result.stderr}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
