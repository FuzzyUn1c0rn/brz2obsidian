"""Retry transitions at actual CLI, immutable file and isolated Git boundaries."""

import hashlib
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


class CarryWriterTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "writer-carry-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "assessed"
        self.checkout.mkdir()
        self.source = self.root / "attempt-001"
        self.source.mkdir()
        self.attempt = self.root / "attempt-002"
        self.input_path = self.root / "carry-input.json"
        self.boundary_index = 0
        self.init_git("Carry Test", "carry@example.invalid", self.root / "no-hooks")
        (self.checkout / "ticket.md").write_text("A1: produces output\n")
        (self.checkout / "spec.md").write_text("Accepted synthetic spec\n")
        self.base = self.commit("Scope")
        self.git("switch", "-c", "candidate")
        (self.checkout / "output.txt").write_text("Candidate output\n")
        self.candidate = self.commit("Candidate")
        (self.source / "logs").mkdir()
        (self.source / "logs/check.txt").write_bytes(
            b"Original candidate observation\r\n"
        )
        self.candidate_input = {
            "actor": "original-implementer",
            "ticket": "ticket.md",
            "spec": "spec.md",
            "base_ref": self.base,
            "owned_files": ["output.txt"],
            "criteria": ["A1"],
            "checks": [self.check("logs/check.txt")],
            "limits": [],
        }
        self.publish("candidate", self.candidate_input, self.source)
        self.verification = {
            "actor": "independent-verifier",
            "verdict": "PASS",
            "criteria": [
                {"id": "A1", "status": "satisfied", "evidence": ["logs/check.txt"]}
            ],
            "findings": [],
            "checks": [],
            "limits": [],
        }
        self.data = {"reason": "Prerequisite recovered", "carry_verification": False}

    def check(self, evidence):
        return {
            "name": "Synthetic observation",
            "status": "passed",
            "method": "Inspect synthetic output",
            "exit_code": 0,
            "evidence": [evidence],
        }

    def invoke(self, command, **kwargs):
        kwargs.setdefault("env", getattr(self, "child_env", None))
        return subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            **kwargs,
        )

    def publish(self, stage, data, attempt, expected=0):
        path = self.root / f"{stage}-input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = self.invoke(
            [
                sys.executable,
                str(WRITER),
                stage,
                str(attempt),
                "--checkout",
                str(self.checkout),
                "--input",
                str(path),
            ]
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def command(self):
        return [
            sys.executable,
            str(WRITER),
            "carry-forward",
            str(self.attempt),
            "--from",
            str(self.source),
            "--checkout",
            str(self.checkout),
            "--input",
            str(self.input_path),
        ]

    def snapshot(self):
        return {
            path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()
        }

    def run_writer(self, expected=0):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        before = self.snapshot()
        input_bytes = self.input_path.read_bytes()
        result = self.invoke(self.command())
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.input_path.read_bytes(), input_bytes)
        return result

    def validate(self, stage, expected=0):
        result = self.invoke(
            [
                sys.executable,
                str(VALIDATOR),
                str(self.attempt),
                "--stage",
                stage,
                "--checkout",
                str(self.checkout),
            ]
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_blocked_retry_preserves_candidate_and_requires_fresh_verification(self):
        candidate = json.loads((self.source / "candidate.json").read_bytes())
        candidate["checks"][0].update(
            status="unavailable", exit_code=None, reason="Prerequisite absent"
        )
        original = (" \n" + json.dumps(candidate, ensure_ascii=False) + "\r\n").encode()
        (self.source / "candidate.json").write_bytes(original)
        blocked = dict(
            self.verification, verdict="BLOCKED", findings=["Prerequisite absent"]
        )
        blocked["criteria"] = [
            {"id": "A1", "status": "unverified", "evidence": ["logs/check.txt"]}
        ]
        self.publish("verification", blocked, self.source, expected=2)
        self.run_writer()
        self.assertEqual((self.attempt / "candidate.json").read_bytes(), original)
        self.assertEqual(
            (self.attempt / "logs/check.txt").read_bytes(),
            b"Original candidate observation\r\n",
        )
        self.assertFalse((self.attempt / "verification.json").exists())
        self.assertFalse((self.attempt / "integration.json").exists())
        receipt = json.loads((self.attempt / "carry-forward.json").read_bytes())
        self.assertEqual(
            receipt,
            {
                "reason": "Prerequisite recovered",
                "carry_verification": False,
                "source_attempt": str(self.source),
                "destination_attempt": str(self.attempt),
            },
        )
        self.validate("candidate")
        self.publish("verification", self.verification, self.attempt)
        self.validate("verification")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.candidate)

    def prepare_pass(self):
        absolute = self.root / "absolute evidence café.txt"
        absolute.write_bytes(b"Absolute observation\n")
        (self.source / "logs/verification.txt").write_bytes(b"Verification check\r\n")
        (self.source / "criterion.txt").write_bytes(b"Criterion observation\n")
        candidate_path = self.source / "candidate.json"
        candidate = json.loads(candidate_path.read_bytes())
        candidate["checks"][0]["evidence"] += ["logs/./check.txt", str(absolute)]
        candidate_path.write_bytes((" \n" + json.dumps(candidate) + "\r\n ").encode())
        self.verification["checks"] = [self.check("logs/verification.txt")]
        self.verification["criteria"][0]["evidence"] += ["criterion.txt", str(absolute)]
        self.publish("verification", self.verification, self.source)
        verification_path = self.source / "verification.json"
        verification_path.write_bytes(
            (
                "\n  " + json.dumps(json.loads(verification_path.read_bytes())) + "\r\n"
            ).encode()
        )
        self.data = {
            "reason": "Temporary integration failure resolved",
            "carry_verification": True,
            "verification_reuse_rationale": "Candidate and observed inputs remain unchanged",
        }
        return absolute

    def test_temporary_integration_retry_preserves_pass_bytes_and_all_evidence(self):
        absolute = self.prepare_pass()
        self.git("switch", "main")
        (self.checkout / "parallel.txt").write_text("Parallel work\n")
        previous = self.commit("Parallel integration work")
        self.publish(
            "integration",
            {
                "actor": "merger",
                "status": "failed",
                "previous_tip_ref": previous,
                "checks": [],
                "limits": ["Temporary prerequisite absent"],
            },
            self.source,
            expected=2,
        )
        self.git("switch", "candidate")
        self.attempt = self.root / "new attempt café"
        self.run_writer()
        for name in (
            "candidate.json",
            "verification.json",
            "logs/check.txt",
            "logs/verification.txt",
            "criterion.txt",
        ):
            self.assertEqual(
                (self.attempt / name).read_bytes(), (self.source / name).read_bytes()
            )
        self.assertEqual(absolute.read_bytes(), b"Absolute observation\n")
        self.assertFalse((self.attempt / absolute.name).exists())
        self.assertFalse((self.attempt / "integration.json").exists())
        receipt = json.loads((self.attempt / "carry-forward.json").read_bytes())
        self.assertEqual(
            receipt,
            dict(
                self.data,
                source_attempt=str(self.source),
                destination_attempt=str(self.attempt),
            ),
        )
        self.validate("verification")
        self.git("switch", "main")
        self.git("merge", "--no-ff", "candidate", "-m", "Integrate unchanged candidate")
        self.publish(
            "integration",
            {
                "actor": "merger",
                "status": "integrated",
                "previous_tip_ref": previous,
                "checks": [],
                "limits": [],
            },
            self.attempt,
        )
        integration = json.loads((self.attempt / "integration.json").read_bytes())
        self.assertEqual(
            integration["verification_sha256"],
            hashlib.sha256(
                (self.source / "verification.json").read_bytes()
            ).hexdigest(),
        )
        self.validate("integration")

    def test_reserved_evidence_collisions_are_refused_before_creating_destination(self):
        candidate_path = self.source / "candidate.json"
        candidate = json.loads(candidate_path.read_bytes())
        original = candidate_path.read_bytes()
        for reference in (
            "candidate.json",
            "verification.json",
            "integration.json",
            "carry-forward.json",
        ):
            with self.subTest(reference=reference):
                if reference != "candidate.json":
                    (self.source / reference).write_bytes(
                        b"Immutable evidence with reserved name\n"
                    )
                candidate["checks"][0]["evidence"] = ["logs/check.txt", reference]
                candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
                result = self.run_writer(expected=1)
                self.assertIn("collision", result.stderr)
                self.assertFalse(
                    self.attempt.exists(), "known collision must fail in preflight"
                )
        candidate_path.write_bytes(original)

    def test_occupied_relative_parent_evidence_is_refused_before_any_copy(self):
        candidate_path = self.source / "candidate.json"
        candidate = json.loads(candidate_path.read_bytes())
        shared = self.root / "outside.txt"
        shared.write_bytes(b"Existing shared evidence\n")
        candidate["checks"][0]["evidence"].append("../outside.txt")
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        result = self.run_writer(expected=1)
        self.assertIn(str(shared), result.stderr)
        self.assertFalse(self.attempt.exists())
        self.assertEqual(shared.read_bytes(), b"Existing shared evidence\n")

    def test_parent_relative_evidence_retains_layout_in_a_different_parent(self):
        shared = self.root / "shared"
        shared.mkdir()
        (shared / "observation.txt").write_bytes(b"Relative parent observation\r\n")
        candidate_path = self.source / "candidate.json"
        candidate = json.loads(candidate_path.read_bytes())
        candidate["checks"][0]["evidence"] += ["../shared/./observation.txt"]
        if os.name == "nt":
            candidate["checks"][0]["evidence"] += [r"logs\CHECK.txt"]
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        self.attempt = self.root / "new-parent" / "attempt-002"
        self.run_writer()
        self.assertEqual(
            (self.attempt.parent / "shared/observation.txt").read_bytes(),
            b"Relative parent observation\r\n",
        )
        self.assertEqual(
            (shared / "observation.txt").read_bytes(),
            b"Relative parent observation\r\n",
        )
        self.assertEqual(
            (self.attempt / "candidate.json").read_bytes(), candidate_path.read_bytes()
        )
        self.validate("candidate")

    def test_already_incorporated_retry_reruns_checks_without_merge_or_commit(self):
        self.prepare_pass()
        self.git("switch", "main")
        self.git("merge", "--no-ff", "candidate", "-m", "Previously incorporated")
        (self.checkout / "later.txt").write_text("Later integration work\n")
        incorporated_tip = self.commit("Later work")
        self.publish(
            "integration",
            {
                "actor": "merger",
                "status": "failed",
                "previous_tip_ref": incorporated_tip,
                "checks": [],
                "limits": ["Temporary check prerequisite absent"],
            },
            self.source,
            expected=2,
        )
        self.git("switch", "candidate")
        self.run_writer()
        self.git("switch", "main")
        before = self.git("rev-list", "--all", "--count")
        observed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; assert Path('output.txt').read_text() == 'Candidate output\\n'",
            ],
            cwd=self.checkout,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(observed.returncode, 0, observed.stderr)
        (self.attempt / "rerun.txt").write_text(
            "Reran output assertion at current integration HEAD; exit 0\n"
        )
        check = self.check("rerun.txt")
        check["method"] = (
            f"From {self.checkout}: Python assertion of output.txt content"
        )
        self.publish(
            "integration",
            {
                "actor": "merger",
                "status": "integrated",
                "previous_tip_ref": incorporated_tip,
                "checks": [check],
                "limits": [],
            },
            self.attempt,
        )
        self.validate("integration")
        self.assertEqual(self.git("rev-parse", "HEAD"), incorporated_tip)
        self.assertEqual(self.git("rev-list", "--all", "--count"), before)

    def test_invalid_retry_judgments_fail_without_destination_or_source_changes(self):
        self.prepare_pass()
        good = deepcopy(self.data)
        cases = []
        for field in ("reason", "carry_verification"):
            data = deepcopy(good)
            del data[field]
            cases.append(data)
        for value in ("", "  ", None, 1, []):
            cases.append(dict(good, reason=value))
        for value in (None, 0, 1, "true", []):
            cases.append(dict(good, carry_verification=value))
        for value in ("", "  ", None, 1):
            cases.append(dict(good, verification_reuse_rationale=value))
        data = deepcopy(good)
        del data["verification_reuse_rationale"]
        cases += [
            data,
            dict(good, candidate_commit=self.candidate),
            dict(good, unexpected=True),
            dict(good, carry_verification=False),
        ]
        for data in cases:
            with self.subTest(data=data):
                self.data = data
                result = self.run_writer(expected=1)
                self.assertIn(str(self.input_path), result.stderr)
                self.assertFalse(self.attempt.exists())

    def test_missing_carried_evidence_refuses_before_any_destination_creation(self):
        absolute = self.prepare_pass()
        for name in (
            "logs/check.txt",
            "logs/verification.txt",
            "criterion.txt",
            str(absolute),
        ):
            with self.subTest(name=name):
                path = self.source / name
                payload = path.read_bytes()
                path.unlink()
                self.run_writer(expected=1)
                self.assertFalse(self.attempt.exists())
                path.write_bytes(payload)

    def test_nonpass_verification_reuse_and_stale_candidate_context_are_refused(self):
        self.prepare_pass()
        path = self.source / "verification.json"
        original = path.read_bytes()
        good = json.loads(original)
        for updates in (
            {"verdict": "BLOCKED"},
            {"verdict": "REWORK"},
            {"ticket": "spec.md"},
            {"candidate_commit": self.base},
            {"actor": "original-implementer"},
        ):
            with self.subTest(updates=updates):
                path.write_text(json.dumps(dict(good, **updates)), encoding="utf-8")
                self.run_writer(expected=1)
                self.assertFalse(self.attempt.exists())
        path.write_bytes(original)

    def test_dirty_and_wrong_candidate_checkout_are_refused(self):
        (self.checkout / "output.txt").write_text("Uncommitted repair\n")
        self.run_writer(expected=1)
        self.assertFalse(self.attempt.exists())
        self.git("restore", "output.txt")
        self.git("checkout", self.base)
        self.run_writer(expected=1)
        self.assertFalse(self.attempt.exists())

    def test_failed_candidate_carry_preserves_held_exit_meaning(self):
        path = self.source / "candidate.json"
        candidate = json.loads(path.read_bytes())
        candidate["checks"][0].update(
            status="failed", exit_code=1, reason="Observed failure"
        )
        path.write_text(json.dumps(candidate), encoding="utf-8")
        result = self.run_writer(expected=2)
        self.assertIn("Transition held", result.stdout)
        self.assertEqual(
            (self.attempt / "candidate.json").read_bytes(), path.read_bytes()
        )
        self.validate("candidate", expected=2)

    def test_all_occupied_attempts_are_refused_without_replacement(self):
        source = self.source
        for index, name in enumerate(
            (
                "candidate.json",
                "verification.json",
                "integration.json",
                "carry-forward.json",
                "logs/check.txt",
                "logs/check.txt/child",
                "logs",
                ".handoff-interrupted.tmp",
            )
        ):
            with self.subTest(name=name):
                self.attempt = self.root / f"occupied-{index}"
                target = self.attempt / name
                target.parent.mkdir(parents=True)
                target.write_bytes(b"Existing destination bytes\n")
                prior = {
                    path: path.read_bytes()
                    for path in self.attempt.rglob("*")
                    if path.is_file()
                }
                self.run_writer(expected=1)
                self.assertEqual(
                    {
                        path: path.read_bytes()
                        for path in self.attempt.rglob("*")
                        if path.is_file()
                    },
                    prior,
                )
        self.attempt = source
        self.run_writer(expected=1)
        self.attempt = source / "nested-attempt"
        self.run_writer(expected=1)
        self.assertFalse(self.attempt.exists())

    def test_external_evidence_ancestor_file_blocks_copy_before_mutation(self):
        (self.root / "shared").mkdir()
        (self.root / "shared/observation.txt").write_bytes(
            b"Original parent evidence\n"
        )
        path = self.source / "candidate.json"
        candidate = json.loads(path.read_bytes())
        candidate["checks"][0]["evidence"].append("../shared/observation.txt")
        path.write_text(json.dumps(candidate), encoding="utf-8")
        self.attempt = self.root / "new-parent" / "attempt-002"
        self.attempt.parent.mkdir()
        blocker = self.attempt.parent / "shared"
        blocker.write_bytes(b"Existing ancestor file\n")
        self.run_writer(expected=1)
        self.assertFalse(self.attempt.exists())
        self.assertEqual(blocker.read_bytes(), b"Existing ancestor file\n")

    def filesystem_environment(self, boundary):
        directory = self.root / "boundary"
        directory.mkdir(exist_ok=True)
        (directory / "sitecustomize.py").write_text(
            "import os, sys, time\n"
            "from pathlib import Path\n"
            "root = Path(os.environ['CARRY_BOUNDARY_ROOT'])\n"
            "mode = os.environ['CARRY_BOUNDARY_MODE']\n"
            "def pause():\n"
            "    (root / os.environ['CARRY_BOUNDARY_ID']).write_text('boundary reached')\n"
            "    while not (root / 'release').exists():\n"
            "        time.sleep(0.01)\n"
            "if mode in ('race', 'candidate'):\n"
            "    waiting = True\n"
            "    def audit(event, args):\n"
            "        global waiting\n"
            "        destination = Path(os.environ['CARRY_DESTINATION'])\n"
            "        selected = (mode == 'race' and event == 'os.mkdir' and Path(args[0]).resolve().is_relative_to(destination)) or (mode == 'candidate' and event == 'os.link' and Path(args[1]) == destination / 'candidate.json')\n"
            "        if waiting and selected:\n"
            "            waiting = False\n"
            "            pause()\n"
            "    sys.addaudithook(audit)\n"
            "else:\n"
            "    original = os.fsync\n"
            "    flushed = 0\n"
            "    def fsync(fd):\n"
            "        global flushed\n"
            "        original(fd)\n"
            "        flushed += 1\n"
            "        if flushed == 2:\n"
            "            pause()\n"
            "    os.fsync = fsync\n",
            encoding="utf-8",
        )
        return dict(
            os.environ,
            PYTHONPATH=str(directory),
            CARRY_BOUNDARY_ROOT=str(directory),
            CARRY_BOUNDARY_MODE=boundary,
            CARRY_DESTINATION=str(self.attempt),
        )

    def start_writer(self, env):
        if not self.input_path.exists():
            self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        self.boundary_index += 1
        marker = f"ready-{self.boundary_index}"
        process = subprocess.Popen(
            self.command(),
            cwd=self.root,
            env=dict(env, CARRY_BOUNDARY_ID=marker),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        process.boundary_marker = self.root / "boundary" / marker
        return process

    def wait_boundary(self, processes):
        deadline = time.monotonic() + 20
        for process in processes:
            marker = process.boundary_marker
            while not marker.exists():
                self.assertIsNone(
                    process.poll(), "CLI exited before selected filesystem boundary"
                )
                self.assertLess(
                    time.monotonic(),
                    deadline,
                    "CLI never reached selected filesystem boundary",
                )
                time.sleep(0.01)

    def test_concurrent_carries_race_at_real_filesystem_with_one_complete_winner(self):
        before = self.snapshot()
        env = self.filesystem_environment("race")
        processes = [self.start_writer(env), self.start_writer(env)]
        try:
            self.wait_boundary(processes)
            (self.root / "boundary/release").write_text("go")
            outcomes = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                outcomes.append(process.returncode)
                self.assertNotIn("Traceback", stderr)
                if process.returncode == 0:
                    self.assertIn("Carried to", stdout)
                else:
                    self.assertIn(str(self.attempt), stderr)
            self.assertEqual(sorted(outcomes), [0, 1])
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=10)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(
            (self.attempt / "candidate.json").read_bytes(),
            (self.source / "candidate.json").read_bytes(),
        )
        self.assertEqual(
            (self.attempt / "logs/check.txt").read_bytes(),
            b"Original candidate observation\r\n",
        )
        json.loads((self.attempt / "carry-forward.json").read_bytes())
        self.validate("candidate")

    def test_io_failure_after_evidence_reports_exact_partial_attempt_and_refuses_resume(
        self,
    ):
        before = self.snapshot()
        process = self.start_writer(self.filesystem_environment("pause"))
        try:
            self.wait_boundary([process])
            self.assertTrue((self.attempt / "logs/check.txt").is_file())
            (self.attempt / "carry-forward.json").mkdir()
            (self.root / "boundary/release").write_text("go")
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 1, stdout + stderr)
            self.assertIn(str(self.attempt), stderr)
            self.assertIn("partial attempt is not ready", stderr)
            self.assertNotIn("Carried to", stdout)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.attempt / "candidate.json").exists())
        self.run_writer(expected=1)
        self.validate("candidate", expected=1)

    def test_process_interruption_preserves_source_and_never_exposes_partial_record(
        self,
    ):
        self.prepare_pass()
        before = self.snapshot()
        process = self.start_writer(self.filesystem_environment("candidate"))
        try:
            self.wait_boundary([process])
            self.assertTrue((self.attempt / "logs/check.txt").is_file())
            self.assertEqual(
                (self.attempt / "verification.json").read_bytes(),
                (self.source / "verification.json").read_bytes(),
            )
            self.assertIsNone(process.poll())
        finally:
            process.terminate()
            stdout, _stderr = process.communicate(timeout=10)
        self.assertIn(f"Assigned carry-forward destination {self.attempt}", stdout)
        self.assertNotIn("Carried to", stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.attempt / "candidate.json").exists())
        for name in (
            "candidate.json",
            "verification.json",
            "integration.json",
            "carry-forward.json",
        ):
            path = self.attempt / name
            if path.is_file():
                json.loads(path.read_bytes())
        self.run_writer(expected=1)
        self.validate("candidate", expected=1)
        self.validate("verification", expected=1)

    def test_equivalent_candidate_checkout_keeps_original_actor_and_worktree_context(
        self,
    ):
        original_checkout = self.checkout
        self.checkout = self.root / "equivalent-checkout"
        subprocess.run(
            ["git", "clone", "--quiet", str(original_checkout), str(self.checkout)],
            capture_output=True,
            check=True,
        )
        self.git("checkout", self.candidate)
        self.run_writer()
        candidate = json.loads((self.attempt / "candidate.json").read_bytes())
        self.assertEqual(candidate["worktree"], str(original_checkout))
        self.assertEqual(candidate["actor"], "original-implementer")
        self.validate("candidate")

    def test_invalid_json_and_nonabsolute_attempts_are_refused(self):
        before = self.snapshot()
        for payload in (
            b"[]",
            b"{} {}",
            b"{broken",
            b"\xff",
            b'{"reason":"one", "reason":"two", "carry_verification":false}',
        ):
            with self.subTest(payload=payload):
                self.input_path.write_bytes(payload)
                result = self.invoke(self.command())
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.input_path.read_bytes(), payload)
                self.assertFalse(self.attempt.exists())
                self.assertEqual(self.snapshot(), before)
        source = self.source
        self.source = Path("attempt-001")
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        result = self.invoke(self.command())
        self.assertEqual(result.returncode, 1)
        self.assertIn("absolute", result.stderr)
        self.source = source
        self.attempt = Path("attempt-002")
        result = self.invoke(self.command())
        self.assertEqual(result.returncode, 1)
        self.assertIn("absolute", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_carried_record_encoding_matches_standalone_utf8_validation(self):
        path = self.source / "candidate.json"
        original = path.read_bytes()
        for index, payload in enumerate(
            (b"\xef\xbb\xbf" + original, original.decode("utf-8").encode("utf-16"))
        ):
            with self.subTest(payload=payload[:12]):
                self.attempt = self.root / f"encoding-{index}"
                path.write_bytes(payload)
                self.run_writer(expected=1)
                self.assertFalse(self.attempt.exists())

    def test_cjk_publication_held_and_refusal_diagnostics_are_utf8(self):
        self.child_env = dict(os.environ, PYTHONIOENCODING="cp1252")
        self.attempt = self.root / "候補 猫"
        (self.attempt / "logs").mkdir(parents=True)
        (self.attempt / "logs/check.txt").write_bytes(b"Synthetic observation\n")
        published = self.publish("candidate", self.candidate_input, self.attempt)
        self.assertIn(str(self.attempt / "candidate.json"), published.stdout)
        self.validate("candidate")
        previous = {
            path: path.read_bytes()
            for path in self.attempt.rglob("*")
            if path.is_file()
        }
        refused = self.publish(
            "candidate", self.candidate_input, self.attempt, expected=1
        )
        self.assertIn(str(self.attempt), refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)
        self.assertEqual(
            {
                path: path.read_bytes()
                for path in self.attempt.rglob("*")
                if path.is_file()
            },
            previous,
        )
        blocked = dict(
            self.verification,
            verdict="BLOCKED",
            findings=["Synthetic prerequisite absent"],
        )
        held = self.publish("verification", blocked, self.attempt, expected=2)
        self.assertIn(str(self.attempt / "verification.json"), held.stdout)
        self.validate("verification", expected=2)

    def test_cjk_carry_and_validator_evidence_diagnostics_are_utf8(self):
        self.child_env = dict(os.environ, PYTHONIOENCODING="cp1252")
        reference = "logs/証拠 猫.txt"
        (self.source / reference).write_bytes(b"Unicode path observation\n")
        path = self.source / "candidate.json"
        candidate = json.loads(path.read_bytes())
        candidate["checks"][0]["evidence"].append(reference)
        path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
        self.attempt = self.root / "再試行 猫"
        self.input_path = self.root / "再試行入力 猫.json"
        published = self.run_writer()
        self.assertIn(str(self.attempt), published.stdout)
        self.validate("candidate")
        (self.attempt / reference).unlink()
        result = self.invoke(
            [
                sys.executable,
                str(VALIDATOR),
                str(self.attempt),
                "--stage",
                "candidate",
                "--checkout",
                str(self.checkout),
            ]
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(reference, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        refused = self.run_writer(expected=1)
        self.assertIn(str(self.attempt), refused.stderr)
        self.assertIn(str(self.input_path), refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

    def test_carry_help_explains_explicit_judgments_evidence_receipt_and_partial_recovery(
        self,
    ):
        result = self.invoke([sys.executable, str(WRITER), "carry-forward", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for phrase in (
            "reason",
            "carry_verification",
            "verification_reuse_rationale",
            "PASS",
            "BLOCKED",
            "fresh",
            "absolute",
            "relative",
            "carry-forward.json",
            "partial",
            "unused",
            "2",
            "held",
        ):
            self.assertIn(phrase, result.stdout)


if __name__ == "__main__":
    unittest.main()
