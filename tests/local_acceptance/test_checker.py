import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_minimal_workflow import make_archive
from tests.local_acceptance.checker import check_vault


def test_independent_checker_compares_every_original_payload(tmp_path):
    source = make_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    assert check_vault(source, vault)["payloads"] == 1
    backup = vault / "Attachments/22222222/Notes.md.original"
    backup.write_bytes(b"Corrupted backup")
    with pytest.raises(AssertionError, match="payload bytes"):
        check_vault(source, vault)


def test_checker_preserves_high_precision_json_numbers(tmp_path):
    import json
    from zipfile import ZipFile

    from tests.sources.test_reader import rewrite

    source = make_archive(tmp_path / "source.brz")
    with ZipFile(source) as archive:
        meta = archive.read("meta.json")
    rewrite(
        source, "meta.json", meta.replace(b"1.5", b"0.12345678901234567890123456789")
    )
    vault = tmp_path / "vault"
    default_workflow().convert(source, vault)
    check_vault(source, vault)
    path = vault / "migration-record.json"
    path.write_text(json.dumps(json.loads(path.read_bytes())), encoding="utf-8")
    with pytest.raises(AssertionError, match="original JSON"):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["count", "receipt"])
def test_checker_audits_result_against_real_files_not_claimed_manifest(
    tmp_path, damage
):
    from tests.local_acceptance.checker import check_run_result

    source = make_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    result = (
        default_workflow().convert(source, vault).model_dump(mode="json", by_alias=True)
    )
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)
    if damage == "count":
        result["counts"]["actual_notes"] = 999
    else:
        result["receipt"]["manifest"].pop()
    with pytest.raises(AssertionError):
        check_run_result(result, vault, summary)
