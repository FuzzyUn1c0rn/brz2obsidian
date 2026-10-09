"""Integration publication through actual CLIs, exact bytes and merge histories."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from git_support import GitCheckout

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
WRITER = SCRIPTS / "write_handoff.py"
VALIDATOR = SCRIPTS / "validate_handoff.py"


class IntegrationWriterTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "writer-integration-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "assessed"
        self.checkout.mkdir()
        self.run_cwd = self.root
        self.attempt = self.root / "attempt-001"
        self.attempt.mkdir()
        self.input_path = self.root / "integration-input.json"
        self.init_git(
            "Integration Test", "merger@example.invalid", self.root / "no-hooks"
        )
        (self.checkout / "ticket.md").write_text("A1: produces output\n")
        (self.checkout / "spec.md").write_text("Accepted synthetic spec\n")
        self.base = self.commit("Scope")
        self.git("switch", "-c", "candidate")
        (self.checkout / "output.txt").write_text("Candidate output\n")
        self.candidate = self.commit("Candidate")
        (self.attempt / "receipt.txt").write_text("Observed actual synthetic output\n")
        self.publish_stage(
            "candidate",
            {
                "actor": "implementer",
                "ticket": "ticket.md",
                "spec": "spec.md",
                "base_ref": self.base,
                "owned_files": ["output.txt"],
                "criteria": ["A1"],
                "checks": [],
                "limits": [],
            },
        )
        self.verification = {
            "actor": "independent-verifier",
            "verdict": "PASS",
            "criteria": [
                {"id": "A1", "status": "satisfied", "evidence": ["receipt.txt"]}
            ],
            "findings": [],
            "checks": [],
            "limits": [],
        }
        self.publish_stage("verification", self.verification)
        self.git("switch", "main")
        (self.checkout / "integration.txt").write_text("Parallel integration work\n")
        self.previous = self.commit("Divergent integration work")
        self.git("merge", "--no-ff", "candidate", "-m", "Integrate candidate")
        self.result = self.git("rev-parse", "HEAD")
        self.data = {
            "actor": "merger",
            "status": "integrated",
            "previous_tip_ref": self.previous,
            "checks": [],
            "limits": ["Synthetic CLI evidence only"],
        }

    def command(self, stage="integration", input_path=None):
        return [
            sys.executable,
            str(WRITER),
            stage,
            str(self.attempt),
            "--checkout",
            str(self.checkout),
            *self.requirement_args(stage),
            "--input",
            str(input_path or self.input_path),
        ]

    def invoke(self, command):
        return subprocess.run(
            command,
            cwd=self.run_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def publish_stage(self, stage, data, expected=0):
        path = self.root / f"{stage}-input.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = self.invoke(self.command(stage, path))
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def run_writer(self, expected=0):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        before = self.input_path.read_bytes()
        occupied = (self.attempt / "integration.json").exists()
        prior = {
            path: path.read_bytes()
            for path in self.attempt.rglob("*")
            if path.is_file()
        }
        result = self.invoke(self.command())
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(self.input_path.read_bytes(), before)
        for path, payload in prior.items():
            self.assertEqual(path.read_bytes(), payload)
        if expected == 1 and not occupied:
            self.assertFalse((self.attempt / "integration.json").exists())
        return result

    def validate(self, expected=0):
        result = self.invoke(
            [
                sys.executable,
                str(VALIDATOR),
                str(self.attempt),
                "--stage",
                "integration",
                "--checkout",
                str(self.checkout),
                *self.requirement_args("integration"),
            ]
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_integrated_binds_selected_candidate_and_actual_divergent_merge(self):
        result = self.run_writer()
        self.assertIn(f"Published {self.attempt / 'integration.json'}", result.stdout)
        self.assertIn("Transition allowed", result.stdout)
        record = json.loads((self.attempt / "integration.json").read_bytes())
        self.assertEqual(
            record,
            {
                "schema_version": 2,
                **self.requirement_fields("integration"),
                "kind": "integration",
                "actor": "merger",
                "ticket": "ticket.md",
                "candidate_commit": self.candidate,
                "previous_tip": self.previous,
                "integration_commit": self.result,
                "verification_sha256": hashlib.sha256(
                    (self.attempt / "verification.json").read_bytes()
                ).hexdigest(),
                "status": "integrated",
                "checks": [],
                "limits": ["Synthetic CLI evidence only"],
            },
        )
        self.validate()

    def test_explicit_checkout_and_captured_historical_tip_survive_moving_branch(self):
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
        self.assertEqual(self.git("rev-parse", "main"), self.result)
        self.run_writer()
        record = json.loads((self.attempt / "integration.json").read_bytes())
        self.assertEqual(record["previous_tip"], self.previous)
        self.assertEqual(record["integration_commit"], self.result)
        self.validate()

    def test_verification_digest_uses_original_bytes_and_detects_later_tampering(self):
        path = self.attempt / "verification.json"
        verification = json.loads(path.read_bytes())
        verification["limits"] = ["Observation: café"]
        original = (
            " \n" + json.dumps(verification, ensure_ascii=False) + "\r\n "
        ).encode()
        path.write_bytes(original)
        self.run_writer()
        record = json.loads((self.attempt / "integration.json").read_bytes())
        self.assertEqual(
            record["verification_sha256"], hashlib.sha256(original).hexdigest()
        )
        canonical = (json.dumps(verification, sort_keys=True, indent=2) + "\n").encode()
        self.assertNotEqual(
            record["verification_sha256"], hashlib.sha256(canonical).hexdigest()
        )
        self.validate()
        path.write_bytes(original + b"\n")
        self.assertIn("verification digest mismatch", self.validate(1).stderr)

    def test_failed_outcome_records_clean_inspected_head_without_success_ancestry(self):
        self.git("switch", "--detach", self.base)
        self.data.update(
            status="failed",
            checks=[
                {
                    "kind": "manual",
                    "name": "Integration check",
                    "status": "failed",
                    "method": "Inspect candidate availability in assessed checkout",
                    "exit_code": 1,
                    "reason": "Candidate merge was not completed",
                    "evidence": ["receipt.txt"],
                }
            ],
        )
        result = self.run_writer(2)
        self.assertIn("Transition held", result.stdout)
        record = json.loads((self.attempt / "integration.json").read_bytes())
        self.assertEqual(record["integration_commit"], self.base)
        self.assertEqual(record["previous_tip"], self.previous)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["checks"], self.data["checks"])
        self.validate(2)

    def test_failed_outcome_can_record_blocked_verification_without_approval(self):
        path = self.attempt / "verification.json"
        record = json.loads(path.read_bytes())
        record.update(verdict="BLOCKED", findings=["A1: user verdict unavailable"])
        record["criteria"][0]["status"] = "unverified"
        path.write_text(json.dumps(record), encoding="utf-8")
        self.data["status"] = "failed"
        self.run_writer(2)
        self.validate(2)

    def test_integrated_requires_approved_candidate_and_verification(self):
        path = self.attempt / "verification.json"
        original = path.read_bytes()
        for verdict in ("BLOCKED", "REWORK"):
            with self.subTest(verdict=verdict):
                record = json.loads(original)
                record.update(verdict=verdict, findings=["A1 unresolved"])
                record["criteria"][0]["status"] = "unverified"
                path.write_text(json.dumps(record), encoding="utf-8")
                self.assertIn("approved candidate", self.run_writer(1).stderr)
        path.write_bytes(original)
        candidate_path = self.attempt / "candidate.json"
        candidate = json.loads(candidate_path.read_bytes())
        candidate["checks"] = [
            {
                "kind": "manual",
                "name": "Candidate check",
                "status": "failed",
                "method": "Inspect output",
                "exit_code": 1,
                "reason": "Candidate failure",
                "evidence": ["receipt.txt"],
            }
        ]
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        self.assertIn("approved candidate", self.run_writer(1).stderr)

    def test_required_judgments_and_helper_owned_overrides_are_refused(self):
        valid = deepcopy(self.data)
        cases = []
        for field in valid:
            missing = deepcopy(valid)
            del missing[field]
            cases.append((field, missing))
        for field in (
            "schema_version",
            "kind",
            "ticket",
            "candidate_commit",
            "previous_tip",
            "integration_commit",
            "verification_sha256",
            "worktree",
            "unknown",
        ):
            cases.append((field, dict(valid, **{field: "override"})))
        for field, value in (
            ("actor", ""),
            ("actor", 7),
            ("status", "PASS"),
            ("status", None),
            ("previous_tip_ref", ""),
            ("previous_tip_ref", 7),
            ("checks", None),
            ("limits", None),
            ("limits", [7]),
        ):
            cases.append((field, dict(valid, **{field: value})))
        for field, data in cases:
            with self.subTest(field=field, data=data):
                self.data = data
                self.assertIn(field, self.run_writer(1).stderr)

    def test_checks_retain_explicit_reuse_source_reason_and_relative_evidence(self):
        self.data["checks"] = [
            {
                "kind": "manual",
                "name": "Reusable observation",
                "status": "reused",
                "method": "Review earlier receipt against resulting checkout",
                "exit_code": None,
                "source_commit": self.candidate,
                "reason": "Merge preserves reviewed output",
                "evidence": ["receipt.txt"],
            }
        ]
        valid = deepcopy(self.data)
        for field in ("source_commit", "reason", "evidence", "method", "exit_code"):
            with self.subTest(field=field):
                self.data = deepcopy(valid)
                del self.data["checks"][0][field]
                self.run_writer(1)
        self.data = deepcopy(valid)
        self.data["checks"][0]["inferred_acceptance"] = True
        self.assertIn("checks[0]", self.run_writer(1).stderr)
        self.data = valid
        self.run_writer()
        self.assertEqual(
            json.loads((self.attempt / "integration.json").read_bytes())["checks"],
            valid["checks"],
        )
        self.validate()

    def test_failed_or_unavailable_integration_checks_cannot_claim_integrated(self):
        for status, code in (("failed", 1), ("unavailable", None)):
            with self.subTest(status=status):
                self.data["checks"] = [
                    {
                        "kind": "manual",
                        "name": "Required integration check",
                        "status": status,
                        "method": "Inspect assessed result",
                        "exit_code": code,
                        "reason": "Synthetic failure",
                        "evidence": ["receipt.txt"],
                    }
                ]
                self.assertIn("checks have not passed", self.run_writer(1).stderr)

    def test_invalid_or_non_commit_captured_references_are_refused(self):
        for reference in (
            "not-a-ref",
            "HEAD:ticket.md",
            "HEAD^{tree}",
            "--all",
            "0" * 40,
        ):
            with self.subTest(reference=reference):
                self.data["previous_tip_ref"] = reference
                self.run_writer(1)
        self.git("tag", "captured-tip", self.previous)
        self.data["previous_tip_ref"] = "captured-tip"
        self.run_writer()
        self.assertEqual(
            json.loads((self.attempt / "integration.json").read_bytes())[
                "previous_tip"
            ],
            self.previous,
        )
        self.validate()

    def test_integrated_refuses_result_without_candidate_ancestry(self):
        self.git("switch", "--detach", self.previous)
        self.run_writer(1)

    def test_integrated_refuses_captured_tip_outside_result_ancestry(self):
        self.git("switch", "--detach", self.base)
        (self.checkout / "other.txt").write_text("Unmerged history\n")
        outside = self.commit("Other branch")
        self.git("switch", "main")
        self.data["previous_tip_ref"] = outside
        self.run_writer(1)

    def test_dirty_tracked_staged_and_untracked_states_are_refused(self):
        for state in ("tracked", "staged", "untracked"):
            with self.subTest(state=state):
                path = self.checkout / (
                    "output.txt" if state != "untracked" else "extra.txt"
                )
                path.write_text("Uncommitted change\n")
                if state == "staged":
                    self.git("add", str(path))
                self.assertIn("checkout must be clean", self.run_writer(1).stderr)
                self.git("reset", "--hard", self.result)
                if state == "untracked":
                    path.unlink()

    def test_missing_scope_and_noncheckout_paths_are_refused_even_for_failed_status(
        self,
    ):
        self.data["status"] = "failed"
        (self.checkout / "ticket.md").unlink()
        self.commit("Remove ticket scope")
        self.assertIn("missing ticket", self.run_writer(1).stderr)
        self.checkout = self.root
        self.run_writer(1)

    def test_mismatched_verification_identity_and_actor_are_refused(self):
        path = self.attempt / "verification.json"
        valid = json.loads(path.read_bytes())
        for field, value in (
            ("ticket", "spec.md"),
            ("candidate_commit", self.base),
            ("actor", "implementer"),
        ):
            with self.subTest(field=field):
                path.write_text(
                    json.dumps(dict(valid, **{field: value})), encoding="utf-8"
                )
                self.run_writer(1)

    def test_missing_evidence_and_verification_are_refused(self):
        receipt = self.attempt / "receipt.txt"
        receipt.unlink()
        self.assertIn("missing evidence", self.run_writer(1).stderr)
        receipt.write_text("Restored observation\n")
        (self.attempt / "verification.json").unlink()
        self.run_writer(1)

    def test_malformed_and_duplicate_input_fields_are_refused(self):
        for payload in ('{"actor":', '["merger"]', '{"actor":"first","actor":"last"}'):
            with self.subTest(payload=payload):
                self.input_path.write_text(payload, encoding="utf-8")
                prior = {path: path.read_bytes() for path in self.attempt.iterdir()}
                result = self.invoke(self.command())
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual(self.input_path.read_text(encoding="utf-8"), payload)
                self.assertFalse((self.attempt / "integration.json").exists())
                for path, original in prior.items():
                    self.assertEqual(path.read_bytes(), original)

    def test_existing_integration_record_is_never_replaced_even_when_identical(self):
        self.run_writer()
        self.run_writer(1)
        self.validate()

    def test_concurrent_publication_yields_one_complete_winner(self):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        prior = {path: path.read_bytes() for path in self.attempt.iterdir()}
        processes = [
            subprocess.Popen(
                self.command(),
                cwd=self.run_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            for _ in range(2)
        ]
        outputs = [process.communicate(timeout=30) for process in processes]
        self.assertEqual(
            sorted(process.returncode for process in processes), [0, 1], outputs
        )
        for path, payload in prior.items():
            self.assertEqual(path.read_bytes(), payload)
        self.validate()

    def test_occupied_directory_causes_publication_failure_without_prior_mutation(self):
        (self.attempt / "integration.json").mkdir()
        self.run_writer(1)
        self.assertTrue((self.attempt / "integration.json").is_dir())

    def test_help_documents_input_capture_digest_failures_and_exit_meanings(self):
        result = self.invoke([sys.executable, str(WRITER), "integration", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for phrase in (
            "previous_tip_ref",
            "immediately before merging",
            "exact verification.json",
            "SHA-256",
            "failed records",
            "Exit 0",
            "2:",
            "1:",
            "does not merge",
        ):
            self.assertIn(phrase, " ".join(result.stdout.split()))


if __name__ == "__main__":
    unittest.main()
