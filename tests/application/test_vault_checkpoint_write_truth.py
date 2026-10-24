"""Public failed-write outcomes against actual owned Git objects."""

import hashlib
import shutil
import subprocess
import sys

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.core import prepare_review, resolve_review
from tests.application.test_vault_checkpoints import capture, fixture_case, git, inspect
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def _fault_git(vault, *, kind, step, after):
    """Run real Git, failing one selected object write before or after it occurs."""
    marker = vault.parent / "write-count"
    marker.write_text("0", encoding="ascii")
    attempted = vault.parent / "attempted-object"
    script = vault.parent / "fault-git.py"
    script.write_text(
        "import pathlib, subprocess, sys\n"
        + "git = "
        + repr(shutil.which("git"))
        + "\n"
        + "marker = pathlib.Path("
        + repr(str(marker))
        + ")\n"
        + "attempted = pathlib.Path("
        + repr(str(attempted))
        + ")\n"
        + "args = sys.argv[1:]\n"
        + "data = sys.stdin.buffer.read()\n"
        + "target = 'hash-object' in args and '-w' in args and "
        + ("'--stdin' in args" if kind == "metadata" else "'--stdin-paths' in args")
        + "\n"
        + "if target:\n"
        + "    count = int(marker.read_text(encoding='ascii')) + 1\n"
        + "    marker.write_text(str(count), encoding='ascii')\n"
        + "    if count == "
        + str(step)
        + ":\n"
        + (
            "        attempted.write_bytes(data)\n"
            if kind == "metadata"
            else "        attempted.write_bytes(pathlib.Path(data.decode().strip().strip('\\\"')).read_bytes())\n"
        )
        + ("        sys.exit(17)\n" if not after else "")
        + "done = subprocess.run([git, *args], input=data, capture_output=True)\n"
        + "sys.stdout.buffer.write(done.stdout)\n"
        + "sys.stderr.buffer.write(done.stderr)\n"
        + "if target and count == "
        + str(step)
        + ": sys.exit(17)\n"
        + "sys.exit(done.returncode)\n",
        encoding="utf-8",
    )
    wrapper = vault.parent / "fault-git.cmd"
    wrapper.write_text(
        '@echo off\r\nsetlocal\r\nset "is_hash="\r\nset "is_write="\r\nset "is_input="\r\n'
        ':scan\r\nif "%~1"=="" goto dispatch\r\n'
        'if "%~1"=="hash-object" set "is_hash=1"\r\n'
        'if "%~1"=="-w" set "is_write=1"\r\n'
        'if "%~1"=="'
        + ("--stdin" if kind == "metadata" else "--stdin-paths")
        + '" set "is_input=1"\r\n'
        "shift\r\ngoto scan\r\n:dispatch\r\n"
        "if defined is_hash if defined is_write if defined is_input goto fault\r\n"
        '"' + shutil.which("git") + '" %*\r\nexit /b %errorlevel%\r\n'
        ':fault\r\n"'
        + sys.executable
        + '" "'
        + str(script)
        + '" %*\r\nexit /b %errorlevel%\r\n',
        encoding="utf-8",
    )
    return wrapper, marker, attempted


def _actual_blob_exists(vault, payload):
    oid = hashlib.sha1(
        b"blob " + str(len(payload)).encode() + b"\0" + payload, usedforsecurity=False
    ).hexdigest()
    probe = subprocess.run(
        ["git", "-C", str(vault), "cat-file", "-t", oid],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0 and probe.stdout == b"blob\n"


@pytest.mark.parametrize("after", (False, True))
def test_empty_roles_metadata_write_failure_reports_actual_object_truth(after):
    vault, source = fixture_case()
    git(vault, "init", "-q")
    wrapper, marker, attempted = _fault_git(vault, kind="metadata", step=1, after=after)
    operations = Operations()
    observed = inspect(operations, vault, git_executable=wrapper)
    assert observed.status == "supported"
    marker.write_text("0", encoding="ascii")
    result = capture(
        operations,
        vault,
        source,
        vault_id="empty-vault",
        import_id="empty-import",
        identity={
            "collection_id": "empty-collection",
            "module_id": "fixture",
            "module_version": "1",
            "profile_id": "profile",
            "profile_version": "1",
            "output_format": 7,
            "settings_digest": "literal-settings",
        },
        admission=observed,
        git_executable=wrapper,
    )
    assert result.status == "failed" and result.code == "capture_unavailable"
    assert marker.read_text(encoding="ascii") == "1"
    assert result.objects_written is after
    assert result.object_storage == ("verified" if after else "possible")
    assert _actual_blob_exists(vault, attempted.read_bytes()) is after
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    assert not (vault / ".brz2obsidian").exists()


@pytest.mark.parametrize("after", (False, True))
def test_empty_roles_historical_review_write_failure_reports_actual_object_truth(after):
    # The actual S1 memory contains bytes even though this operation has no
    # current source/vault/proposed/preimage payloads to store.
    original = with_review_links(
        request(original=b"baseline-only", current=b"authored", incoming=b"source-next")
    )
    first = prepare_review(original, preflight=preflight())
    accepted = resolve_review(first, action(first, choice="current"))
    assert accepted.status == "accepted" and accepted.plan.ready
    memory = accepted.plan.approvals[0].source_memory
    facts = original.model_copy(
        update={
            "subjects": (),
            "identity_inventory": (),
            "link_context": None,
            "source_version_memory": (memory,),
        }
    )
    review = prepare_review(facts, preflight=preflight())
    assert review.ready
    vault, source = fixture_case()
    git(vault, "init", "-q")
    wrapper, marker, attempted = _fault_git(vault, kind="review", step=3, after=after)
    operations = Operations()
    observed = inspect(operations, vault, git_executable=wrapper)
    assert observed.status == "supported"
    marker.write_text("0", encoding="ascii")
    result = capture(
        operations,
        vault,
        source,
        vault_id="historical-vault",
        import_id="historical-import",
        identity=facts.incoming_identity,
        admission=observed,
        review=review,
        git_executable=wrapper,
    )
    assert result.status == "failed" and result.code == "capture_unavailable"
    assert marker.read_text(encoding="ascii") == "3"
    assert result.objects_written is True  # The first review-content blob was verified.
    assert result.object_storage == ("verified" if after else "possible")
    assert _actual_blob_exists(vault, attempted.read_bytes()) is after
    assert git(vault, "for-each-ref", "refs/brz2obsidian/imports") == b""
    assert not (vault / ".brz2obsidian").exists()
