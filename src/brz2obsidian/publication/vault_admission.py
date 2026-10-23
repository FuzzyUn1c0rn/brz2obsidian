"""Read-only Git and filesystem admission for authored vault checkpoints.

Discovery refuses foreign stores before issuing repository commands. Git commands
never refresh the user's index, execute storage policy, fetch, or repair objects.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path

from brz2obsidian.application.vault_contracts import (
    VaultAdmission,
    VaultFile,
    VaultFinding,
    VaultRepository,
    VaultSubject,
)
from brz2obsidian.contracts import ReviewConsentRequirement, ReviewPreflight
from brz2obsidian.publication.git_read import OUTPUT_BUDGET, read_git
from brz2obsidian.publication.vault_attributes import (
    AttributeCapabilityUnavailable,
    assigned_markers,
    index_extensions,
)
from brz2obsidian.publication.vault_native import observe_file, verify_directory

HOOKS = frozenset(
    (
        "applypatch-msg",
        "pre-applypatch",
        "post-applypatch",
        "pre-commit",
        "pre-merge-commit",
        "prepare-commit-msg",
        "commit-msg",
        "post-commit",
        "pre-rebase",
        "post-checkout",
        "post-merge",
        "pre-push",
        "pre-receive",
        "update",
        "proc-receive",
        "post-receive",
        "post-update",
        "reference-transaction",
        "push-to-checkout",
        "pre-auto-gc",
        "post-rewrite",
        "sendemail-validate",
        "fsmonitor-watchman",
        "p4-changelist",
        "p4-prepare-changelist",
        "p4-post-changelist",
        "p4-pre-submit",
        "post-index-change",
    )
)
CAPABILITIES = frozenset(
    (
        "config",
        "rev-parse",
        "ls-files",
        "check-attr",
        "check-ignore",
        "fsck",
        "cat-file",
        "hash-object",
        "mktree",
        "commit-tree",
        "update-ref",
        "update-index",
        "for-each-ref",
    )
)
_QUALIFIED_OPTIONS = {}
_COMMAND_NAMES = {}
CACHE_PATHS = (".obsidian/cache", ".obsidian/.cache")
TEMP_PATHS = (".brz2obsidian/tmp",)
FALSE = ("false", "0", "no", "off", "")


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


def _configured_hook_state(raw, boolean=None):
    """Preserve ordered event resets and case-sensitive configured hook names."""
    values = raw.decode("utf-8").split("\0")
    bindings, parallel, commands, disabled = {}, set(), {}, set()
    for i in range(0, len(values) - 2, 3):
        key, separator, value = values[i + 2].partition("\n")
        section, dot, rest = key.partition(".")
        name, middle, variable = rest.rpartition(".")
        if section.lower() != "hook" or not dot or not middle:
            continue
        if not separator:
            raise OSError("Configured hook keys require a value")
        variable = variable.lower()
        if variable == "command":
            commands[name] = value
        elif variable == "parallel":
            enabled = boolean(value) if boolean else value.lower() not in FALSE
            if enabled is not None:
                (parallel.add if enabled else parallel.discard)(name)
        elif variable == "event":
            if value:
                if name in HOOKS:
                    raise OSError(
                        "Known hook event cannot be a configured friendly name"
                    )
                bindings.setdefault(name, set()).add(value)
            else:
                bindings.pop(name, None)
        elif variable == "enabled":
            enabled = boolean(value) if boolean else value.lower() not in FALSE
            if enabled is False:
                disabled.add(name)
            elif enabled is True:
                disabled.discard(name)
    friendly = set(commands) | parallel | set(bindings)
    if any(
        name not in commands and events and name not in disabled
        for name, events in bindings.items()
    ):
        raise OSError("Configured hook event has no command")
    active = tuple(
        (name, event)
        for name, events in bindings.items()
        for event in events
        if event in HOOKS
        and name not in disabled
        and (event in friendly or event not in disabled)
    )
    return active, friendly, commands


def _unsafe(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def _bare(path):
    def kind(name, expected):
        try:
            return expected((path / name).lstat().st_mode)
        except FileNotFoundError:
            return False

    return (
        kind("HEAD", stat.S_ISREG)
        and kind("objects", stat.S_ISDIR)
        and kind("refs", stat.S_ISDIR)
    )


def _exists(path):
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _existing_git_operation_blockers(gitdir):
    """Observe the existing Git operation and lock blockers without history reads."""
    markers = (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "REBASE_HEAD",
        "BISECT_START",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
    )
    locks = [
        gitdir / name
        for name in (
            "index.lock",
            "HEAD.lock",
            "packed-refs.lock",
            "config.lock",
            "shallow.lock",
            "gc.pid",
            "gc.log.lock",
            "maintenance.lock",
        )
    ]
    locks.extend(
        path
        for prefix in ("refs", "logs", "objects")
        for path in (gitdir / prefix).rglob("*.lock")
    )
    return any(_exists(gitdir / name) for name in markers), any(
        _exists(path) for path in locks
    )


def _safe_relative(value):
    p = Path(value)
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
    return (
        bool(value)
        and not p.is_absolute()
        and not p.drive
        and "\\" not in value
        and all(
            part.casefold() not in ("", ".", "..", ".git")
            and part == part.rstrip(" .")
            and part.split(".")[0].casefold() not in reserved
            and ":" not in part
            and (
                os.name != "nt"
                or not any(ord(char) < 32 or char in '?*<>|"' for char in part)
            )
            for part in value.split("/")
        )
    )


def _walk(path):
    pending = [Path(path)]
    size = 0
    while pending:
        current = pending.pop()
        verify_directory(current)
        names, files = [], []
        with os.scandir(current) as entries:
            for entry in entries:
                size += len(entry.name.encode("utf-8")) + 128
                if size > OUTPUT_BUDGET:
                    raise OSError(
                        "Directory observation exceeds its safe resource budget"
                    )
                (names if entry.is_dir(follow_symlinks=False) else files).append(
                    entry.name
                )
        yield str(current), names, files
        pending.extend(current / name for name in reversed(names))


def _file_digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


class _Inspection:
    def __init__(
        self,
        vault,
        subjects,
        executable,
        active_operation=None,
        recovery_observation=None,
    ):
        self.root = Path(vault).absolute()
        self.subjects = ()
        self.request_subjects = subjects
        self.active_operation = active_operation
        self.recovery_observation = recovery_observation
        self.validated_active_operation = False
        self.linked_intents = []
        self.executable = (
            str(executable) if executable is not None else shutil.which("git")
        )
        self.explicit_executable = executable is not None
        self.version = None
        self.capabilities = ()
        self.option_key = None
        self.tracked_paths = set()
        self.index_stages = ()
        self.resources = ExitStack()
        self.ignored_paths = set()
        self.findings = []
        self.inventory = []
        self.prefixes = {}
        self.exclusions = set()
        self.file_observations = set()
        self.complete = False
        self.history = None
        self.repo = VaultRepository(
            kind="unknown",
            root=None,
            git_directory=None,
            common_directory=None,
            object_directory=None,
            head=None,
            object_format=None,
            ref_format=None,
        )
        self.config = {}
        self.policy = []
        self.storage_state = []
        self.consents = []
        self.operation = "unknown"
        self.suppress_monitor = False
        self.policy_view = None
        self.view_env = None
        self.view_config = ()
        # No prompt, lazy object fetch, optional index write, replace-object view,
        # or pager. Effective inherited config is still read before suppression.
        self.env = {
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
        self.env["LC_ALL"] = "C"
        for name in tuple(self.env):
            if name.startswith("GIT_TRACE") or name in (
                "GIT_REDIRECT_STDERR",
                "GIT_REDIRECT_STDOUT",
                "GIT_REDIRECT_STDIN",
            ):
                del self.env[name]

    def finding(self, code, policy, message, paths=()):
        self.findings.append(
            VaultFinding(code=code, policy=policy, message=message, paths=tuple(paths))
        )

    def git(self, *args, input=None, allowed=(0,), environment=None):
        prefix = [self.executable, "--no-pager", "--no-replace-objects"]
        if self.suppress_monitor:
            prefix += ["-c", "core.fsmonitor=false"]
        if self.policy_view:
            prefix += ["--git-dir=" + self.policy_view, "--work-tree=" + str(self.root)]
            for key, value in self.view_config:
                prefix += ["-c", key + "=" + value]
        effective_environment = (
            environment if environment is not None else self.view_env or self.env
        )
        if args and args[0] in ("ls-files", "check-attr", "check-ignore"):
            # These internal queries use exact paths/trusted magic, independently
            # of optional command-line pathspec interpretation in the caller.
            effective_environment = dict(effective_environment)
            for name in (
                "GIT_LITERAL_PATHSPECS",
                "GIT_GLOB_PATHSPECS",
                "GIT_NOGLOB_PATHSPECS",
                "GIT_ICASE_PATHSPECS",
            ):
                effective_environment.pop(name, None)
        result = read_git(
            [*prefix, "-C", str(self.root), *args],
            input=input,
            env=effective_environment,
        )
        if result.returncode not in allowed:
            raise OSError("Git could not establish a complete observation")
        if result.returncode == 0 and result.stderr:
            raise OSError("Git reported an incomplete observation")
        return result.stdout

    def text(self, *args, **kwargs):
        return self.git(*args, **kwargs).decode("utf-8").rstrip("\r\n")

    def layout(self):
        root = self.root
        if not root.is_dir():
            self.finding(
                "vault_unavailable",
                "inventory",
                "Choose an existing readable vault directory.",
            )
            return False
        if any(_unsafe(p) for p in (root, *root.parents)):
            self.finding(
                "reparse_path",
                "layout",
                "Choose a vault with ordinary physical path components.",
            )
            return False
        self.storage_state.append(
            verify_directory(root, writable=not os.path.lexists(root / ".git"))
        )
        if any(_exists(p / ".git") or _bare(p) for p in root.parents):
            self.finding(
                "parent_repository",
                "layout",
                "Choose a vault outside the parent repository.",
            )
            return False
        if _bare(root):
            self.finding(
                "bare_repository",
                "layout",
                "Choose a complete non-bare vault worktree.",
            )
            return False
        if any(
            k in os.environ
            for k in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_INDEX_FILE",
                "GIT_NAMESPACE",
                "GIT_SHALLOW_FILE",
                "GIT_GRAFT_FILE",
            )
        ):
            self.finding(
                "redirected_environment",
                "layout",
                "Remove redirected Git storage from the launching environment.",
            )
            return False
        if os.environ.get("GIT_ATTR_SOURCE"):
            self.finding(
                "attribute_source",
                "storage",
                "A redirected attribute source requires a current working-tree policy observation.",
            )
            return False
        for subject in self.subjects:
            if not _safe_relative(subject.path):
                self.finding(
                    "unsafe_subject",
                    "inventory",
                    "Review subjects must name safe vault-relative paths.",
                )
                return False
        if len({s.path for s in self.subjects}) != len(self.subjects):
            self.finding(
                "duplicate_subject",
                "inventory",
                "Review subjects must identify unique paths.",
            )
            return False
        gitdir = root / ".git"
        if os.path.lexists(gitdir):
            if _unsafe(gitdir) or not gitdir.is_dir():
                self.finding(
                    "redirected_layout",
                    "layout",
                    "Linked, redirected and submodule Git stores are initially unsupported.",
                )
                return False
            if not (gitdir / "HEAD").is_file() or not (gitdir / "objects").is_dir():
                self.finding(
                    "object_integrity",
                    "git",
                    "Required local Git metadata/object storage is missing; restore matching complete history.",
                )
                return False
            if any(
                (gitdir / p).exists()
                for p in ("commondir", "gitdir", "worktrees", "modules")
            ):
                self.finding(
                    "shared_layout",
                    "layout",
                    "Use a self-contained repository without linked worktrees or submodules.",
                )
                return False
            if (gitdir / "index").exists():
                info, _, raw, _ = observe_file(
                    gitdir, gitdir / "index", prefix_limit=OUTPUT_BUDGET + 1
                )
                if info.st_size > OUTPUT_BUDGET or len(raw) != info.st_size:
                    raise OSError("Git index exceeds its safe observation budget")
                extensions = index_extensions(raw)
                if extensions is None:
                    self.finding(
                        "unsupported_format",
                        "git",
                        "This index object format needs compatibility qualification before preparation.",
                    )
                    return False
                if any(name in (b"link", b"sdir") for name in extensions):
                    self.finding(
                        "index_layout",
                        "layout",
                        "Split and sparse index storage need compatibility qualification before preparation.",
                    )
                    return False
            for directory, names, files in _walk(gitdir):
                verify_directory(Path(directory))
                for name in (*names, *files):
                    item = Path(directory) / name
                    if _unsafe(item) or item.is_file() and item.lstat().st_nlink != 1:
                        self.finding(
                            "external_store",
                            "layout",
                            "Git metadata must not use reparse or external paths.",
                        )
                        return False
            if (gitdir / "objects" / "info" / "alternates").exists() or (
                gitdir / "objects" / "info" / "http-alternates"
            ).exists():
                self.finding(
                    "external_store",
                    "layout",
                    "Alternate object stores are initially unsupported.",
                )
                return False
            if _exists(gitdir / "info" / "grafts"):
                self.finding(
                    "incomplete_store",
                    "git",
                    "Grafted history cannot establish complete raw ancestry; use matching complete local history.",
                )
                return False
            self.repo = self.repo.model_copy(
                update={
                    "kind": "root",
                    "root": str(root),
                    "git_directory": str(gitdir),
                    "common_directory": str(gitdir),
                    "object_directory": str(gitdir / "objects"),
                }
            )
            self.storage_state.append(verify_directory(gitdir, writable=True))
        else:
            self.repo = self.repo.model_copy(update={"kind": "none"})
        # Inspect names without entering nested stores or following reparses.
        for directory, names, files in _walk(root):
            base = Path(directory)
            verify_directory(base)
            if base == root:
                names[:] = [n for n in names if n.casefold() != ".git"]
            if base != root and (
                any(name.casefold() == ".git" for name in (*names, *files))
                or _bare(base)
            ):
                self.finding(
                    "nested_repository",
                    "layout",
                    "Move nested repositories/submodules outside this vault.",
                    (base.relative_to(root).as_posix(),),
                )
                return False
            for name in (*names, *files):
                if base == root and name.casefold() == ".git":
                    continue
                if _unsafe(base / name):
                    self.finding(
                        "reparse_path",
                        "layout",
                        "Authored inventory cannot follow reparse points.",
                        ((base / name).relative_to(root).as_posix(),),
                    )
                    return False
            verify_directory(base)
            names[:] = [n for n in names if not self.excluded_directory(base / n)]
        return True

    def excluded_directory(self, path):
        relative = path.relative_to(self.root).as_posix()
        if relative == ".brz2obsidian":
            return True
        if relative in (*CACHE_PATHS, *TEMP_PATHS):
            self.exclusions.add(relative)
            return True
        return False

    def effective_config(self):
        result = read_git(
            [
                self.executable,
                "--no-pager",
                "--no-replace-objects",
                "-C",
                str(self.root),
                "config",
                "--null",
                "--show-origin",
                "--show-scope",
                "--list",
            ],
            env=self.env,
        )
        if result.returncode or result.stderr:
            raise OSError("Effective Git policy is unavailable")
        return result.stdout

    def qualify_options(self):
        if self.repo.kind == "none":
            locations = self.locations()
            if locations is None:
                return False
            _, actual_git, common, objects, object_format, ref_format = locations
            if (
                object_format != "sha1"
                or ref_format != "files"
                or Path(common) != Path(self.policy_view)
                or Path(actual_git) != Path(self.policy_view)
                or Path(objects) != Path(self.policy_view) / "objects"
            ):
                self.finding(
                    "git_capability",
                    "git",
                    "Install a Git build providing the required local object/ref formats and plumbing options.",
                )
                return False
        # Cache executable option semantics only for the actual discovered native
        # binary's unchanged bytes. Repository formats/policy are always fresh.
        if self.option_key not in _QUALIFIED_OPTIONS:
            checks = (
                ("mktree", ("-z", "--batch")),
                ("commit-tree", ("-p", "-F")),
                ("update-ref", ("--stdin", "-z", "--no-deref")),
                ("update-index", ("--index-info", "--info-only", "-z")),
            )
            for command, options in checks:
                help_text = self.text(command, "-h", allowed=(0, 129)).replace(
                    "--[no-]", "--"
                )
                if any(option not in help_text for option in options):
                    self.finding(
                        "git_capability",
                        "git",
                        "Install Git with the required local history plumbing options.",
                    )
                    return False
            if (
                self.text("hash-object", "--no-filters", "--stdin", input=b"")
                != "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
            ):
                self.finding(
                    "git_capability",
                    "git",
                    "Git could not establish exact raw-byte SHA-1 storage capability.",
                )
                return False
            if self.git("cat-file", "--batch-check", input=b""):
                self.finding(
                    "git_capability",
                    "git",
                    "Git could not establish bounded local object inspection.",
                )
                return False
            if self.option_key:
                _QUALIFIED_OPTIONS[self.option_key] = True
        self.capabilities += (
            "raw-sha1-no-filters",
            "files-refs",
            "absolute-git-paths",
            "nul-policy-index",
            "local-object-batch",
            "history-plumbing-options",
        )
        return True

    def locations(self):
        values = self.text(
            "rev-parse",
            "--path-format=absolute",
            "--show-toplevel",
            "--absolute-git-dir",
            "--git-common-dir",
            "--git-path",
            "objects",
            "--show-object-format",
            "--show-ref-format",
        ).splitlines()
        if len(values) != 6 or any(not Path(path).is_absolute() for path in values[:4]):
            self.finding(
                "git_capability",
                "git",
                "Install Git providing the required absolute layout/object/reference observations.",
            )
            return None
        return values

    def hook_boolean(self, value):
        text = value.lower()
        if text in FALSE:
            return False
        if text in ("true", "1", "yes", "on"):
            return True
        # Ask the qualified Git Boolean parser about this exact raw occurrence;
        # reading the original key would collapse ordered duplicate values.
        key = "brz2obsidian.internalbool"
        parsed = read_git(
            [
                self.executable,
                "--no-pager",
                "-C",
                str(self.root),
                "-c",
                key + "=" + value,
                "config",
                "--type=bool",
                "--get",
                key,
            ],
            env=self.env,
        )
        if (
            parsed.returncode == 0
            and not parsed.stderr
            and parsed.stdout in (b"true\n", b"false\n")
        ):
            return parsed.stdout == b"true\n"
        if (
            parsed.returncode == 128
            and parsed.stderr.startswith(b"fatal: bad boolean config value '")
            and parsed.stderr.rstrip().endswith(b"for 'brz2obsidian.internalbool'")
        ):
            return None
        raise OSError("Git Boolean policy observation unavailable")

    def configuration(self):
        raw = self.effective_config()
        self.policy.append(raw.hex())
        active_hooks, _, _ = _configured_hook_state(raw, self.hook_boolean)
        if active_hooks:
            self.finding(
                "configured_hook",
                "execution",
                "Active configured Git hooks require a supported repository policy.",
            )
        values = raw.decode("utf-8").split("\0")
        for i in range(0, len(values) - 2, 3):
            key, _, value = values[i + 2].partition("\n")
            section, _, rest = key.partition(".")
            subsection, separator, variable = rest.rpartition(".")
            normalized = section.lower() + "."
            normalized += (
                subsection + "." + variable.lower() if separator else rest.lower()
            )
            self.config[normalized] = value
        c = self.config
        if c.get("attr.tree"):
            self.finding(
                "attribute_source",
                "storage",
                "A redirected attribute source requires working-tree policy revalidation.",
            )
        if c.get("core.fsmonitor", "false").lower() not in (
            *FALSE,
            "true",
            "1",
            "yes",
            "on",
        ):
            self.finding(
                "fsmonitor",
                "execution",
                "An applicable custom filesystem-monitor command is unsupported.",
            )
        self.suppress_monitor = True
        if c.get("core.bare", "false").lower() not in FALSE or "core.worktree" in c:
            self.finding(
                "redirected_layout",
                "layout",
                "Use an ordinary repository rooted at the vault.",
            )
        if (
            c.get("core.sparsecheckout", "false").lower() not in FALSE
            or c.get("index.sparse", "false").lower() not in FALSE
        ):
            self.finding(
                "sparse_checkout",
                "layout",
                "Sparse checkout/index must be completed outside the converter.",
            )
        if any(
            k in c for k in ("extensions.partialclone", "extensions.worktreeconfig")
        ) or any(
            k.endswith(".promisor") and v.lower() not in FALSE for k, v in c.items()
        ):
            self.finding(
                "incomplete_store",
                "layout",
                "Partial/promisor and shared worktree repositories are initially unsupported.",
            )
        if c.get("core.repositoryformatversion", "0") not in ("0", "1"):
            self.finding(
                "unsupported_format",
                "git",
                "This repository format requires compatibility qualification before preparation.",
            )
        if self.repo.kind == "root":
            gitdir = Path(self.repo.git_directory)
            if (gitdir / "shallow").exists() or any(
                (gitdir / "objects" / "pack").glob("*.promisor")
            ):
                self.finding(
                    "incomplete_store",
                    "layout",
                    "Shallow/promisor history must be made complete outside the converter.",
                )
        if self.repo.kind == "root" or "core.hookspath" in c:
            location = (
                self.text("config", "--path", "--get", "core.hooksPath")
                if "core.hookspath" in c
                else None
            )
            hooks = (
                Path(location)
                if location is not None
                else Path(self.repo.git_directory) / "hooks"
            )
            if not hooks.is_absolute():
                hooks = self.root / hooks
            if hooks.exists():
                if _unsafe(hooks) or not hooks.is_dir():
                    self.finding(
                        "hooks_unknown",
                        "execution",
                        "The effective hook location cannot be safely inspected.",
                    )
                else:
                    for hook in hooks.iterdir():
                        name = hook.name.casefold() if os.name == "nt" else hook.name
                        if (
                            name.removesuffix(".exe") in HOOKS
                            and hook.is_file()
                            and (os.name == "nt" or os.access(hook, os.X_OK))
                        ):
                            self.finding(
                                "active_hook",
                                "execution",
                                "Active Git hooks require a supported repository policy.",
                            )
                            break
        return not self.findings

    def repository(self):
        if self.repo.kind == "none":
            return True
        gitdir = Path(self.repo.git_directory)
        locations = self.locations()
        if locations is None:
            return False
        actual, actual_git, common, objects, object_format, ref_format = locations
        if (
            Path(actual) != self.root
            or Path(common) != gitdir
            or Path(actual_git) != gitdir
            or Path(objects) != gitdir / "objects"
        ):
            self.finding(
                "shared_layout",
                "layout",
                "Git must resolve to the vault's self-contained local store.",
            )
            return False
        if object_format != "sha1" or ref_format != "files":
            self.finding(
                "unsupported_format"
                if object_format in ("sha1", "sha256")
                and ref_format in ("files", "reftable")
                else "git_capability",
                "git",
                "This object/reference format needs compatibility qualification before writes.",
            )
            return False
        self.repo = self.repo.model_copy(
            update={"object_format": object_format, "ref_format": ref_format}
        )
        git_operation, foreign_lock = _existing_git_operation_blockers(gitdir)
        if git_operation:
            self.finding(
                "git_operation",
                "operation",
                "Finish the existing Git operation before preparing converter work.",
            )
            self.operation = "active"
        if foreign_lock:
            self.finding(
                "foreign_lock",
                "operation",
                "An existing Git lock requires its owner's completion or recovery.",
            )
            self.operation = "active"
        if self.recovery_observation is not None:
            from brz2obsidian.publication.vault_apply import _OperationObservation
            from brz2obsidian.publication.vault_recovery import _lease_free

            retained = self.recovery_observation
            if not isinstance(retained, _OperationObservation):
                raise OSError("Recovery observation has no validated authority")
            operation = retained.graph.intent
            ref = (
                "refs/brz2obsidian/imports/"
                + operation.association_id
                + "/operations/"
                + operation.operation_id
            )
            current = self.git("rev-parse", "--verify", ref).decode().strip()
            locator = retained.checkpoint.locator
            if retained.checkpoint.status != "valid" or locator is None:
                raise OSError("Recovery checkpoint association is unavailable")
            checkpoint_tip = (
                self.git("rev-parse", "--verify", locator.association.ref)
                .decode()
                .strip()
            )
            if (
                current != retained.graph.commit
                or checkpoint_tip != locator.commit
                or not _lease_free(self.root, operation.operation_id)
                or locator.association.association_id != operation.association_id
                or locator.association.vault_anchor != verify_directory(self.root)
                or locator.association.git_anchor
                != verify_directory(self.root / ".git")
            ):
                raise OSError("Recovery authority or converter lease changed")
            self.validated_active_operation = True
            self.history = retained.checkpoint
            self.operation = "idle"
        elif (gitdir / "brz2obsidian").exists():
            owned = False
            if self.active_operation is not None:
                try:
                    from brz2obsidian.publication.vault_apply import owns_operation

                    owned = owns_operation(self.root, self.active_operation)
                except OSError, ValueError, TypeError:
                    pass
            if owned:
                self.validated_active_operation = True
                from brz2obsidian.publication.vault_history import _Git, _read

                self.history = _read(
                    self.root,
                    _Git(self.root, self.executable),
                    linked_intents=self.linked_intents,
                )
                if self.history.status != "valid":
                    raise OSError("Current converter history unavailable")
                self.operation = "idle"
            else:
                self.finding(
                    "converter_operation",
                    "operation",
                    "Converter operation/history metadata requires validated recovery discovery first.",
                )
                self.operation = "recovery_required"
        elif (self.root / ".brz2obsidian").exists():
            from brz2obsidian.publication.vault_history import _Git, _read

            try:
                self.history = _read(
                    self.root,
                    _Git(self.root, self.executable),
                    linked_intents=self.linked_intents,
                )
                if self.history.status != "valid":
                    raise OSError("Current converter history unavailable")
                _, _, raw, _ = observe_file(
                    self.root,
                    self.root / ".brz2obsidian/locator.json",
                    prefix_limit=OUTPUT_BUDGET + 1,
                )
                from brz2obsidian.application.checkpoint_contracts import (
                    CheckpointLocator,
                )

                if CheckpointLocator.model_validate_json(raw) != self.history.locator:
                    raise OSError("Current locator changed during history discovery")
                self.operation = "idle"
            except OSError, ValueError, TypeError:
                self.finding(
                    "converter_operation",
                    "operation",
                    "Current converter history requires recovery discovery before dependent work.",
                )
                self.operation = "recovery_required"
        index_records = self.git("ls-files", "--stage", "-v", "-z")
        entries = [entry for entry in index_records.split(b"\0") if entry]
        if any(entry[1:2] != b" " or b"\t" not in entry for entry in entries):
            raise OSError("Malformed index observations")
        stages = [entry[2:] for entry in entries]
        self.storage_state.extend(
            (
                index_records.hex(),
                _file_digest(gitdir / "index")
                if (gitdir / "index").exists()
                else "index-absent",
            )
        )
        if any(entry.split(b"\t", 1)[0].split()[-1] != b"0" for entry in stages):
            self.finding(
                "unmerged_index",
                "operation",
                "Finish the existing unmerged Git index before converter work.",
            )
            self.operation = "active"
        if any(entry[:1].islower() or entry[:1] == b"S" for entry in entries):
            self.finding(
                "index_flags",
                "layout",
                "Skip-worktree and assume-unchanged entries are initially unsupported.",
            )
        if any(
            entry.startswith((b"160000 ", b"040000 ", b"120000 ")) for entry in stages
        ):
            self.finding(
                "index_layout",
                "layout",
                "Submodule, sparse-directory and symbolic-link entries are initially unsupported.",
            )
        if self.findings:
            return False
        self.index_stages = tuple(stages)
        self.tracked_paths = {
            entry.split(b"\t", 1)[1].decode("utf-8") for entry in stages
        }
        refs = self.git("for-each-ref", "--format=%(refname) %(objectname)")
        self.storage_state.append(refs.hex())
        if not self.validated_active_operation:
            operation_refs = [
                line
                for line in refs.decode("ascii").splitlines()
                if line.split(" ", 1)[0].startswith("refs/brz2obsidian/imports/")
                and "/operations/" in line.split(" ", 1)[0]
            ]
            if operation_refs or self.linked_intents:
                from brz2obsidian.publication.vault_apply import inspect_update_status

                status = inspect_update_status(self.root)
                if status.status not in (
                    "applied",
                    "no_content_change",
                    "restored",
                    "undone",
                ) or (status.recovery_required):
                    self.finding(
                        "converter_operation",
                        "operation",
                        "Retained operation history needs validated recovery before another update.",
                    )
                    self.operation = "recovery_required"
        with (gitdir / "HEAD").open("rb") as stream:
            head_raw = stream.read(65537)
        if len(head_raw) > 65536:
            raise OSError("HEAD metadata exceeds its safe resource budget")
        self.storage_state.append(head_raw.hex())
        if head_raw.startswith(b"ref: "):
            ref = head_raw[5:].strip().decode("utf-8")
            if not ref.startswith("refs/heads/") or ".." in ref or "\\" in ref:
                raise OSError("Invalid symbolic HEAD")
            mapping = dict(line.split(b" ", 1) for line in refs.splitlines())
            head = mapping.get(ref.encode(), b"unborn").decode("ascii")
        else:
            head = head_raw.strip().decode("ascii").lower()
            if len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
                raise OSError("Invalid detached HEAD")
        result = read_git(
            [
                self.executable,
                "--no-pager",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(self.root),
                "fsck",
                "--full",
                "--no-reflogs",
                "--no-progress",
            ],
            env=self.env,
        )
        if result.returncode:
            self.finding(
                "object_integrity",
                "git",
                "Required local objects/references are missing or corrupt; restore matching complete history.",
            )
            return False
        self.repo = self.repo.model_copy(update={"head": head})
        return self.qualify_options()

    def authored(self):
        tracked = self.tracked_paths
        known = set()
        for directory, names, files in _walk(self.root):
            verify_directory(Path(directory))
            names[:] = sorted(n for n in names if n.casefold() != ".git")
            names[:] = [
                n for n in names if not self.excluded_directory(Path(directory) / n)
            ]
            for name in sorted(files):
                path = Path(directory) / name
                relative = path.relative_to(self.root).as_posix()
                collision = relative.casefold()
                if not _safe_relative(relative) or collision in known:
                    self.finding(
                        "path_collision",
                        "inventory",
                        "Resolve unsafe or case-colliding authored paths.",
                    )
                    return
                known.add(collision)
                before = path.lstat()
                if (
                    _unsafe(path)
                    or not stat.S_ISREG(before.st_mode)
                    or before.st_nlink != 1
                ):
                    self.finding(
                        "unsafe_file",
                        "inventory",
                        "Authored content must use independent ordinary files.",
                        (relative,),
                    )
                    return
                selected = relative in {s.path for s in self.subjects}
                if selected and bool(getattr(before, "st_file_attributes", 0) & 1):
                    self.finding(
                        "write_access",
                        "inventory",
                        "The selected authored path is read-only; make it writable before preparation.",
                        (relative,),
                    )
                    return
                try:
                    after, content, prefix, identity = observe_file(
                        self.root, path, writable=selected
                    )
                    if selected:
                        verify_directory(path.parent, writable=True)
                except PermissionError:
                    self.finding(
                        "write_access" if selected else "read_access",
                        "inventory",
                        "Required access to an authored path is unavailable.",
                        (relative,),
                    )
                    return
                self.prefixes[relative] = prefix
                self.file_observations.add(relative)
                exclusion = (
                    "cache"
                    if any(relative.startswith(p + "/") for p in CACHE_PATHS)
                    else "temporary"
                    if any(relative.startswith(p + "/") for p in TEMP_PATHS)
                    else None
                )
                self.inventory.append(
                    VaultFile(
                        path=relative,
                        mode="100755"
                        if os.name != "nt" and before.st_mode & stat.S_IXUSR
                        else "100644",
                        size=after.st_size,
                        sha256=content,
                        identity=identity,
                        tracked=relative in tracked,
                        excluded=exclusion is not None,
                        exclusion=exclusion,
                    )
                )
        self.inventory.sort(key=lambda f: f.path)
        ignore_paths = sorted(
            {f.path for f in self.inventory}
            | {subject.path for subject in self.subjects}
        )
        ignore_input = "".join(path + "\0" for path in ignore_paths).encode("utf-8")
        ignored_raw = (
            self.git(
                "check-ignore",
                "--no-index",
                "--stdin",
                "-z",
                input=ignore_input,
                allowed=(0, 1),
            )
            if ignore_paths
            else b""
        )
        if ignored_raw and not ignored_raw.endswith(b"\0"):
            raise OSError("Malformed effective exclusion observation")
        ignored = set(ignored_raw.decode("utf-8").split("\0")) - {""}
        if not ignored.issubset(set(ignore_paths)):
            raise OSError("Incomplete effective exclusion observation")
        self.ignored_paths = ignored
        self.policy.append(ignored_raw.hex())
        self.inventory = [
            f.model_copy(update={"excluded": True, "exclusion": "git_ignore"})
            if f.path in ignored and not f.tracked and f.exclusion is None
            else f
            for f in self.inventory
        ]
        self.complete = True
        for subject in self.subjects:
            path = self.root / subject.path
            if path.exists():
                if subject.path not in self.file_observations:
                    self.finding(
                        "unsafe_subject",
                        "inventory",
                        "An existing selected path must match its observed authored-file identity and spelling.",
                        (subject.path,),
                    )
                    return
                continue
            parent = path.parent
            while not parent.exists():
                parent = parent.parent
            try:
                verify_directory(parent, writable=True)
            except OSError:
                self.finding(
                    "write_access",
                    "inventory",
                    "The selected new path requires write access to its existing parent directory.",
                    (subject.path,),
                )
                return
        if (
            shutil.disk_usage(self.root).free
            < 2 * sum(f.size for f in self.inventory if not f.excluded) + 1024 * 1024
        ):
            self.finding(
                "insufficient_space",
                "inventory",
                "Free enough local space for authored checkpoints before preparation.",
            )

    def attributes(self):
        paths = sorted(
            {f.path for f in self.inventory if not f.excluded}
            | {s.path for s in self.subjects}
        )
        attribute_input = "".join(p + "\0" for p in paths).encode("utf-8")
        raw = self.git(
            "check-attr",
            "-z",
            "--all",
            "--stdin",
            input=attribute_input,
        )
        self.policy.append(raw.hex())
        values = raw.decode("utf-8").split("\0")
        if not values or values[-1] or (len(values) - 1) % 3:
            raise OSError("Malformed effective attribute observation")
        relevant = {
            "text",
            "crlf",
            "eol",
            "working-tree-encoding",
            "ident",
            "filter",
            "diff",
            "merge",
        }
        observed = {}
        for i in range(0, len(values) - 1, 3):
            path, attribute, value = values[i : i + 3]
            if path not in paths or (path, attribute) in observed:
                raise OSError("Inconsistent effective attribute observation")
            if attribute in relevant:
                observed[path, attribute] = value
        # --all omits true unspecified markers, so a returned 'unspecified' is
        # already a string. Only the boolean-looking spellings need typed query.
        ambiguous = {
            attribute
            for (_, attribute), value in observed.items()
            if value in ("set", "unset")
        }
        assigned = set()
        if ambiguous:
            directory = self.temporary_base()
            if directory is None:
                return
            attribute_reader = self.resources.enter_context(
                assigned_markers(
                    self.executable,
                    environment=self.view_env or self.env,
                    stages=self.index_stages,
                    paths=paths,
                    attributes=ambiguous,
                    directory=directory,
                    query=self.git,
                )
            )
            assigned = attribute_reader()
            self.capabilities += ("typed-attribute-pathspec",)
        attrs = {
            key: value
            if value not in ("set", "unset") or key in assigned
            else value == "set"
            for key, value in observed.items()
        }
        self.policy.append(
            [
                (path, attribute, value)
                for (path, attribute), value in sorted(attrs.items())
            ]
        )
        builtin = False
        merge_names = {
            key[len("merge.") : key.rfind(".")]
            for key in self.config
            if key.startswith("merge.") and key.count(".") >= 2
        }
        for path in paths:

            def value(attribute, current_path=path):
                return attrs.get((current_path, attribute))

            def newline_action(setting):
                if setting is True:
                    return "text"
                if setting is False:
                    return "binary"
                return setting if setting in ("input", "auto") else None

            action = newline_action(value("text"))
            if action is None:
                action = newline_action(value("crlf"))
            if action != "binary" and value("eol") in ("lf", "crlf"):
                action = "text"
            if (
                action is None
                and self.config.get("core.autocrlf", "false").lower() not in FALSE
            ):
                action = "text"
            encoding = value("working-tree-encoding")
            if isinstance(encoding, bool):
                self.finding(
                    "encoding_policy",
                    "storage",
                    "A boolean encoding attribute is not a usable Git storage policy.",
                    (path,),
                )
            builtin |= (
                action not in (None, "binary")
                or value("ident") is True
                or (
                    isinstance(encoding, str)
                    and bool(encoding)
                    and encoding.replace("-", "").casefold() != "utf8"
                )
            )
            driver = value("filter")
            if isinstance(driver, str):
                self.finding(
                    "lfs" if driver == "lfs" else "custom_filter",
                    "storage",
                    "Applicable custom/LFS storage is unsupported; preserve repository policy.",
                    (path,),
                )
            driver = value("merge")
            if driver is None:
                driver = self.config.get("merge.default")
            if isinstance(driver, str) and driver in merge_names:
                self.finding(
                    "custom_driver",
                    "execution",
                    "An applicable custom merge driver is unsupported.",
                    (path,),
                )
            driver = value("diff")
            if isinstance(driver, str) and any(
                key in self.config
                for key in (f"diff.{driver}.command", f"diff.{driver}.textconv")
            ):
                self.finding(
                    "custom_driver",
                    "execution",
                    "An applicable custom diff/textconv driver is unsupported.",
                    (path,),
                )
        if self.config.get("diff.external") or os.environ.get("GIT_EXTERNAL_DIFF"):
            self.finding(
                "custom_driver",
                "execution",
                "An applicable external diff command is unsupported.",
            )
        # LFS pointers remain managed storage even when attributes were removed.
        for item in self.inventory:
            if (
                not item.excluded
                and item.size <= 1024
                and self.prefixes[item.path].startswith(
                    b"version https://git-lfs.github.com/spec/v1\n"
                )
            ):
                self.finding(
                    "lfs",
                    "storage",
                    "LFS pointer content requires supported managed storage.",
                    (item.path,),
                )
        self.policy.append([(f.path, f.exclusion, f.tracked) for f in self.inventory])
        self.policy.append([(s.path, s.subject_id) for s in self.subjects])
        fingerprint = _digest(
            (str(self.root), self.repo.model_dump(exclude={"head"}), self.policy)
        )

        def consent(kind, policy, selected):
            return ReviewConsentRequirement(
                schema_id="brz2obsidian.review-consent-requirement",
                schema_version=1,
                consent_id="vault:" + kind,
                kind=kind,
                requirement="required",
                policy=policy,
                fingerprint=_digest((fingerprint, kind, sorted(set(selected)))),
                disclosure="Retain exact on-disk bytes under the reviewed storage policy."
                if kind == "storage"
                else "Include the selected excluded authored paths in converter history.",
                subjects=tuple(sorted(set(selected))),
            )

        if builtin:
            self.consents.append(
                consent(
                    "storage",
                    "builtin_transform",
                    [s.subject_id for s in self.subjects],
                )
            )
        excluded = {f.path for f in self.inventory if f.exclusion == "git_ignore"}
        ignored_subjects = self.ignored_paths
        included = {
            s.subject_id
            for s in self.subjects
            if (s.path in excluded or s.path in ignored_subjects)
            and s.path not in {f.path for f in self.inventory if f.tracked}
        }
        if included:
            self.consents.append(consent("tracking", "ordinary", included))

    def temporary_base(self):
        # gettempdir() itself creates probe files. Read Python 3.14's candidate
        # list without probing, then establish actual directory capabilities.
        candidates = (
            [tempfile.tempdir]
            if tempfile.tempdir
            else tempfile._candidate_tempdir_list()
        )
        resolved_root = self.root.resolve(strict=True)
        for candidate in candidates:
            path = Path(candidate)
            if not path.is_dir():
                continue
            base = path.resolve(strict=True)
            if base == resolved_root or resolved_root in base.parents:
                self.finding(
                    "unsafe_temp_location",
                    "inventory",
                    "Select temporary storage outside the inspected vault before preparation.",
                )
                return None
            verify_directory(base, writable=True)
            return base
        self.finding(
            "unsafe_temp_location",
            "inventory",
            "Select an accessible temporary-storage directory outside the vault.",
        )
        return None

    def locator_shape(self):
        directory = self.root / ".brz2obsidian"
        if self.repo.kind != "root" or not directory.is_dir():
            return False
        verify_directory(directory)
        return (
            set(os.listdir(directory)) == {"locator.json"}
            and (directory / "locator.json").is_file()
        )

    def run(self):
        try:
            self.subjects = tuple(
                VaultSubject.model_validate(s) for s in self.request_subjects
            )
        except ValueError, TypeError:
            self.finding(
                "unsafe_subject",
                "inventory",
                "Review subjects require valid unique vault-relative paths and source-facet identities.",
            )
            return self.finish()
        if not self.layout():
            return self.finish()
        if _exists(self.root / ".brz2obsidian") and not self.locator_shape():
            self.finding(
                "converter_operation",
                "operation",
                "Converter metadata requires recovery discovery even when local history is missing.",
            )
            self.operation = "recovery_required"
            return self.finish()
        if not self.executable:
            self.finding(
                "git_unavailable",
                "git",
                "Install Git and restart the converter before preparation.",
            )
            return self.finish()
        try:
            self.version = self.text("--version")
            # The Windows cmd/git.exe is only a launcher. Bind cached option
            # proof to its actual version and the underlying qualified binary.
            launcher = Path(self.executable)
            underlying = launcher.parent.parent / "mingw64" / "bin" / "git.exe"
            if (
                not self.explicit_executable
                and launcher.parent.name.casefold() == "cmd"
                and underlying.is_file()
            ):
                self.option_key = (
                    self.version,
                    _file_digest(launcher),
                    _file_digest(underlying),
                    self.env.get("GIT_EXEC_PATH"),
                    self.env.get("PATH"),
                )
                self.storage_state.append(_digest(self.option_key))
            commands = _COMMAND_NAMES.get(self.option_key) if self.option_key else None
            if commands is None:
                commands = set(self.text("--list-cmds=builtins").splitlines())
            if not CAPABILITIES <= commands:
                self.finding(
                    "git_capability",
                    "git",
                    "Install a Git version providing the required local storage commands.",
                )
                return self.finish()
            self.capabilities = tuple(sorted(CAPABILITIES))
            if self.option_key:
                _COMMAND_NAMES[self.option_key] = commands
        except OSError, subprocess.SubprocessError:
            self.finding(
                "git_unavailable",
                "git",
                "Install a usable Git executable and restart the converter before preparation.",
            )
            return self.finish()
        if self.configuration() and self.repository():
            if self.repo.kind == "none":
                # Git's policy interpreters require an empty repository view.
                # No vault files, objects or index are written into this view.
                temp_base = self.temporary_base()
                if temp_base is None:
                    return self.finish()
                view = self.resources.enter_context(
                    tempfile.TemporaryDirectory(
                        prefix="brz2obsidian-policy-", dir=temp_base
                    )
                )
                path = Path(view)
                (path / "objects").mkdir()
                (path / "refs").mkdir()
                (path / "HEAD").write_bytes(b"ref: refs/heads/inspection\n")
                empty_config = path / "empty-config"
                empty_config.write_bytes(b"")
                self.policy_view = view
                self.view_env = {
                    k: v for k, v in self.env.items() if not k.startswith("GIT_CONFIG_")
                }
                self.view_env.update(
                    {
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": str(empty_config),
                        "GIT_CONFIG_SYSTEM": str(empty_config),
                    }
                )
                self.view_config = tuple(
                    (k, v)
                    for k, v in self.config.items()
                    if k
                    in (
                        "core.attributesfile",
                        "core.excludesfile",
                        "core.ignorecase",
                        "core.symlinks",
                        "core.autocrlf",
                        "core.eol",
                    )
                )
                if self.qualify_options():
                    self.git("ls-files", "--stage", "-z")
                    self.authored()
                    if self.complete:
                        self.attributes()
            else:
                self.authored()
                if self.complete:
                    self.attributes()
        return self.finish()

    def finish(self):
        gaps = tuple(f.path for f in self.inventory if f.exclusion == "git_ignore")
        policy = _digest(
            (str(self.root), self.repo.model_dump(exclude={"head"}), self.policy)
        )
        # A selected missing destination can become a file in the prepared
        # result. Compare the same rule-query domain and selected tracking facts
        # across that transition, while the full observation still accounts for
        # every actual authored path and byte.
        selected_paths = {subject.path for subject in self.subjects}
        selected_policy = []
        for path in sorted(selected_paths):
            tracked = path in self.tracked_paths
            exclusion = (
                "cache"
                if any(path.startswith(prefix + "/") for prefix in CACHE_PATHS)
                else "temporary"
                if any(path.startswith(prefix + "/") for prefix in TEMP_PATHS)
                else "git_ignore"
                if path in self.ignored_paths and not tracked
                else None
            )
            selected_policy.append((path, exclusion, tracked))
        continuous_policy = _digest(
            (
                str(self.root),
                self.repo.model_dump(exclude={"head"}),
                self.policy[:-2],
                [
                    (f.path, f.exclusion, f.tracked)
                    for f in self.inventory
                    if f.path not in selected_paths
                ],
                selected_policy,
                self.policy[-1:],
            )
        )
        fingerprint = _digest(
            (
                policy,
                self.version,
                self.capabilities,
                self.storage_state,
                [f.model_dump() for f in self.inventory],
                [f.model_dump() for f in self.findings],
            )
        )
        recovery = any(f.policy == "operation" for f in self.findings)
        status = (
            "recovery_first"
            if recovery
            else "refused"
            if self.findings
            else "supported"
            if self.complete
            else "unknown"
        )
        actions = (
            ("resolve_operation",)
            if recovery
            else ()
            if status != "supported"
            else ("review_initialization",)
            if self.repo.kind == "none"
            else ("review_history",)
        )
        authority = _digest(
            (
                self.repo.kind,
                self.repo.git_directory,
                self.operation,
                self.history.locator.model_dump(mode="json")
                if self.history is not None and self.history.status == "valid"
                else "history-not-yet-validated",
            )
        )
        preflight = ReviewPreflight(
            schema_id="brz2obsidian.review-preflight",
            schema_version=1,
            operation_status=self.operation,
            state_status="supported"
            if self.history is not None and self.history.status == "valid"
            else "unknown",
            state_schema="brz2obsidian.checkpoint-manifest"
            if self.history is not None and self.history.status == "valid"
            else None,
            state_version=1
            if self.history is not None and self.history.status == "valid"
            else None,
            state_fingerprint=authority,
            consents=tuple(self.consents),
        )
        return VaultAdmission(
            schema_id="brz2obsidian.vault-admission",
            schema_version=1,
            vault=str(self.root),
            status=status,
            repository=self.repo,
            git_executable=self.executable,
            git_version=self.version,
            capabilities=self.capabilities,
            policy_scope="current_repository"
            if self.repo.kind == "root"
            else "before_initialization"
            if self.repo.kind == "none"
            else "unknown",
            policy_fingerprint=policy,
            policy_continuity_fingerprint=continuous_policy,
            observation_fingerprint=fingerprint,
            inventory=tuple(self.inventory),
            inventory_complete=self.complete,
            exclusions=tuple(sorted(self.exclusions)),
            recovery_gaps=gaps,
            findings=tuple(self.findings),
            admitted_actions=actions,
            preflight=preflight,
        )


def _observe_vault(
    vault,
    *,
    subjects=(),
    git_executable=None,
    active_operation=None,
    recovery_observation=None,
):
    """Observe current storage; caller assertions cannot grant trusted proof."""
    inspection = _Inspection(
        vault, subjects, git_executable, active_operation, recovery_observation
    )
    try:
        with inspection.resources:
            return inspection.run(), inspection.history
    except AttributeCapabilityUnavailable:
        inspection.complete = False
        inspection.finding(
            "git_capability",
            "git",
            "Install Git with the required lossless attribute-query capability before preparation.",
        )
        return inspection.finish(), None
    except OSError, UnicodeError, ValueError, subprocess.SubprocessError:
        inspection.complete = False
        inspection.finding(
            "observation_unavailable",
            "inventory",
            "A complete safe observation is unavailable; check access, repository integrity and concurrent changes.",
        )
        return inspection.finish(), None


def inspect_vault(vault, *, subjects=(), git_executable=None, active_operation=None):
    """Fresh admission; internal composition may consume the same validated history."""
    return _observe_vault(
        vault,
        subjects=subjects,
        git_executable=git_executable,
        active_operation=active_operation,
    )[0]


def _inspect_vault_for_recovery(vault, observation, *, subjects=()):
    """Observe policy and bytes beneath one validated, stopped operation graph."""
    return _observe_vault(vault, subjects=subjects, recovery_observation=observation)[0]
