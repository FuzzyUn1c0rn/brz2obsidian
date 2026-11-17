"""An existing external image must not obstruct an unchanged imported image."""

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from tests.application.test_module_seams import METADATA
from tests.application.test_onboarding import owned_case
from tests.application.test_onboarding_completion import authored_files
from tests.application.test_update_lifecycle import _user_state, git
from tests.application.test_verified_coverage import (
    OWNER,
    add_attachment,
    change_record,
    source_parts,
    write_source,
)


def test_onboarding_preserves_external_windows_image_beside_managed_image():
    tmp_path = owned_case()
    parts = source_parts(tmp_path)
    body = (
        b"Existing ![](C:\\Imported\\image.webp#$width=65p$)\r\n"
        b"Managed ![](.data/md-images/image.webp)\r\n"
    )
    parts[OWNER + "/Notes.md"] = body
    change_record(parts, "33333333-3333-4333-8333-333333333333", DataLength=len(body))
    payload = b"RIFF\x00independently known image bytes"
    add_attachment(
        parts, "66666666-6666-4666-8666-666666666666", 12, "image.webp", payload
    )
    archive = write_source(tmp_path, parts)
    source_before = archive.read_bytes()
    workflow = default_workflow()
    workflow.metadata_factory = lambda: METADATA
    vault = tmp_path / "vault"
    converted = workflow.convert(archive, vault)
    assert converted.receipt is not None and converted.receipt.verified, converted
    note = vault / "Home — Entry thought.md"
    original_note = note.read_bytes()
    assert b"![](C:\\Imported\\image.webp#$width=65p$)" in original_note
    assert b"image.webp)" in original_note
    current_note = original_note + b"\r\nIndependent local writing.\r\n"
    note.write_bytes(current_note)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Manual.md").write_bytes(b"Personal writing.\r\n")
    (vault / "Attachments/manual.bin").write_bytes(b"\x00Personal binary.\r\n")
    git(vault, "add", "Manual.md")
    git(vault, "commit", "-qm", "Independent history")
    before, user_before = authored_files(vault), _user_state(vault)

    result = Operations(workflow=workflow).prepare_onboarding(
        vault, archive, original_source=archive
    )
    assert result.preparation is not None, result
    review = result.preparation.review
    assert review.ready, [
        (c.path, c.disposition, c.provenance.rule) for c in review.proposal.changes
    ]
    managed = next(s for s in review.facts.subjects if s.path.endswith("/image.webp"))
    assert managed.baseline.content.data == payload
    assert managed.current.content.data == payload
    assert managed.incoming.data == payload
    unchanged = next(c for c in review.proposal.changes if c.path == managed.path)
    assert unchanged.disposition == "no_change" and unchanged.result.data == payload
    assert not review.requirements
    document = next(
        d
        for d in review.facts.link_context.current_documents
        if d.source_path == note.name
    )
    assert document.status == "supported"
    external, internal = document.occurrences[:2]
    assert external.query is None and external.meaning.status == "external"
    assert internal.meaning.status == "resolved"
    assert internal.meaning.path == managed.path
    assert (
        next(c for c in review.proposal.changes if c.path == note.name).result.data
        == current_note
    )
    assert authored_files(vault) == before and _user_state(vault) == user_before
    assert archive.read_bytes() == source_before
