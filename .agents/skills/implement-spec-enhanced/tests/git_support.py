"""Real Git operations shared by the independently authored CLI fixtures."""

import subprocess


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
