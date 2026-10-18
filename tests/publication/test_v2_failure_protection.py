"""Actual OS/staging/stream controls reach new v2 artifact families."""

from tests.support.v2_collection import inventory

SUPPORT_TARGETS = (
    "Templates/New note.md",
    "Templates/Concept.md",
    "Templates/Bases/Members.base",
    ".obsidian/templates.json",
    ".obsidian/types.json",
    "Vault guide.md",
)


def staged_relative(path):
    for parent in path.parents:
        if parent.name.startswith(".brz2obsidian-"):
            return path.relative_to(parent).as_posix()
    return None


def caller_files(tmp_path):
    caller = tmp_path / "caller"
    (caller / "nested").mkdir(parents=True)
    (caller / "sentinel.bin").write_bytes(b"caller owned\x00\xff")
    (caller / "nested/keep.md").write_bytes(b"caller Markdown\r\n")
    return caller, inventory(caller)


def failed_safely(tmp_path, caller, before, error, code):
    assert error.value.issues[0].code == code
    assert not (tmp_path / "vault").exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []
    assert inventory(caller) == before
