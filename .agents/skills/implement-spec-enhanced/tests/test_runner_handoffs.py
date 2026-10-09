"""Receipt enforcement through the published writer and validator commands."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_support import GitCheckout

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[4]


class RunnerHandoffTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "runner-handoff-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.attempt = self.root / "attempt"
        self.attempt.mkdir()
        self.init_git("Receipt Test", "receipt@example.invalid", self.root / "hooks")
        for filename in ("ticket.md", "spec.md", "output.txt"):
            (self.checkout / filename).write_text("Synthetic accepted scope\n")
        self.head = self.commit("Accepted candidate")
        (self.attempt / "observation.txt").write_text("Manual inspection\n")
        self.input = {
            "actor": "worker",
            "ticket": "ticket.md",
            "spec": "spec.md",
            "base_ref": self.head,
            "owned_files": ["output.txt"],
            "criteria": ["A1"],
            "checks": [],
            "limits": [],
        }
        self.requirements = {
            "schema_version": 1,
            "ticket": "ticket.md",
            "stage": "candidate",
            "candidate_commit": self.head,
            "assessed_commit": self.head,
            "environment": "base",
            "checks": [{"id": "lint", "fresh": True}],
        }
        self.input_path = self.root / "input.json"
        self.requirements_path = self.root / "requirements.json"
        self.scripts = SCRIPTS

    def invoke(self, script, *arguments):
        return subprocess.run(
            [sys.executable, str(self.scripts / script), *map(str, arguments)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def publish(self):
        self.input_path.write_text(json.dumps(self.input), encoding="utf-8")
        self.requirements_path.write_text(
            json.dumps(self.requirements), encoding="utf-8"
        )
        return self.invoke(
            "write_handoff.py",
            "candidate",
            self.attempt,
            "--checkout",
            self.checkout,
            "--input",
            self.input_path,
            "--requirements",
            self.requirements_path,
        )

    def test_empty_submitted_checks_cannot_erase_independent_requirement(self):
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing required runner check", result.stderr)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_manual_text_or_unreceipted_runner_pass_cannot_replace_execution(self):
        for kind in ("manual", "runner"):
            self.input["checks"] = [
                {
                    "kind": kind,
                    "check_id": "lint",
                    "name": "Written pass",
                    "status": "passed",
                    "method": "python -m ruff check .",
                    "exit_code": 0,
                    "evidence": ["observation.txt"],
                }
            ]
            result = self.publish()
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn(
                "missing required runner check"
                if kind == "manual"
                else "requires a receipt",
                result.stderr,
            )

    def prepare_execution(self, *, fail=False):
        self.scripts = (
            self.checkout / ".agents" / "skills" / "implement-spec-enhanced" / "scripts"
        )
        shutil.copytree(
            SCRIPTS, self.scripts, ignore=shutil.ignore_patterns("__pycache__")
        )
        (self.checkout / "tools").mkdir()
        for name in ("check.py", "check_pytest.py"):
            shutil.copy2(ROOT / "tools" / name, self.checkout / "tools" / name)
        for package in ("brz2obsidian", "brz2obsidian_ui"):
            path = self.checkout / "src" / package
            path.mkdir(parents=True)
            (path / "__init__.py").write_text("")
        (self.checkout / "tests").mkdir()
        (self.checkout / "tests" / "test_public.py").write_text(
            "import pytest\n\n@pytest.mark.gui\ndef test_public():\n    assert "
            + ("False" if fail else "True")
            + "\n"
        )
        (self.checkout / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\nmarkers = ["gui: synthetic GUI-count contract fixture"]\n'
        )
        (self.checkout / ".gitignore").write_text("tmp/\n__pycache__/\n")
        self.head = self.commit("Executable fixture")
        self.input["base_ref"] = self.head
        self.requirements.update(candidate_commit=self.head, assessed_commit=self.head)
        result = subprocess.run(
            [
                sys.executable,
                str(self.checkout / "tools" / "check.py"),
                "run",
                "--checkout",
                str(self.checkout),
                "--python",
                sys.executable,
                "--environment",
                "auto",
                "--check",
                "pytest",
                "--test",
                "tests/test_public.py",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(
            result.returncode, 1 if fail else 0, result.stdout + result.stderr
        )
        receipt = next((self.checkout / "tmp" / "checks").glob("*/receipt.json"))
        facts = json.loads(receipt.read_text(encoding="utf-8"))
        self.requirements["environment"] = facts["environment"]
        self.requirements["checks"] = [
            {
                "id": "pytest",
                "fresh": True,
                "scope": "focused",
                "selectors": ["tests/test_public.py"],
                "keyword": None,
                "marker": None,
                "require_gui": False,
            }
        ]
        self.input["checks"] = [
            {
                "kind": "runner",
                "check_id": "pytest",
                "name": "Public fixture check",
                "status": "failed" if fail else "passed",
                "method": "tools/check.py run --check pytest --test tests/test_public.py",
                "exit_code": facts["checks"][0]["exit_code"],
                "receipt": str(receipt),
                "evidence": [str(receipt)],
                **({"reason": "Observed assertion failure"} if fail else {}),
            }
        ]
        return receipt, facts

    def validate(self, expected=0):
        result = self.invoke(
            "validate_handoff.py",
            self.attempt,
            "--stage",
            "candidate",
            "--checkout",
            self.checkout,
            "--requirements",
            self.requirements_path,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_real_receipt_publishes_and_independent_validation_rejects_scope_narrowing(
        self,
    ):
        self.prepare_execution()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.validate()
        self.requirements["checks"][0].update(scope="full", selectors=[])
        self.requirements_path.write_text(
            json.dumps(self.requirements), encoding="utf-8"
        )
        result = self.validate(1)
        self.assertIn("independent check requirements mismatch", result.stderr)

    def test_failure_receipt_can_publish_held_but_cannot_claim_pass(self):
        self.prepare_execution(fail=True)
        self.input["checks"][0].update(status="passed", exit_code=0)
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("mismatches receipt", result.stderr)
        self.input["checks"][0].update(status="failed", exit_code=1)
        result = self.publish()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.validate(2)

    def test_plain_text_receipt_and_altered_log_are_rejected(self):
        receipt, facts = self.prepare_execution()
        row = facts["checks"][0]
        log = receipt.parent / row["evidence"][0]["path"]
        log.write_bytes(b"written success")
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("altered output evidence", result.stderr)
        receipt.write_text("passed\n")
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse((self.attempt / "candidate.json").exists())

    def test_explicit_runner_reuse_retains_source_and_cannot_satisfy_fresh_execution(
        self,
    ):
        self.prepare_execution()
        self.input["checks"][0].update(
            status="reused",
            exit_code=None,
            source_commit=self.head,
            reason="Identical candidate contents remain applicable",
        )
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fresh execution", result.stderr)
        self.requirements["checks"][0]["fresh"] = False
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.validate()

    def test_verifier_must_produce_own_fresh_receipt_in_assessed_checkout(self):
        original_receipt, _ = self.prepare_execution()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        verifier = self.root / "verifier"
        subprocess.run(
            ["git", "clone", "--quiet", str(self.checkout), str(verifier)],
            check=True,
            capture_output=True,
        )
        self.checkout = verifier
        self.requirements["stage"] = "verification"
        self.input = {
            "actor": "independent-verifier",
            "verdict": "PASS",
            "criteria": [
                {"id": "A1", "status": "satisfied", "evidence": ["observation.txt"]}
            ],
            "findings": [],
            "limits": [],
            "checks": self.input["checks"],
        }
        self.input_path.write_text(json.dumps(self.input), encoding="utf-8")
        self.requirements_path.write_text(
            json.dumps(self.requirements), encoding="utf-8"
        )

        def publish_verification():
            return self.invoke(
                "write_handoff.py",
                "verification",
                self.attempt,
                "--checkout",
                verifier,
                "--input",
                self.input_path,
                "--requirements",
                self.requirements_path,
            )

        result = publish_verification()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fresh runner receipt", result.stderr)
        self.assertEqual(self.input["checks"][0]["receipt"], str(original_receipt))
        run = subprocess.run(
            [
                sys.executable,
                str(verifier / "tools" / "check.py"),
                "run",
                "--checkout",
                str(verifier),
                "--python",
                sys.executable,
                "--check",
                "pytest",
                "--test",
                "tests/test_public.py",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        fresh = next((verifier / "tmp" / "checks").glob("*/receipt.json"))
        self.input["checks"][0].update(receipt=str(fresh), evidence=[str(fresh)])
        self.input_path.write_text(json.dumps(self.input), encoding="utf-8")
        result = publish_verification()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.invoke(
            "validate_handoff.py",
            self.attempt,
            "--stage",
            "verification",
            "--checkout",
            verifier,
            "--requirements",
            self.requirements_path,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_historical_record_is_read_only_and_explicit_reuse_is_never_fresh(self):
        historical_directory = self.root / "historical"
        historical_directory.mkdir()
        (historical_directory / "observation.txt").write_text("Original observation\n")
        old = {key: value for key, value in self.input.items() if key != "base_ref"}
        old.update(
            schema_version=1,
            kind="candidate",
            candidate_commit=self.head,
            base_commit=self.head,
            worktree=str(self.checkout),
            checks=[
                {
                    "name": "Historical lint",
                    "status": "passed",
                    "method": "Observed lint check",
                    "exit_code": 0,
                    "evidence": ["observation.txt"],
                }
            ],
        )
        historical_path = historical_directory / "candidate.json"
        historical_path.write_text(json.dumps(old), encoding="utf-8")
        before = historical_path.read_bytes()
        result = self.invoke(
            "validate_handoff.py",
            historical_directory,
            "--stage",
            "candidate",
            "--checkout",
            self.checkout,
            "--historical",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("not approval", result.stdout)
        self.input["checks"] = [
            {
                "kind": "historical",
                "check_id": "lint",
                "name": "Historical lint reuse",
                "status": "reused",
                "method": "Original lint execution",
                "exit_code": None,
                "evidence": [str(historical_path)],
                "reason": "Reviewer assessed unchanged behavior and conditions",
                "source_commit": self.head,
                "source_record": str(historical_path),
                "source_check": 0,
            }
        ]
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fresh execution", result.stderr)
        self.requirements["checks"][0]["fresh"] = False
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.validate()
        self.assertEqual(historical_path.read_bytes(), before)

    def test_carry_refuses_fresh_demand_before_copying_and_preserves_original_execution(
        self,
    ):
        self.prepare_execution()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        original = (self.attempt / "candidate.json").read_bytes()
        carry_input = self.root / "carry-input.json"
        carry_input.write_text(
            json.dumps(
                {
                    "reason": "Identical contents; unavailable prerequisite recovered",
                    "carry_verification": False,
                }
            ),
            encoding="utf-8",
        )
        source = self.attempt
        destination = self.root / "retry-2"

        def carry(origin, target):
            return self.invoke(
                "write_handoff.py",
                "carry-forward",
                target,
                "--from",
                origin,
                "--checkout",
                self.checkout,
                "--input",
                carry_input,
                "--requirements",
                self.requirements_path,
            )

        result = carry(source, destination)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fresh execution", result.stderr)
        self.assertFalse(destination.exists())
        self.requirements["checks"][0]["fresh"] = False
        self.requirements_path.write_text(
            json.dumps(self.requirements), encoding="utf-8"
        )
        result = carry(source, destination)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((destination / "candidate.json").read_bytes(), original)
        self.attempt = destination
        self.validate()
        third = self.root / "retry-3"
        result = carry(destination, third)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((third / "candidate.json").read_bytes(), original)
        self.attempt = third
        self.validate()

    def test_full_and_additional_focused_requirements_are_enforced_separately(self):
        self.prepare_execution()
        extra = self.checkout / "additional"
        extra.mkdir()
        (extra / "test_extra.py").write_text("def test_extra():\n    assert True\n")
        self.head = self.commit("Additional tests outside full configured selection")
        self.input["base_ref"] = self.head
        self.requirements.update(candidate_commit=self.head, assessed_commit=self.head)

        def run(*arguments):
            before = set((self.checkout / "tmp" / "checks").glob("*/receipt.json"))
            result = subprocess.run(
                [
                    sys.executable,
                    str(self.checkout / "tools" / "check.py"),
                    "run",
                    "--checkout",
                    str(self.checkout),
                    "--python",
                    sys.executable,
                    "--check",
                    "pytest",
                    *arguments,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return (
                set((self.checkout / "tmp" / "checks").glob("*/receipt.json")) - before
            ).pop()

        full = run()
        primary = self.requirements["checks"][0]
        primary.update(scope="full", selectors=[], requirement_key="full-suite")
        focused = dict(
            primary,
            scope="focused",
            selectors=["additional/test_extra.py"],
            requirement_key="handoff-tests",
        )
        self.requirements["checks"].append(focused)
        full_check = self.input["checks"][0]
        full_check.update(
            receipt=str(full), evidence=[str(full)], requirement_key="full-suite"
        )
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("missing required runner check", result.stderr)
        separate = dict(full_check, requirement_key="handoff-tests")
        self.input["checks"].append(separate)
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("did not execute required focused selector", result.stderr)
        additional_receipt = run("--test", "additional/test_extra.py")
        separate.update(
            receipt=str(additional_receipt), evidence=[str(additional_receipt)]
        )
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.validate()

    def test_unavailable_partial_evidence_stays_honest_and_blocks_pass(self):
        partial = self.attempt / "incomplete-receipt.json"
        partial.write_text('{"aggregate": "incomplete",')
        unavailable = {
            "kind": "runner",
            "check_id": "lint",
            "name": "Unavailable lint",
            "status": "unavailable",
            "method": "Runner setup attempted",
            "exit_code": None,
            "evidence": [str(partial), "observation.txt"],
            "receipt": str(partial),
            "reason": "Interpreter prerequisite unavailable",
        }
        self.input["checks"] = [unavailable]
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.requirements["stage"] = "verification"
        self.input = {
            "actor": "independent-verifier",
            "verdict": "BLOCKED",
            "criteria": [
                {"id": "A1", "status": "unverified", "evidence": ["observation.txt"]}
            ],
            "findings": ["Required interpreter unavailable"],
            "checks": [unavailable],
            "limits": [],
        }
        self.input_path.write_text(json.dumps(self.input), encoding="utf-8")
        self.requirements_path.write_text(
            json.dumps(self.requirements), encoding="utf-8"
        )
        result = self.invoke(
            "write_handoff.py",
            "verification",
            self.attempt,
            "--checkout",
            self.checkout,
            "--input",
            self.input_path,
            "--requirements",
            self.requirements_path,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        result = self.invoke(
            "validate_handoff.py",
            self.attempt,
            "--stage",
            "verification",
            "--checkout",
            self.checkout,
            "--requirements",
            self.requirements_path,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        original = (self.attempt / "verification.json").read_bytes()
        self.input.update(verdict="PASS", findings=[])
        self.input["criteria"][0]["status"] = "satisfied"
        self.input_path.write_text(json.dumps(self.input), encoding="utf-8")
        result = self.invoke(
            "write_handoff.py",
            "verification",
            self.attempt,
            "--checkout",
            self.checkout,
            "--input",
            self.input_path,
            "--requirements",
            self.requirements_path,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("PASS requires", result.stderr)
        self.assertEqual((self.attempt / "verification.json").read_bytes(), original)

    def test_mixed_failed_run_preserves_later_passing_result_and_holds_transition(self):
        self.prepare_execution(fail=True)
        before = set((self.checkout / "tmp" / "checks").glob("*/receipt.json"))
        result = subprocess.run(
            [
                sys.executable,
                str(self.checkout / "tools" / "check.py"),
                "run",
                "--checkout",
                str(self.checkout),
                "--python",
                sys.executable,
                "--check",
                "pytest",
                "--test",
                "tests/test_public.py",
                "--check",
                "dependency",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        receipt = (
            set((self.checkout / "tmp" / "checks").glob("*/receipt.json")) - before
        ).pop()
        self.input["checks"][0].update(receipt=str(receipt), evidence=[str(receipt)])
        self.input["checks"].append(
            {
                "kind": "runner",
                "check_id": "dependency",
                "name": "Dependency check after failed pytest",
                "status": "passed",
                "method": "tools/check.py run --check pytest --check dependency",
                "exit_code": 0,
                "receipt": str(receipt),
                "evidence": [str(receipt)],
            }
        )
        self.requirements["checks"].append({"id": "dependency", "fresh": True})
        result = self.publish()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.validate(2)


if __name__ == "__main__":
    unittest.main()
