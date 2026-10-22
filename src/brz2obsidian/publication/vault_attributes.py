"""Lossless Git attribute queries and bounded ordinary-index qualification."""

import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path

from brz2obsidian.publication.git_read import read_git

EMPTY_BLOB = b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
MARKERS = ("set", "unset", "unspecified")


class AttributeCapabilityUnavailable(OSError):
    """Installed Git did not establish the required typed query capability."""


def index_extensions(raw):
    """Locate actual extensions without letting Git freshen a split index."""
    if len(raw) < 32 or raw[:4] != b"DIRC":
        raise OSError("Malformed Git index header")
    # SHA-256 repositories are rejected by the format gate before index commands.
    if hashlib.sha1(raw[:-20]).digest() == raw[-20:]:
        limit = len(raw) - 20
    elif len(raw) >= 44 and hashlib.sha256(raw[:-32]).digest() == raw[-32:]:
        return None
    else:
        raise OSError("Git index checksum is unavailable")
    version = int.from_bytes(raw[4:8], "big")
    if version not in (2, 3, 4):
        raise OSError("Unqualified Git index version")
    count = int.from_bytes(raw[8:12], "big")
    offset = 12
    for _ in range(count):
        start = offset
        if offset + 62 > limit:
            raise OSError("Malformed Git index entry")
        flags = int.from_bytes(raw[offset + 60 : offset + 62], "big")
        offset += 62
        if flags & 0x4000:
            if version == 2 or offset + 2 > limit:
                raise OSError("Malformed extended Git index entry")
            offset += 2
        if version == 4:
            while offset < limit:
                byte = raw[offset]
                offset += 1
                if not byte & 0x80:
                    break
            else:
                raise OSError("Malformed compressed Git index path")
        end = raw.find(b"\0", offset, limit)
        if end < 0:
            raise OSError("Malformed Git index path")
        if version != 4 and flags & 0xFFF != 0xFFF and end - offset != flags & 0xFFF:
            raise OSError("Malformed Git index path length")
        offset = end + 1
        if version != 4:
            offset += -(offset - start) % 8
        if offset > limit:
            raise OSError("Malformed Git index padding")
    extensions = []
    while offset < limit:
        if offset + 8 > limit:
            raise OSError("Malformed Git index extension")
        name = raw[offset : offset + 4]
        size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        offset += 8 + size
        if offset > limit:
            raise OSError("Malformed Git index extension extent")
        extensions.append(name)
    return tuple(extensions)


@contextmanager
def assigned_markers(
    executable, *, environment, stages, paths, attributes, directory, query
):
    """Resolve marker/string identity with an isolated proof and ordinary index.

    Every write belongs to this ephemeral empty Git directory. Only the later
    original-context read sees actual stage OIDs and attribute fallback. No
    authored payload or object is written to either store.
    """
    pathspec_environment = (
        "GIT_LITERAL_PATHSPECS",
        "GIT_GLOB_PATHSPECS",
        "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    )
    with tempfile.TemporaryDirectory(
        prefix="brz2obsidian-attributes-", dir=directory
    ) as name:
        owned = Path(name)
        gitdir = owned / "git"
        gitdir.mkdir()
        for part in ("objects", "refs", "hooks"):
            (gitdir / part).mkdir()
        (gitdir / "HEAD").write_bytes(b"ref: refs/heads/inspection\n")
        empty = owned / "empty-config"
        empty.write_bytes(b"")
        worktree = owned / "worktree"
        worktree.mkdir()
        index = gitdir / "index"
        env = {
            k: v
            for k, v in environment.items()
            if not k.startswith("GIT_CONFIG_") and k not in pathspec_environment
        }
        env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(empty),
                "GIT_CONFIG_SYSTEM": str(empty),
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_INDEX_VERSION": "2",
            }
        )
        command = [
            executable,
            "--no-pager",
            "--no-replace-objects",
            "--git-dir=" + str(gitdir),
            "--work-tree=" + str(worktree),
            "-C",
            str(worktree),
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.splitIndex=false",
            "-c",
            "core.attributesFile=" + str(empty),
            "-c",
            "core.hooksPath=" + str(gitdir / "hooks"),
        ]

        def owned_read(*args, input=None):
            result = read_git([*command, *args], env=env, input=input)
            if result.returncode or result.stderr:
                raise OSError("Typed attribute observation capability is unavailable")
            return result.stdout

        def build(entries):
            records = b"".join(entry + b"\0" for _, entry in sorted(entries.items()))
            owned_read(
                "update-index", "--info-only", "-z", "--index-info", input=records
            )

        proof_paths = set()
        proof_rules = []
        for attribute in sorted(attributes):
            for value in (*MARKERS, "true", "false", "reset"):
                path = "brz2obsidian-proof-" + attribute + "-" + value
                proof_paths.add(path)
                setting = (
                    attribute + "=" + value
                    if value in MARKERS
                    else {
                        "true": attribute,
                        "false": "-" + attribute,
                        "reset": "!" + attribute,
                    }[value]
                )
                proof_rules.append(path + " " + setting + "\n")
        (worktree / ".gitattributes").write_text("".join(proof_rules), encoding="utf-8")
        build(
            {
                path.encode(): b"100644 " + EMPTY_BLOB + b" 0\t" + path.encode()
                for path in proof_paths
            }
        )
        proof_specs = [
            f":(top,glob,attr:{attribute}={value})**"
            for attribute in sorted(attributes)
            for value in MARKERS
        ]
        proof = owned_read("ls-files", "--cached", "-z", "--", *proof_specs)
        expected = {
            "brz2obsidian-proof-" + attribute + "-" + value
            for attribute in attributes
            for value in MARKERS
        }
        if set(proof.decode("utf-8").split("\0")) - {""} != expected:
            raise AttributeCapabilityUnavailable(
                "Git cannot establish lossless typed attribute matching"
            )
        # Reconstruct a separate ordinary domain only after isolated proof. This
        # never asks the empty proof store to load real indexed attribute blobs.
        index.unlink()
        entries = {entry.split(b"\t", 1)[1]: entry for entry in stages}
        for path in paths:
            value = path.encode("utf-8")
            entries.setdefault(value, b"100644 " + EMPTY_BLOB + b" 0\t" + value)
        build(entries)
        query_env = dict(environment)
        for key in pathspec_environment:
            query_env.pop(key, None)
        query_env["GIT_INDEX_FILE"] = str(index)
        domain = (
            query("ls-files", "--cached", "-z", environment=query_env)
            .decode("utf-8")
            .split("\0")
        )
        if set(domain) - {""} != {path.decode("utf-8") for path in entries}:
            raise OSError("Typed attribute observation domain is incomplete")

        def current():
            assigned = set()
            for attribute in sorted(attributes):
                specs = [f":(top,glob,attr:{attribute}={value})**" for value in MARKERS]
                raw = query(
                    "ls-files",
                    "--cached",
                    "-z",
                    "--",
                    *specs,
                    environment=query_env,
                )
                assigned.update(
                    (path, attribute)
                    for path in raw.decode("utf-8").split("\0")
                    if path in paths
                )
            return assigned

        yield current
