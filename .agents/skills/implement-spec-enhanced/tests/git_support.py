"""Real Git operations shared by the independently authored CLI fixtures."""

import hashlib
import json
import subprocess
from pathlib import Path


class GitCheckout:
    """Operate on the fixture's current checkout without owning test setup."""

    def git(self, *args):
        # Git is a separate producer from the UTF-8 handoff CLIs. These fixtures
        # consume its ASCII commit IDs, refs, counts and synthetic filenames.
        return subprocess.run(
            ["git", "-C", str(self.checkout), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def init_git(self, name, email, hooks_path):
        self.git("init", "-b", "main")
        self.git("config", "user.name", name)
        self.git("config", "user.email", email)
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(hooks_path))

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def fixture_requirements(self, stage):
        candidate = getattr(self, "candidate", None)
        if not isinstance(candidate, str):
            candidate = getattr(self, "head", self.git("rev-parse", "HEAD"))
        return {
            "schema_version": 1,
            "ticket": "ticket.md",
            "stage": stage,
            "candidate_commit": candidate,
            "assessed_commit": self.git("rev-parse", "HEAD")
            if stage == "integration"
            else candidate,
            "environment": "base",
            "checks": [],
        }

    def requirement_args(self, stage):
        path = Path(self.checkout).parent / f"{stage}-requirements.json"
        path.write_text(json.dumps(self.fixture_requirements(stage)), encoding="utf-8")
        return ["--requirements", str(path)]

    def requirement_fields(self, stage):
        data = self.fixture_requirements(stage)
        digest = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "check_requirements": data,
            "check_requirements_sha256": digest,
            "assessed_checkout": str(self.checkout),
        }
