"""Combined features cross the real Workflow and CLI with authored expectations."""

import json
from hashlib import sha256

import pytest

from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.cli import main
from tests.application.test_forgotten_workflow import rewrite
from tests.application.test_graph_workflow import identity
from tests.local_acceptance.checker import check_run_result, check_vault, compare_vaults
from tests.local_acceptance.run import reordered_archive
from tests.support.combined_collection import SECOND_TEXT, combined_archive
from tests.support.notes import note_body

HOME_BODY = (
    "# Opening\n\nα \\<Enter> / \\<type>\r\n"
    '[[Notes/First.md|\\<Value>]] ![\\<Alt>](Attachments/00000000000000000000000000000001/picture.png "Caption")\r'
    "`<Code> </Enter>` \\<Escaped> <https://example.invalid>\n"
    "```md\n<Enter></Enter> ![fake](.data/md-images/missing.png)\n```\n\n\n"
    "## Resources\n\n"
    "- [[Attachments/00000000000000000000000000000001/manual.bin|manual.bin]]\n"
    "- [C:\\\\unavailable\\\\directory](<file:///C:/unavailable/directory>)\n\n"
    "## Children\n\n- [[Categories/Concept.md|Concept]]\n\n"
    "## Related\n\n- [[Notes/Different marker.md|Different marker]]\n\n"
    "## Categories\n\n[[Categories.md|Browse categories]]\n"
).encode()


def test_combined_complete_bytes_identity_counts_privacy_and_safe_originals(tmp_path):
    source = combined_archive(tmp_path / "source.brz")
    before = source.read_bytes()
    operation = default_workflow()
    inspected = operation.inspect(source)
    assert inspected.receipt is None and inspected.outcome == "warnings"
    assert list(tmp_path.iterdir()) == [source]
    vault = tmp_path / "vault"
    result = operation.convert(source, vault)
    assert (
        result.issues == inspected.issues
        and result.source_identity == inspected.source_identity
    )
    assert note_body((vault / "Home — Opening.md").read_bytes()) == HOME_BODY
    assert (
        vault / "Attachments/00000000000000000000000000000009/Notes.md.original"
    ).read_bytes() == SECOND_TEXT.encode()
    assert not (
        vault / "Attachments/00000000000000000000000000000001/Notes.md.original"
    ).exists()
    external_only = note_body((vault / "Notes/First.md").read_bytes())
    assert (
        external_only
        == b"# First\n\n\n\n## Resources\n\n- [manual.pdf](<file:///C:/training/only.pdf>)\n\n## Children\n\n- [[Notes/Middle.md|Middle]]\n"
    )
    resources = note_body((vault / "Notes/Different marker.md").read_bytes())
    assert resources.count(b"|manual.pdf]]") == 1
    assert resources.count(b"- [manual.pdf](<file:///") == 2
    assert b"file:///C:/combined/directory" in resources
    assert (
        result.counts.actual_notes,
        result.counts.actual_assets,
        result.counts.actual_references,
        result.counts.text_adaptations,
        result.counts.image_presentation_normalizations,
        result.counts.source_gaps,
        result.counts.actual_generated_embeds,
    ) == (8, 12, 4, 7, 2, 3, 2)
    assert all(
        identity(12).encode() not in p.read_bytes()
        and b"private secret" not in p.read_bytes()
        for p in vault.rglob("*")
        if p.is_file()
    )
    check_run_result(result.model_dump(mode="json"), vault, check_vault(source, vault))
    assert source.read_bytes() == before


def test_combined_zip_root_reordering_preserves_complete_logical_output(tmp_path):
    source = combined_archive(tmp_path / "source.brz")
    shuffled = tmp_path / "shuffled.brz"
    reordered_archive(source, shuffled)
    operation = default_workflow()
    first, second = tmp_path / "first", tmp_path / "second"
    assert operation.convert(source, first).outcome == "warnings"
    assert operation.convert(shuffled, second).outcome == "warnings"
    assert check_vault(source, first) == check_vault(shuffled, second)
    compare_vaults(first, second)


@pytest.mark.parametrize(
    "command,json_mode",
    [("inspect", False), ("inspect", True), ("convert", False), ("convert", True)],
)
def test_combined_cli_matches_library_diagnostics_schema_and_actual_inventory(
    tmp_path, capsys, command, json_mode
):
    source = combined_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    argv = (
        [command, str(source)]
        + ([str(vault)] if command == "convert" else [])
        + (["--json"] if json_mode else [])
    )
    inspected = default_workflow().inspect(source)
    assert main(argv) == 2
    captured = capsys.readouterr()
    assert not captured.err
    if json_mode:
        result = json.loads(captured.out)
        assert result["schema_version"] == 6 and result["operation"] == command
        assert result["issues"] == [i.model_dump(mode="json") for i in inspected.issues]
        assert result["source_identity"] == inspected.source_identity.model_dump(
            mode="json"
        )
        if command == "convert":
            check_run_result(result, vault, check_vault(source, vault))
        else:
            assert result["receipt"] is None and not vault.exists()
            assert result["counts"] == inspected.counts.model_dump(mode="json")
    else:
        assert all(
            i.code in captured.out and i.guidance in captured.out
            for i in inspected.issues
        )
        assert "#$width=75p$" in captured.out and "#$width=90p$" in captured.out
    assert "Set Home" not in captured.out


def test_conversion_revalidates_changed_combined_source_after_successful_inspect(
    tmp_path,
):
    source = combined_archive(tmp_path / "source.brz")
    operation = default_workflow()
    assert operation.inspect(source).outcome == "warnings"

    def change(parts):
        parts[identity(1) + "/Notes.md"] = b"<script>unsupported</script>"
        rows = [json.loads(line) for line in parts["attachments.json"].splitlines()]
        for row in rows:
            if row["SourceId"] == identity(1) and row["Location"] == "Notes.md":
                row["DataLength"] = len(parts[identity(1) + "/Notes.md"])
        parts["attachments.json"] = b"\n".join(json.dumps(r).encode() for r in rows)

    rewrite(source, change)
    before = source.read_bytes()
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "refused" and result.receipt is None
    assert result.issues[0].code == "unsupported_feature"
    assert identity(1) in result.issues[0].affected and result.issues[0].evidence
    assert not (tmp_path / "vault").exists() and source.read_bytes() == before


def test_alternative_source_composes_opaque_text_presentation_and_external_file_facts(
    tmp_path,
):
    from tests.application.test_alternate_source import workflow
    from tests.application.test_sized_images_workflow import images
    from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
    from tests.support.paired_sources import paired_sources

    _, source = paired_sources(tmp_path)
    data = json.loads(source.read_bytes())
    doc = data["documents"][0]
    original_body = (source.parent / "payload-101").read_bytes().decode()
    original, adapted = "α KEY " + original_body, "α changed " + original_body
    (source.parent / "payload-101").write_bytes(original.encode())
    (source.parent / "payload-103").write_bytes(images()[0])
    doc["text"] = adapted
    doc["text_adaptations"] = [
        {
            "start": 2,
            "end": 5,
            "before": "KEY",
            "after": "changed",
            "adapted_start": 2,
            "adapted_end": 9,
            "source_digest": sha256(original.encode()).hexdigest(),
        }
    ]
    for reference in doc["references"]:
        for field in ("start", "end", "destination_start", "destination_end"):
            if field in reference:
                reference[field] += len("α changed ")
    image = doc["references"][1]
    image["presentation_normalization"] = {
        "declaration": "folio:map",
        "start": image["destination_start"],
        "end": image["destination_end"],
        "document_digest": sha256(adapted.encode()).hexdigest(),
    }
    external = next(a for a in data["assets"] if a["key"] == "asset:105:reference-web")
    external.update(
        role="file",
        owner="orphan:alone",
        uri="file:///C:/unavailable/file.pdf",
        name="file.pdf",
        label="file.pdf",
    )
    source.write_text(json.dumps(data), encoding="utf-8")
    operation = workflow(FolioSourceModule(), FOLIO_POLICY)
    inspected = operation.inspect(source)
    result = operation.convert(source, tmp_path / "vault")
    assert result.outcome == "warnings" and result.issues == inspected.issues
    assert (
        result.counts.text_adaptations,
        result.counts.image_presentation_normalizations,
    ) == (1, 1)
    body = note_body((tmp_path / "vault/Home — Opening.md").read_bytes())
    assert (
        b"changed Welcome [[Notes/Empty.md|Empty]].\r\n![Map](Attachments/00000001/map.png)\r\n"
        in body
    )
    assert (
        tmp_path / "vault/Attachments/00000001/Notes.md.original"
    ).read_bytes() == original.encode()
    assert (
        b"[file.pdf](<file:///C:/unavailable/file.pdf>)"
        in (tmp_path / "vault/Notes/Alone.md").read_bytes()
    )
