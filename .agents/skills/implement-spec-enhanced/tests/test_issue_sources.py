"""GitHub scope snapshots through the public writer and validator CLIs."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from git_support import GitCheckout

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TICKET = "https://github.com/example/project/issues/12"
SPEC = "https://github.com/example/project/issues/10"


class IssueSourceTests(GitCheckout, unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "tmp" / "issue-source-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.init_git("Issue Test", "issue@example.invalid", self.root / "no-hooks")
        (self.checkout / "output.txt").write_text("Before\n")
        self.base = self.commit("Base")
        (self.checkout / "output.txt").write_text("After\n")
        self.head = self.commit("Candidate")
        self.attempt = self.root / "attempt-001"
        (self.attempt / "sources").mkdir(parents=True)
        self.snapshots = {}
        for key, url in (("ticket", TICKET), ("spec", SPEC)):
            payload = {
                "url": url,
                "title": f"Accepted {key}",
                "body": "A1: output contains After",
                "updatedAt": "2026-10-11T10:00:00Z",
                "comments": [{"body": "Public output boundary approved"}],
            }
            path = self.attempt / "sources" / f"{key}.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.snapshots[key] = f"sources/{key}.json"
        (self.attempt / "observation.txt").write_text("Output is After\n")
        self.data = {
            "actor": "implementer",
            "ticket": TICKET,
            "spec": SPEC,
            "source_snapshots": self.snapshots,
            "base_ref": self.base,
            "owned_files": ["output.txt"],
            "criteria": ["A1"],
            "checks": [],
            "limits": [],
        }

    def fixture_requirements(self, stage):
        return {**super().fixture_requirements(stage), "ticket": self.data["ticket"]}

    def invoke(self, script, args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def publish(self, stage, data, expected=0):
        source = self.root / f"{stage}-input.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        return self.invoke(
            "write_handoff.py",
            [
                stage,
                str(self.attempt),
                "--checkout",
                str(self.checkout),
                "--input",
                str(source),
                *self.requirement_args(stage),
            ],
            expected,
        )

    def validate(self, stage="candidate", expected=0, attempt=None):
        return self.invoke(
            "validate_handoff.py",
            [
                str(attempt or self.attempt),
                "--stage",
                stage,
                "--checkout",
                str(self.checkout),
                *self.requirement_args(stage),
            ],
            expected,
        )

    def test_issue_scope_survives_review_integration_and_retry_without_local_specs(
        self,
    ):
        originals = {
            key: (self.attempt / path).read_bytes()
            for key, path in self.snapshots.items()
        }
        self.publish("candidate", self.data)
        record = json.loads((self.attempt / "candidate.json").read_bytes())
        self.assertEqual(record["ticket"], TICKET)
        self.assertEqual(record["spec"], SPEC)
        for key, payload in originals.items():
            self.assertEqual(
                record["source_snapshots"][key]["sha256"],
                hashlib.sha256(payload).hexdigest(),
            )
        self.publish(
            "verification",
            {
                "actor": "independent-reviewer",
                "verdict": "PASS",
                "criteria": [
                    {"id": "A1", "status": "satisfied", "evidence": ["observation.txt"]}
                ],
                "findings": [],
                "checks": [],
                "limits": [],
            },
        )
        self.publish(
            "integration",
            {
                "actor": "merger",
                "status": "integrated",
                "previous_tip_ref": self.base,
                "checks": [],
                "limits": [],
            },
        )
        self.validate("integration")
        retry = self.root / "attempt-002"
        source = self.root / "retry-input.json"
        source.write_text(
            json.dumps(
                {
                    "reason": "Temporary prerequisite recovered",
                    "carry_verification": True,
                    "verification_reuse_rationale": "Same candidate and preserved accepted scope",
                }
            )
        )
        self.invoke(
            "write_handoff.py",
            [
                "carry-forward",
                str(retry),
                "--from",
                str(self.attempt),
                "--checkout",
                str(self.checkout),
                "--input",
                str(source),
                *self.requirement_args("verification"),
                "--candidate-requirements",
                self.requirement_args("candidate")[1],
            ],
        )
        self.validate("verification", attempt=retry)
        for key, payload in originals.items():
            self.assertEqual((retry / self.snapshots[key]).read_bytes(), payload)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_changed_snapshot_invalidates_existing_candidate(self):
        self.publish("candidate", self.data)
        path = self.attempt / self.snapshots["ticket"]
        path.write_text(path.read_text() + "\n")
        result = self.validate(expected=1)
        self.assertIn("snapshot digest mismatch", result.stderr)

    def test_missing_or_misidentified_issue_scope_is_not_published(self):
        for fault in (
            "missing snapshot",
            "wrong URL",
            "missing comments",
            "missing version",
        ):
            with self.subTest(fault=fault):
                data = json.loads(json.dumps(self.data))
                path = self.attempt / self.snapshots["ticket"]
                original = path.read_bytes()
                if fault == "missing snapshot":
                    del data["source_snapshots"]["ticket"]
                else:
                    content = json.loads(original)
                    if fault == "wrong URL":
                        content["url"] = SPEC
                    else:
                        del content[
                            "comments" if fault == "missing comments" else "updatedAt"
                        ]
                    path.write_text(json.dumps(content))
                try:
                    self.publish("candidate", data, expected=1)
                    self.assertFalse((self.attempt / "candidate.json").exists())
                finally:
                    path.write_bytes(original)

    def test_snapshot_cannot_escape_attempt_or_replace_a_record(self):
        for path in ("../scope.json", str(self.root / "scope.json"), "candidate.json"):
            with self.subTest(path=path):
                data = {
                    **self.data,
                    "source_snapshots": {**self.snapshots, "ticket": path},
                }
                self.publish("candidate", data, expected=1)
                self.assertFalse((self.attempt / "candidate.json").exists())

    def test_non_issue_urls_are_refused(self):
        for reference in (
            "https://github.com/example/project/pull/12",
            TICKET + "#comment",
            "https://example.invalid/issues/12",
        ):
            with self.subTest(reference=reference):
                self.publish("candidate", {**self.data, "spec": reference}, expected=1)
                self.assertFalse((self.attempt / "candidate.json").exists())


if __name__ == "__main__":
    unittest.main()
