"""Candidate publication through real CLIs, files, and isolated Git state."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path

from git_support import GitCheckout

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WRITER = SCRIPTS / "write_handoff.py"
VALIDATOR = SCRIPTS / "validate_handoff.py"


class CandidateWriterTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "writer-candidate-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.run_cwd = self.root
        self.checkout = self.root / "assessed"
        self.checkout.mkdir()
        self.attempt = self.root / "attempt-001"
        self.attempt.mkdir()
        self.input_path = self.root / "input.json"
        self.init_git("Writer Test", "writer@example.invalid", self.root / "no-hooks")
        (self.checkout / "ticket.md").write_text("A1: produces output\n")
        (self.checkout / "spec.md").write_text("Accepted synthetic spec\n")
        self.base = self.commit("Scope")
        (self.checkout / "output.txt").write_text("Candidate output\n")
        self.head = self.commit("Candidate")
        (self.attempt / "receipt.txt").write_text("Observed synthetic output\n")
        self.data = {
            "actor": "worker-1",
            "ticket": "./ticket.md",
            "spec": "./spec.md",
            "base_ref": self.base,
            "owned_files": ["./output.txt"],
            "criteria": ["A1"],
            "checks": [
                {
                    "kind": "manual",
                    "name": "Synthetic review",
                    "status": "passed",
                    "method": "Inspect output in assessed checkout",
                    "exit_code": None,
                    "evidence": ["receipt.txt"],
                }
            ],
            "limits": [],
        }

    def command(self):
        return [
            sys.executable,
            str(WRITER),
            "candidate",
            str(self.attempt),
            "--checkout",
            str(self.checkout),
            *self.requirement_args("candidate"),
            "--input",
            str(self.input_path),
        ]

    def run_writer(self, expected=0):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        before = self.input_path.read_bytes()
        result = subprocess.run(
            self.command(),
            cwd=self.run_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(self.input_path.read_bytes(), before)
        return result

    def validate(self, expected=0):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                str(self.attempt),
                "--stage",
                "candidate",
                "--checkout",
                str(self.checkout),
                *self.requirement_args("candidate"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_candidate_uses_explicit_checkout_and_captured_base(self):
        self.run_cwd = self.root / "caller-checkout"
        subprocess.run(
            ["git", "clone", "--quiet", str(self.checkout), str(self.run_cwd)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(self.run_cwd), "checkout", self.base],
            check=True,
            capture_output=True,
        )
        result = self.run_writer()
        record = json.loads((self.attempt / "candidate.json").read_bytes())
        self.assertEqual(
            record,
            {
                "schema_version": 2,
                **self.requirement_fields("candidate"),
                "kind": "candidate",
                "actor": "worker-1",
                "ticket": "ticket.md",
                "spec": "spec.md",
                "base_commit": self.base,
                "candidate_commit": self.head,
                "worktree": str(self.checkout),
                "owned_files": ["output.txt"],
                "criteria": ["A1"],
                "checks": self.data["checks"],
                "limits": [],
            },
        )
        self.assertIn(str(self.attempt / "candidate.json"), result.stdout)
        self.assertIn("Transition allowed", result.stdout)
        self.validate()

    def test_invalid_input_is_diagnosed_without_publication(self):
        valid = deepcopy(self.data)
        cases = []
        for field in valid:
            invalid = deepcopy(valid)
            del invalid[field]
            cases.append((invalid, field))
        for field, value in (
            ("schema_version", 1),
            ("kind", "candidate"),
            ("candidate_commit", self.head),
            ("base_commit", self.base),
            ("worktree", str(self.checkout)),
            ("surprise", True),
        ):
            invalid = deepcopy(valid)
            invalid[field] = value
            cases.append((invalid, field))
        for field, value in (
            ("actor", ""),
            ("base_ref", 5),
            ("criteria", []),
            ("owned_files", "output.txt"),
            ("checks", None),
            ("limits", None),
            ("ticket", "../ticket.md"),
            ("spec", "..\\spec.md"),
        ):
            invalid = deepcopy(valid)
            invalid[field] = value
            cases.append((invalid, field))
        invalid = deepcopy(valid)
        invalid["checks"][0]["surprise"] = True
        cases.append((invalid, "surprise"))
        for invalid, field in cases:
            with self.subTest(field=field, value=invalid):
                self.data = invalid
                result = self.run_writer(1)
                self.assertIn(field, result.stderr)
                self.assertIn(str(self.input_path), result.stderr)
                self.assertFalse((self.attempt / "candidate.json").exists())

    def test_relative_attempt_is_refused(self):
        self.attempt = Path("attempt-001")
        result = self.run_writer(1)
        self.assertIn("absolute", result.stderr)
        self.assertFalse((self.root / "attempt-001" / "candidate.json").exists())

    def test_duplicate_input_field_is_not_silently_replaced(self):
        payload = json.dumps(self.data)[:-1] + ', "actor": "replacement"}'
        self.input_path.write_text(payload, encoding="utf-8")
        result = subprocess.run(
            self.command(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("duplicate", result.stderr)
        self.assertIn("actor", result.stderr)
        self.assertEqual(self.input_path.read_text(encoding="utf-8"), payload)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_failed_check_is_published_held_and_unavailable_may_advance(self):
        for status, expected in (("failed", 2), ("unavailable", 0)):
            with self.subTest(status=status):
                self.attempt = self.root / status
                self.attempt.mkdir()
                (self.attempt / "receipt.txt").write_text(
                    "Attempt and reason observed\n"
                )
                self.data["checks"][0].update(
                    status=status, reason="Synthetic prerequisite"
                )
                result = self.run_writer(expected)
                self.assertIn("Published", result.stdout)
                self.assertIn(
                    "Transition held" if expected == 2 else "Transition allowed",
                    result.stdout,
                )
                self.validate(expected)

    def test_evidence_uses_attempt_or_absolute_paths_and_existing_bytes_are_preserved(
        self,
    ):
        absolute = self.root / "absolute.txt"
        absolute.write_text("Independent evidence\n")
        self.data["checks"][0]["evidence"].append(str(absolute))
        self.run_writer()
        destination = self.attempt / "candidate.json"
        original = destination.read_bytes()
        self.assertTrue(original.startswith(b'{\n  "actor": "worker-1",\n'))
        self.assertTrue(original.endswith(b"\n"))
        result = self.run_writer(1)
        self.assertIn("No record published", result.stderr)
        self.assertEqual(destination.read_bytes(), original)
        self.data["actor"] = ""
        self.run_writer(1)
        self.assertEqual(destination.read_bytes(), original)
        self.data["actor"] = "worker-1"
        self.validate()
        self.attempt = self.root / "attempt-002"
        self.attempt.mkdir()
        (self.attempt / "receipt.txt").write_text("Independent receipt\n")
        self.run_writer()
        self.assertEqual((self.attempt / "candidate.json").read_bytes(), original)

    def test_missing_evidence_refuses_publication(self):
        (self.attempt / "receipt.txt").unlink()
        # An identically named input-neighbor is not attempt-relative evidence.
        (self.root / "receipt.txt").write_text("Wrong location\n")
        result = self.run_writer(1)
        self.assertIn("missing evidence", result.stderr)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_invalid_reference_noncommit_and_unrelated_base_are_refused(self):
        blob = self.git("rev-parse", "HEAD:output.txt")
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        (self.checkout / "other.txt").write_text("Different history\n")
        unrelated = self.commit("Unrelated scope")
        self.git("checkout", "main")
        for reference in ("missing-reference", blob, unrelated, "--help"):
            with self.subTest(reference=reference):
                self.data["base_ref"] = reference
                self.run_writer(1)
                self.assertFalse((self.attempt / "candidate.json").exists())

    def test_annotated_historical_reference_resolves_to_full_commit(self):
        self.git(
            "tag", "-a", "captured-base", self.base, "-m", "Captured before checks"
        )
        self.data["base_ref"] = "captured-base"
        self.run_writer()
        record = json.loads((self.attempt / "candidate.json").read_bytes())
        self.assertEqual(record["base_commit"], self.base)
        self.validate()

    def test_dirty_missing_scope_and_noncheckout_state_are_refused(self):
        (self.checkout / "output.txt").write_text("Dirty change\n")
        self.assertIn("clean", self.run_writer(1).stderr)
        self.git("checkout", "--", "output.txt")
        self.data["ticket"] = "missing.md"
        self.assertIn("ticket", self.run_writer(1).stderr)
        self.data["ticket"] = "ticket.md"
        self.checkout = self.root
        self.run_writer(1)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_concurrent_cli_publishers_have_one_complete_winner(self):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        processes = [
            subprocess.Popen(
                self.command(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(timeout=20) for process in processes]
        self.assertEqual(
            sorted(process.returncode for process in processes), [0, 1], outputs
        )
        record = json.loads((self.attempt / "candidate.json").read_bytes())
        self.assertEqual(record["candidate_commit"], self.head)
        self.validate()

    def filesystem_environment(self, operation):
        boundary = self.root / "boundary"
        boundary.mkdir()
        (boundary / "sitecustomize.py").write_text(
            "import os, time\n"
            "from pathlib import Path\n"
            "original = os.fsync\n"
            "def controlled(fd):\n"
            "    original(fd)\n"
            "    Path(os.environ['BOUNDARY_READY']).write_text('flushed')\n"
            "    if os.environ['BOUNDARY_OPERATION'] == 'fail':\n"
            "        raise OSError('controlled filesystem failure')\n"
            "    while True:\n"
            "        time.sleep(0.05)\n"
            "os.fsync = controlled\n",
            encoding="utf-8",
        )
        return dict(
            os.environ,
            PYTHONPATH=str(boundary),
            BOUNDARY_READY=str(self.root / "boundary-ready"),
            BOUNDARY_OPERATION=operation,
        )

    def test_filesystem_failure_exposes_no_record_and_preserves_other_records(self):
        previous = self.attempt / "verification.json"
        previous.write_bytes(b"previous immutable record\n")
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        result = subprocess.run(
            self.command(),
            env=self.filesystem_environment("fail"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("controlled filesystem failure", result.stderr)
        self.assertFalse((self.attempt / "candidate.json").exists())
        self.assertEqual(previous.read_bytes(), b"previous immutable record\n")

    def test_interruption_after_staging_exposes_no_partial_record(self):
        previous = self.attempt / "verification.json"
        previous.write_bytes(b"previous immutable record\n")
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        before = self.input_path.read_bytes()
        process = subprocess.Popen(
            self.command(),
            env=self.filesystem_environment("pause"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            deadline = time.monotonic() + 15
            while not (self.root / "boundary-ready").exists():
                self.assertIsNone(process.poll(), "CLI exited before OS boundary")
                self.assertLess(
                    time.monotonic(), deadline, "CLI never reached OS boundary"
                )
                time.sleep(0.02)
            self.assertFalse((self.attempt / "candidate.json").exists())
        finally:
            process.terminate()
            process.communicate(timeout=10)
        self.assertFalse((self.attempt / "candidate.json").exists())
        self.assertEqual(previous.read_bytes(), b"previous immutable record\n")
        self.assertEqual(self.input_path.read_bytes(), before)

    def test_postpublication_cleanup_failure_still_reports_complete_publication(self):
        boundary = self.root / "boundary"
        boundary.mkdir()
        (boundary / "sitecustomize.py").write_text(
            "import os\n"
            "original = os.unlink\n"
            "def controlled(path, *args, **kwargs):\n"
            "    if '.handoff-' in str(path):\n"
            "        raise OSError('controlled cleanup failure')\n"
            "    return original(path, *args, **kwargs)\n"
            "os.unlink = controlled\n",
            encoding="utf-8",
        )
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        result = subprocess.run(
            self.command(),
            env=dict(os.environ, PYTHONPATH=str(boundary)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Published", result.stdout)
        self.validate()

    def test_candidate_help_describes_input_history_evidence_and_exits(self):
        result = subprocess.run(
            [sys.executable, str(WRITER), "candidate", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for phrase in (
            "base_ref",
            "actor",
            "owned_files",
            "criteria",
            "limits",
            "absolute",
            "attempt",
            "evidence",
            "captured",
            "2",
            "held",
        ):
            self.assertIn(phrase, result.stdout)

    def test_invalid_cli_arguments_are_errors_not_published_held_outcomes(self):
        result = subprocess.run(
            self.command()[:-2],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("--input", result.stderr)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_input_must_be_one_utf8_json_object(self):
        for payload in (b"[]", b"{} {}", b"{broken", b"\xff"):
            with self.subTest(payload=payload):
                self.input_path.write_bytes(payload)
                result = subprocess.run(
                    self.command(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(str(self.input_path), result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.input_path.read_bytes(), payload)
                self.assertFalse((self.attempt / "candidate.json").exists())


if __name__ == "__main__":
    unittest.main()
