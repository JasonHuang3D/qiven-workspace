"""Behavior test for the workspace bootstrap typed gate failures."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


BOOTSTRAP_PATH = Path(__file__).with_name("qiven-bootstrap.py")
SPEC = importlib.util.spec_from_file_location("qiven_bootstrap", BOOTSTRAP_PATH)
assert SPEC is not None and SPEC.loader is not None
BOOTSTRAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOTSTRAP)


class ConfigureTimeoutEnvelopeTests(unittest.TestCase):
    def test_timeout_emits_typed_record_and_rc_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            adapter = temp / "adapter.cmake"
            adapter.write_text("# fixture\n", encoding="utf-8", newline="\n")
            generation = "sha256:" + "a" * 64
            lock = {"generation": generation, "nodes": {"qiven-devkit": {}}}
            args = type(
                "Args",
                (),
                {
                    "devkit": str(temp / "devkit"),
                    "mode": "shadow",
                    "trust_policy": None,
                    "repo": "fixture",
                    "repo_root": str(temp),
                    "preset": "default",
                    "cmake": "cmake-fixture",
                },
            )()

            original_checkout = BOOTSTRAP._devkit_checkout
            original_identity = BOOTSTRAP._identity_check
            original_run = BOOTSTRAP.subprocess.run
            original_timeout = BOOTSTRAP.CONFIGURE_TIMEOUT
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                if len(calls) == 1:
                    return type(
                        "Completed",
                        (),
                        {
                            "returncode": 0,
                            "stdout": json.dumps(
                                {
                                    "workspace_generation": generation,
                                    "adapter_path": str(adapter),
                                    "adapter_sha256": "sha256:" + "b" * 64,
                                    "target_revision": "c" * 40,
                                }
                            ),
                            "stderr": "",
                        },
                    )()
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])

            BOOTSTRAP._devkit_checkout = lambda control, explicit: Path(explicit)
            BOOTSTRAP._identity_check = lambda checkout, node, strict_clean: []
            BOOTSTRAP.subprocess.run = fake_run
            BOOTSTRAP.CONFIGURE_TIMEOUT = 1
            stdout = io.StringIO()
            stderr = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(BOOTSTRAP.Typed) as raised:
                        BOOTSTRAP._gate_configure(args, temp, lock)
                    rc = BOOTSTRAP._emit_typed_envelope(raised.exception)
            finally:
                BOOTSTRAP._devkit_checkout = original_checkout
                BOOTSTRAP._identity_check = original_identity
                BOOTSTRAP.subprocess.run = original_run
                BOOTSTRAP.CONFIGURE_TIMEOUT = original_timeout

            output = stdout.getvalue()
            envelope_start = output.find("{")
            envelope, _ = json.JSONDecoder().raw_decode(output[envelope_start:])
            self.assertEqual(rc, 1)
            self.assertEqual(envelope["schema"], "qiven-workspace-bootstrap-error-v1")
            self.assertEqual(envelope["error"]["type"], "ConfigureTimeout")
            record = envelope["record"]
            self.assertEqual(record["record_kind"], "bootstrap-gate-configure")
            self.assertEqual(record["producer"]["id"], "workspace-bootstrap-gate-configure")
            self.assertEqual(record["findings"][0]["rule_id"], "gate-configure/configure-timeout")
            self.assertEqual(record["next_action"], {"action": "DIAGNOSE"})
            self.assertEqual(record["domain_outcome"]["exit_code"], 1)
            self.assertIn("ConfigureTimeout", stderr.getvalue())
            self.assertEqual(len(calls), 2)


class RecoveryEnvelopeTests(unittest.TestCase):
    """Audit C2: record-construction failure keeps a minimal VALID
    recovery record (rule_id + next_action) on every typed failure
    envelope - the recovery channel must be PRESENT, not merely
    in-vocabulary when present."""

    REQUIRED_SECTIONS = (
        "schema_version", "record_kind", "producer", "operation",
        "observation", "admission", "completion", "domain_outcome",
        "coverage", "findings", "next_action", "evidence", "retry_state",
        "payload",
    )

    def _emit_with_broken_constructor(self, error):
        """Run _emit_typed_envelope with full record construction
        monkeypatched to raise (the C2 construction-failure simulation);
        return (rc, parsed envelope)."""

        def broken(*_args, **_kwargs):
            raise ValueError("fixture: full record construction failed")

        original = BOOTSTRAP._typed_error_record
        BOOTSTRAP._typed_error_record = broken
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                rc = BOOTSTRAP._emit_typed_envelope(error)
        finally:
            BOOTSTRAP._typed_error_record = original
        output = stdout.getvalue()
        envelope, _ = json.JSONDecoder().raw_decode(output[output.find("{"):])
        return rc, envelope

    def test_construction_failure_preflight_keeps_recovery_record(self) -> None:
        rc, envelope = self._emit_with_broken_constructor(
            BOOTSTRAP.Typed("PreflightTimeout", "fixture preflight timeout"))
        self.assertEqual(rc, 1)
        self.assertEqual(envelope["schema"], "qiven-workspace-bootstrap-error-v1")
        self.assertEqual(envelope["error"]["type"], "PreflightTimeout")
        self.assertIn("record", envelope)
        record = envelope["record"]
        self.assertEqual(record["record_kind"], "bootstrap-preflight")
        self.assertEqual(record["producer"]["id"], "workspace-bootstrap-preflight")
        self.assertEqual(record["findings"][0]["rule_id"], "bootstrap/preflight-timeout")
        self.assertEqual(record["next_action"], {"action": "DIAGNOSE"})
        self.assertEqual(record["domain_outcome"]["exit_code"], 1)

    def test_construction_failure_gate_keeps_recovery_record(self) -> None:
        rc, envelope = self._emit_with_broken_constructor(
            BOOTSTRAP._gate_typed("ConfigureTimeout", "fixture configure timeout"))
        self.assertEqual(rc, 1)
        self.assertEqual(envelope["error"]["type"], "ConfigureTimeout")
        record = envelope["record"]
        self.assertEqual(record["record_kind"], "bootstrap-gate-configure")
        self.assertEqual(record["producer"]["id"], "workspace-bootstrap-gate-configure")
        self.assertEqual(record["findings"][0]["rule_id"],
                         "gate-configure/configure-timeout")
        self.assertEqual(record["next_action"], {"action": "DIAGNOSE"})

    def test_every_failure_class_carries_recovery_channel(self) -> None:
        """Channel-PRESENCE sweep: for EVERY typed failure class the
        bootstrap can emit (both rule-path tables plus an unmapped kind
        hitting the default path), a construction failure still leaves
        rule_id + next_action on the envelope."""
        gate_kinds = set(BOOTSTRAP._CR_GATE_RULE_PATH)
        kinds = sorted(set(BOOTSTRAP._CR_RULE_PATH) | gate_kinds
                       | {"UnmappedKind"})
        self.assertGreater(len(kinds), 10)
        for kind in kinds:
            if kind in gate_kinds:
                error = BOOTSTRAP._gate_typed(kind, f"fixture {kind}")
            else:
                error = BOOTSTRAP.Typed(kind, f"fixture {kind}")
            with self.subTest(kind=kind):
                rc, envelope = self._emit_with_broken_constructor(error)
                self.assertEqual(rc, 1)
                self.assertEqual(envelope["error"]["type"], kind)
                self.assertIn("record", envelope)
                record = envelope["record"]
                for section in self.REQUIRED_SECTIONS:
                    self.assertIn(section, record)
                self.assertEqual(record["schema_version"], 1)
                self.assertTrue(record["findings"][0]["rule_id"])
                self.assertIn("action", record["next_action"])
                self.assertEqual(record["next_action"]["action"], "DIAGNOSE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
