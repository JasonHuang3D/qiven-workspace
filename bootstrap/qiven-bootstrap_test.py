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


if __name__ == "__main__":
    unittest.main(verbosity=2)
