"""A fresh CLI process consumes a review saved by the shared BRZ lifecycle."""

import hashlib
import json
import subprocess
import sys

from brz2obsidian.application.operations import Operations
from tests.application.test_update_lifecycle import (
    _changed_archive,
    _finish_incoming,
    _seed,
    case_path,
    git,
)

__all__ = ["case_path"]


def test_fresh_cli_inspects_and_applies_saved_incoming_brz_choices(case_path, tmp_path):
    evidence = {
        "owner": json.loads((case_path / ".fixture-owner.json").read_text()),
        "phase": "seed",
    }

    def record(phase, **values):
        evidence.update(phase=phase, **values)
        (tmp_path / "saved-cli-fixture.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )

    record("seed")
    vault, initial = _seed(case_path)
    incoming = _changed_archive(initial, case_path / "incoming.brz")
    record(
        "prepare",
        vault=str(vault),
        source=str(incoming),
        source_sha256=hashlib.sha256(incoming.read_bytes()).hexdigest(),
    )
    offered = Operations().prepare_update(vault, incoming)
    assert offered.status == "prepared_review" and not offered.ready, offered
    (case_path / "offered-preparation.json").write_text(
        offered.preparation.model_dump_json(), encoding="utf-8"
    )
    prepared = _finish_incoming(offered.preparation)
    assert prepared.review.ready
    expected_decisions = {
        approval.decision_id for approval in prepared.review.approvals
    }
    assert expected_decisions
    saved = Operations().save_update(prepared)
    assert saved.code == "saved" and saved.checkpoint is not None, saved
    proposal = prepared.review.proposal
    record(
        "inspect",
        proposal_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=saved.checkpoint.model_dump(mode="json"),
        decisions=sorted(expected_decisions),
    )
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(vault).parts
    }
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    head = (vault / ".git/HEAD").read_bytes()
    index = vault / ".git/index"
    index_before = index.read_bytes() if index.exists() else None
    record(
        "inspect",
        before_sha256={
            path: hashlib.sha256(raw).hexdigest() for path, raw in before.items()
        },
        refs_sha256=hashlib.sha256(refs).hexdigest(),
        refs_hex=refs.hex(),
        head_hex=head.hex(),
        index_hex=index_before.hex() if index_before is not None else None,
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "brz2obsidian",
            "review",
            "inspect",
            str(vault),
            "--proposal-id",
            proposal.proposal_id,
            "--generation",
            str(proposal.generation),
            "--checkpoint",
            saved.checkpoint.commit,
            "--byte-limit",
            "0",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    record(
        "inspect_returned",
        exit_code=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )

    assert process.returncode == 0, (process.stdout, process.stderr)
    assert process.stderr == ""
    result = json.loads(process.stdout)
    assert result["schema"] == "brz2obsidian.cli-review-result"
    assert result["schema_version"] == 1 and result["command"] == "inspect"
    assert result["status"] == "prepared_review"
    assert result["ready"] is True
    assert result["proposal_id"] == proposal.proposal_id
    assert result["generation"] == proposal.generation
    assert result["checkpoint"]["commit"] == saved.checkpoint.commit
    assert result["changes"] == len(proposal.changes)
    assert result["unresolved"] == result["stale"] == 0
    assert result["source"] == prepared.observed_source.model_dump(mode="json")
    assert result[
        "output_identity"
    ] == prepared.review.facts.incoming_identity.model_dump(mode="json")
    assert result["history_retained"] is True
    assert result["publication"] == "not_started"
    assert {
        row["decision_id"] for row in result["choices"] if row["decision_id"]
    } == expected_decisions
    assert result["choices_next_offset"] is None
    page = result["page"]
    assert page["status"] == "available" and page["total"] == len(proposal.changes)
    assert page["omitted"] is True and page["next_offset"] is None
    assert page["items"]
    assert all(
        row[part] in (None, "")
        for row in page["items"]
        for part in ("original", "current", "incoming", "result")
    )
    assert "preparation" not in result and "loaded" not in result
    assert str(prepared.payload_directory) not in process.stdout
    assert "attachment_alternative_outputs" in result["omissions"]
    assert {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(vault).parts
    } == before
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert (vault / ".git/HEAD").read_bytes() == head
    assert (index.read_bytes() if index.exists() else None) == index_before
    note_path = "Home — Entry thought.md"
    attachment_path = "Attachments/22222222/Notes.md.original"
    assert b"Authored body." in before[note_path]
    expected_note = before[note_path].replace(b"Authored body.", b"Incoming body.")
    assert expected_note != before[note_path]
    record("apply")
    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "brz2obsidian",
            "review",
            "apply",
            str(vault),
            "--proposal-id",
            proposal.proposal_id,
            "--generation",
            str(proposal.generation),
            "--checkpoint",
            saved.checkpoint.commit,
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    record(
        "apply_returned",
        apply_exit=applied.returncode,
        apply_stdout=applied.stdout,
        apply_stderr=applied.stderr,
    )
    assert applied.returncode == 0, (applied.stdout, applied.stderr)
    assert applied.stderr == ""
    outcome = json.loads(applied.stdout)
    assert outcome["schema"] == "brz2obsidian.cli-review-result"
    assert outcome["schema_version"] == 1 and outcome["command"] == "apply"
    assert outcome["status"] == "applied" and outcome["publication"] == "complete"
    assert outcome["proposal_id"] == proposal.proposal_id
    assert outcome["generation"] == proposal.generation
    assert outcome["history_retained"] is True
    operation = outcome["operation"]
    assert operation["status"] == "applied" and operation["kind"] == "apply"
    assert operation["phase"] == "terminal" and operation["history"] == "terminal"
    assert operation["publication"] == "complete"
    assert operation["operation_id"] and operation["receipt_commit"]
    assert (vault / note_path).read_bytes() == expected_note
    assert (vault / attachment_path).read_bytes() == b"Incoming body.\r\n"
    for path, raw in before.items():
        if path not in (
            note_path,
            attachment_path,
            "migration-record.json",
        ) and not path.startswith(".brz2obsidian"):
            assert (vault / path).read_bytes() == raw, path
    assert (vault / ".git/HEAD").read_bytes() == head
    assert (index.read_bytes() if index.exists() else None) == index_before
    current_refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    assert [
        row
        for row in current_refs.splitlines()
        if not row.startswith(b"refs/brz2obsidian/")
    ] == [row for row in refs.splitlines() if not row.startswith(b"refs/brz2obsidian/")]
    operation_ref = (
        saved.checkpoint.association.ref.removesuffix("/checkpoints")
        + "/operations/"
        + operation["operation_id"]
    )
    assert (
        git(vault, "rev-parse", operation_ref).decode().strip()
        == operation["receipt_commit"]
    )
    record("complete")
