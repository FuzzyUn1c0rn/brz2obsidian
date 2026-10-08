"""Independent verification publication through actual CLIs and Git state."""

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


class VerificationWriterTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "writer-verification-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "assessed"
        self.checkout.mkdir()
        self.run_cwd = self.root
        self.attempt = self.root / "attempt-001"
        self.attempt.mkdir()
        self.input_path = self.root / "verification-input.json"
        self.init_git(
            "Verification Test", "verifier@example.invalid", self.root / "no-hooks"
        )
        (self.checkout / "ticket.md").write_text("A1: produces output\n")
        (self.checkout / "spec.md").write_text("Accepted synthetic spec\n")
        self.base = self.commit("Scope")
        (self.checkout / "output.txt").write_text("Candidate output\n")
        self.head = self.commit("Candidate")
        (self.attempt / "candidate-receipt.txt").write_text("Candidate evidence\n")
        (self.attempt / "review.txt").write_text("Independent observation\n")
        candidate_input = self.root / "candidate-input.json"
        candidate_input.write_text(
            json.dumps(
                {
                    "actor": "implementer",
                    "ticket": "ticket.md",
                    "spec": "spec.md",
                    "base_ref": self.base,
                    "owned_files": ["output.txt"],
                    "criteria": ["A1"],
                    "checks": [
                        {
                            "name": "Candidate check",
                            "status": "passed",
                            "method": "Inspect output in assessed checkout",
                            "exit_code": 0,
                            "evidence": ["candidate-receipt.txt"],
                        }
                    ],
                    "limits": [],
                }
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable,
                str(WRITER),
                "candidate",
                str(self.attempt),
                "--checkout",
                str(self.checkout),
                "--input",
                str(candidate_input),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.data = {
            "actor": "independent-verifier",
            "verdict": "PASS",
            "criteria": [
                {"id": "A1", "status": "satisfied", "evidence": ["review.txt"]}
            ],
            "findings": [],
            "checks": [],
            "limits": ["Synthetic CLI evidence only"],
        }

    def command(self):
        return [
            sys.executable,
            str(WRITER),
            "verification",
            str(self.attempt),
            "--checkout",
            str(self.checkout),
            "--input",
            str(self.input_path),
        ]

    def run_writer(self, expected=0):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        before = self.input_path.read_bytes()
        prior = {
            path: path.read_bytes()
            for path in self.attempt.rglob("*")
            if path.is_file()
        }
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
        for path, payload in prior.items():
            self.assertEqual(path.read_bytes(), payload)
        if expected == 1 and self.attempt / "verification.json" not in prior:
            self.assertFalse((self.attempt / "verification.json").exists())
        return result

    def validate(self, expected=0):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                str(self.attempt),
                "--stage",
                "verification",
                "--checkout",
                str(self.checkout),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_pass_composes_candidate_identity_from_the_selected_attempt(self):
        result = self.run_writer()
        self.assertIn(f"Published {self.attempt / 'verification.json'}", result.stdout)
        self.assertIn("Transition allowed", result.stdout)
        self.assertEqual(
            json.loads((self.attempt / "verification.json").read_bytes()),
            {
                "schema_version": 1,
                "kind": "verification",
                "actor": "independent-verifier",
                "ticket": "ticket.md",
                "candidate_commit": self.head,
                "verdict": "PASS",
                "criteria": [
                    {"id": "A1", "status": "satisfied", "evidence": ["review.txt"]}
                ],
                "findings": [],
                "checks": [],
                "limits": ["Synthetic CLI evidence only"],
            },
        )
        self.validate()

    def test_unknown_criterion_judgments_are_refused_with_the_affected_path(self):
        self.data["criteria"][0]["acceptance"] = "inferred from tests"
        result = self.run_writer(1)
        self.assertIn("criteria[0]", result.stderr)
        self.assertIn("acceptance", result.stderr)

    def test_rework_preserves_failed_judgment_and_publishes_held(self):
        self.data.update(verdict="REWORK", findings=["A1 output.txt: repair needed"])
        self.data["criteria"][0]["status"] = "failed"
        self.data["checks"] = [
            {
                "name": "Output check",
                "status": "failed",
                "exit_code": 1,
                "method": "Inspect output.txt in assessed checkout",
                "reason": "Synthetic output violates A1",
                "evidence": ["review.txt"],
            }
        ]
        result = self.run_writer(2)
        self.assertIn("Published", result.stdout)
        self.assertIn("Transition held", result.stdout)
        record = json.loads((self.attempt / "verification.json").read_bytes())
        for field in ("verdict", "criteria", "findings", "checks", "limits"):
            self.assertEqual(record[field], self.data[field])
        self.validate(2)

    def test_blocked_keeps_required_user_acceptance_unverified(self):
        self.data["verdict"] = "BLOCKED"
        self.data["criteria"][0]["status"] = "unverified"
        self.data["findings"] = ["A1: required actual user verdict is unavailable"]
        self.data["checks"] = [
            {
                "name": "User acceptance",
                "status": "unavailable",
                "exit_code": None,
                "method": "Request actual user observation of A1",
                "reason": "User verdict pending",
                "evidence": ["review.txt"],
            }
        ]
        self.assertIn("Transition held", self.run_writer(2).stdout)
        record = json.loads((self.attempt / "verification.json").read_bytes())
        self.assertEqual(record["verdict"], "BLOCKED")
        self.assertEqual(record["criteria"][0]["status"], "unverified")
        self.validate(2)

    def test_judgments_must_be_explicit_valid_and_free_of_helper_owned_fields(self):
        valid = deepcopy(self.data)
        cases = []
        for field in valid:
            omitted = deepcopy(valid)
            del omitted[field]
            cases.append((omitted, field))
        for field, value in (
            ("actor", ""),
            ("verdict", "pass"),
            ("criteria", {}),
            ("findings", [None]),
            ("checks", None),
            ("limits", "none"),
        ):
            invalid = deepcopy(valid)
            invalid[field] = value
            cases.append((invalid, field))
        for field in (
            "ticket",
            "candidate_commit",
            "schema_version",
            "kind",
            "worktree",
            "base_commit",
            "spec",
            "owned_files",
            "base_ref",
            "surprise",
        ):
            invalid = deepcopy(valid)
            invalid[field] = "override"
            cases.append((invalid, field))
        for invalid, field in cases:
            with self.subTest(field=field, input=invalid):
                self.data = invalid
                result = self.run_writer(1)
                self.assertIn(field, result.stderr)
                self.assertIn(str(self.input_path), result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_criterion_and_check_structures_are_explicit_and_strict(self):
        valid = deepcopy(self.data)
        cases = []
        for field in ("id", "status", "evidence"):
            invalid = deepcopy(valid)
            del invalid["criteria"][0][field]
            cases.append((invalid, field))
        for field, value in (("id", ""), ("status", "passed"), ("evidence", [])):
            invalid = deepcopy(valid)
            invalid["criteria"][0][field] = value
            cases.append((invalid, field))
        invalid = deepcopy(valid)
        invalid["criteria"] = ["A1"]
        cases.append((invalid, "criteria[0]"))
        check = {
            "name": "Public check",
            "status": "passed",
            "method": "Inspect output",
            "exit_code": 0,
            "evidence": ["review.txt"],
        }
        for field in check:
            invalid = deepcopy(valid)
            incomplete = deepcopy(check)
            del incomplete[field]
            invalid["checks"] = [incomplete]
            cases.append((invalid, field))
        invalid = deepcopy(valid)
        invalid["checks"] = [dict(check, surprise=True)]
        cases.append((invalid, "checks[0]"))
        for invalid, field in cases:
            with self.subTest(field=field, input=invalid):
                self.data = invalid
                self.assertIn(field, self.run_writer(1).stderr)

    def test_contradictory_pass_claims_fail_without_publication(self):
        valid = deepcopy(self.data)
        cases = []
        for status in ("failed", "unverified"):
            invalid = deepcopy(valid)
            invalid["criteria"][0]["status"] = status
            cases.append(invalid)
        invalid = deepcopy(valid)
        invalid["findings"] = ["A1 output.txt: blocking observation"]
        cases.append(invalid)
        for status, code in (("failed", 1), ("unavailable", None)):
            invalid = deepcopy(valid)
            invalid["checks"] = [
                {
                    "name": "Required check",
                    "status": status,
                    "exit_code": code,
                    "method": "Inspect output",
                    "reason": "Unresolved requirement",
                    "evidence": ["review.txt"],
                }
            ]
            cases.append(invalid)
        for invalid in cases:
            with self.subTest(input=invalid):
                self.data = invalid
                self.assertIn("PASS", self.run_writer(1).stderr)

    def test_candidate_criterion_coverage_requires_every_id_exactly_once(self):
        original = deepcopy(self.data["criteria"][0])
        for criteria in (
            [],
            [original, deepcopy(original)],
            [dict(original, id="A2")],
            [original, dict(original, id="A2")],
        ):
            with self.subTest(criteria=criteria):
                self.data["criteria"] = criteria
                self.assertIn("exactly once", self.run_writer(1).stderr)

    def test_reuse_rationale_and_source_commit_stay_explicit(self):
        check = {
            "name": "Native observation",
            "status": "reused",
            "exit_code": None,
            "method": "Inspect previously captured native observation",
            "reason": "Output, input and renderer conditions remain applicable",
            "source_commit": self.head,
            "evidence": ["review.txt"],
        }
        for missing in ("reason", "source_commit"):
            with self.subTest(missing=missing):
                invalid = deepcopy(check)
                del invalid[missing]
                self.data["checks"] = [invalid]
                self.assertIn(missing, self.run_writer(1).stderr)
        self.data["checks"] = [check]
        self.run_writer()
        record = json.loads((self.attempt / "verification.json").read_bytes())
        self.assertEqual(record["checks"], [check])
        self.validate()

    def test_missing_evidence_uses_final_attempt_not_input_directory(self):
        (self.root / "review.txt").write_text("Wrong evidence directory\n")
        (self.attempt / "review.txt").unlink()
        self.assertIn("missing evidence", self.run_writer(1).stderr)
        (self.attempt / "review.txt").write_text("Independent evidence\n")
        self.data["checks"] = [
            {
                "name": "Public check",
                "status": "passed",
                "method": "Inspect",
                "exit_code": 0,
                "evidence": ["absent.txt"],
            }
        ]
        self.assertIn("absent.txt", self.run_writer(1).stderr)
        self.data["checks"] = []
        (self.attempt / "candidate-receipt.txt").unlink()
        self.assertIn("candidate-receipt.txt", self.run_writer(1).stderr)

    def test_wrong_or_dirty_checkout_and_nonindependent_actor_are_refused(self):
        self.data["actor"] = "implementer"
        self.assertIn("independent", self.run_writer(1).stderr)
        self.data["actor"] = "independent-verifier"
        (self.checkout / "output.txt").write_text("Uncommitted output\n")
        self.assertIn("clean", self.run_writer(1).stderr)
        self.git("checkout", "--", "output.txt")
        (self.checkout / "unexpected.txt").write_text("Untracked change\n")
        self.assertIn("clean", self.run_writer(1).stderr)
        (self.checkout / "unexpected.txt").unlink()
        self.git("checkout", self.base)
        self.assertIn("HEAD", self.run_writer(1).stderr)

    def test_verification_uses_explicit_checkout_from_outside_its_git_context(self):
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
        self.run_writer()
        record = json.loads((self.attempt / "verification.json").read_bytes())
        self.assertEqual(record["candidate_commit"], self.head)
        self.validate()

    def test_immutable_publication_and_serialization_preserve_selected_attempt(self):
        absolute = self.root / "absolute-review.txt"
        absolute.write_text("Independent absolute evidence\n")
        self.data["criteria"][0]["evidence"].append(str(absolute))
        self.run_writer()
        original = (self.attempt / "verification.json").read_bytes()
        self.assertTrue(original.startswith(b'{\n  "actor": "independent-verifier",\n'))
        self.assertTrue(original.endswith(b"\n"))
        self.assertIn("No record published", self.run_writer(1).stderr)
        self.data["actor"] = ""
        self.run_writer(1)
        self.data["actor"] = "independent-verifier"
        self.validate()
        previous = self.attempt
        self.attempt = self.root / "attempt-002"
        self.attempt.mkdir()
        for filename in ("candidate.json", "candidate-receipt.txt", "review.txt"):
            (self.attempt / filename).write_bytes((previous / filename).read_bytes())
        self.run_writer()
        self.assertEqual((self.attempt / "verification.json").read_bytes(), original)
        self.assertEqual((previous / "verification.json").read_bytes(), original)
        self.validate()

    def test_missing_or_invalid_candidate_cannot_supply_identity(self):
        candidate = self.attempt / "candidate.json"
        original = candidate.read_bytes()
        candidate.unlink()
        self.assertIn("candidate.json", self.run_writer(1).stderr)
        record = json.loads(original)
        record["candidate_commit"] = self.base
        candidate.write_text(json.dumps(record), encoding="utf-8")
        self.assertIn("HEAD", self.run_writer(1).stderr)

    def test_competing_verifiers_publish_one_complete_record(self):
        self.input_path.write_text(json.dumps(self.data), encoding="utf-8")
        prior = {
            path: path.read_bytes()
            for path in self.attempt.rglob("*")
            if path.is_file()
        }
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
        outputs = [process.communicate(timeout=20) for process in processes]
        self.assertEqual(
            sorted(process.returncode for process in processes), [0, 1], outputs
        )
        for path, payload in prior.items():
            self.assertEqual(path.read_bytes(), payload)
        self.assertEqual(
            json.loads((self.attempt / "verification.json").read_bytes())["verdict"],
            "PASS",
        )
        self.validate()

    def test_verification_help_describes_explicit_judgments_and_held_outcomes(self):
        result = subprocess.run(
            [sys.executable, str(WRITER), "verification", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for phrase in (
            "actor",
            "verdict",
            "criteria",
            "findings",
            "checks",
            "limits",
            "PASS",
            "REWORK",
            "BLOCKED",
            "independent",
            "evidence",
            "acceptance",
            "candidate",
            "held",
            "1",
            "2",
        ):
            self.assertIn(phrase, result.stdout)


if __name__ == "__main__":
    unittest.main()
