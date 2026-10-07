"""Exercise the validator CLI against isolated real Git checkouts."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_handoff.py"


class HandoffTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "implement-spec-enhanced-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.checkout = root / "checkout"
        self.checkout.mkdir()
        self.bundle = root / "handoffs"
        self.bundle.mkdir()
        (self.bundle / "receipt.txt").write_text("Synthetic review evidence\n")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Handoff Test")
        self.git("config", "user.email", "handoff-test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(root / "no-hooks"))
        (self.checkout / "spec.md").write_text("Accepted synthetic spec\n")
        (self.checkout / "ticket.md").write_text("A1: synthetic output exists\n")
        self.base = self.commit("Accepted scope")
        (self.checkout / "output.txt").write_text("Synthetic output\n")
        self.head = self.commit("Implement A1")
        self.check = {
            "name": "Synthetic check",
            "status": "passed",
            "method": "Inspect synthetic output in checkout",
            "exit_code": None,
            "evidence": ["receipt.txt"],
        }
        common = {
            "schema_version": 1,
            "ticket": "ticket.md",
            "candidate_commit": self.head,
            "checks": [self.check],
            "limits": [],
        }
        self.candidate = dict(
            deepcopy(common),
            kind="candidate",
            actor="implementer",
            spec="spec.md",
            base_commit=self.base,
            worktree=str(self.checkout),
            owned_files=["output.txt"],
            criteria=["A1"],
        )
        self.verification = dict(
            deepcopy(common),
            kind="verification",
            actor="verifier",
            verdict="PASS",
            criteria=[{"id": "A1", "status": "satisfied", "evidence": ["receipt.txt"]}],
            findings=[],
        )
        self.write(self.candidate)
        self.write(self.verification)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.checkout), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def write(self, record):
        path = self.bundle / f"{record['kind']}.json"
        path.write_text(json.dumps(record), encoding="utf-8")

    def run_cli(self, stage, expected):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.bundle),
                "--stage",
                stage,
                "--checkout",
                str(self.checkout),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def integration(self):
        return {
            "schema_version": 1,
            "kind": "integration",
            "actor": "merger",
            "ticket": "ticket.md",
            "candidate_commit": self.head,
            "checks": [deepcopy(self.check)],
            "limits": [],
            "status": "integrated",
            "previous_tip": self.base,
            "integration_commit": self.head,
            "verification_sha256": hashlib.sha256(
                (self.bundle / "verification.json").read_bytes()
            ).hexdigest(),
        }

    def test_valid_candidate_verification_and_integration(self):
        self.run_cli("candidate", 0)
        self.run_cli("verification", 0)
        self.write(self.integration())
        self.run_cli("integration", 0)

    def test_stale_verification_and_same_actor_are_rejected(self):
        for field, value in (("candidate_commit", self.base), ("actor", "implementer")):
            with self.subTest(field=field):
                record = deepcopy(self.verification)
                record[field] = value
                self.write(record)
                self.run_cli("verification", 1)

    def test_missing_criterion_or_evidence_blocks_approval(self):
        self.verification["criteria"] = []
        self.write(self.verification)
        self.run_cli("verification", 1)
        (self.bundle / "receipt.txt").unlink()
        self.run_cli("candidate", 1)

    def test_rework_and_blocked_are_valid_but_cannot_advance(self):
        for verdict in ("REWORK", "BLOCKED"):
            with self.subTest(verdict=verdict):
                self.verification["verdict"] = verdict
                self.verification["criteria"][0]["status"] = "unverified"
                self.write(self.verification)
                self.run_cli("verification", 2)
                self.write(self.integration())
                self.run_cli("integration", 1)

    def test_unavailable_check_requires_resolution_before_pass(self):
        self.candidate["checks"][0].update(
            status="unavailable", reason="App unavailable"
        )
        self.write(self.candidate)
        self.run_cli("candidate", 0)
        self.verification["checks"][0].update(
            status="unavailable", reason="App unavailable"
        )
        self.write(self.verification)
        self.run_cli("verification", 1)

    def test_evidence_reuse_needs_source_and_reason(self):
        check = self.verification["checks"][0]
        check.update(
            status="reused",
            source_commit=self.head,
            reason="Only ticket metadata changed",
        )
        self.write(self.verification)
        self.run_cli("verification", 0)
        del check["reason"]
        self.write(self.verification)
        self.run_cli("verification", 1)

    def test_modified_verdict_invalidates_integration_record(self):
        self.write(self.integration())
        self.verification["limits"] = ["Additional observation"]
        self.write(self.verification)
        self.run_cli("integration", 1)

    def test_dirty_checkout_or_wrong_head_is_rejected(self):
        (self.checkout / "untracked.txt").write_text("Unexpected work\n")
        self.run_cli("candidate", 1)
        self.commit("Unreviewed change")
        self.run_cli("verification", 1)

    def test_integration_ancestry_and_failures(self):
        record = self.integration()
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        (self.checkout / "other.txt").write_text("Unrelated history\n")
        unrelated = self.commit("Unrelated")
        self.git("checkout", "main")
        record["previous_tip"] = unrelated
        self.write(record)
        self.run_cli("integration", 1)
        record["status"] = "failed"
        self.write(record)
        self.run_cli("integration", 2)


if __name__ == "__main__":
    unittest.main()
