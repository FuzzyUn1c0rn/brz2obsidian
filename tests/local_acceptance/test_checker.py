import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_minimal_workflow import make_archive
from tests.local_acceptance.checker import check_vault


def test_independent_checker_derives_required_categories_and_empty_members(tmp_path):
    from tests.application.test_categories_workflow import typed_archive

    source = typed_archive(tmp_path / "typed.brz")
    vault = tmp_path / "vault"
    default_workflow().convert(source, vault)
    summary = check_vault(source, vault)
    assert summary["notes"] == 3
    assert summary["category_notes"] == 1
    assert summary["typed_members"] == 1
    assert summary["membership_sizes"] == [1]


def test_independent_checker_conserves_complete_mixed_v2_source(tmp_path):
    from tests.local_acceptance.checker import check_run_result
    from tests.support.v2_collection import mixed_archive

    source = mixed_archive(tmp_path / "mixed.brz")
    vault = tmp_path / "vault"
    result = (
        default_workflow().convert(source, vault).model_dump(mode="json", by_alias=True)
    )
    summary = check_vault(source, vault)
    check_run_result(result, vault, summary)
    assert (
        summary["notes"],
        summary["payloads"],
        summary["backups"],
        summary["references"],
        summary["warnings"],
        summary["videos"],
    ) == (7, 8, 3, 2, 1, 1)


def test_independent_checker_compares_every_original_payload(tmp_path):
    source = make_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    assert check_vault(source, vault)["payloads"] == 1
    backup = vault / "Attachments/22222222/Notes.md.original"
    backup.write_bytes(b"Corrupted backup")
    with pytest.raises(AssertionError, match="payload bytes"):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["omitted", "date", "number"])
def test_independent_checker_detects_lost_original_metadata(tmp_path, damage):
    import json

    source = make_archive(tmp_path / "source.brz")
    vault = tmp_path / "vault"
    default_workflow().convert(source, vault)
    path = vault / "migration-record.json"
    record = json.loads(path.read_bytes())
    originals = {e["key"]: e for e in record["original_evidence"]}
    if damage == "omitted":
        originals["thoughts.json"]["records"][0]["WasOmitted"] = None
    elif damage == "date":
        originals["thoughts.json"]["records"][0]["CreationDateTime"] += "Z"
    else:
        originals["meta.json"]["records"][0]["Uninterpreted"]["number"] = 2.5
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(AssertionError, match="original JSON"):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["body", "home", "target", "graph", "tag"])
def test_independent_checker_detects_wrong_note_graph_and_native_tags(tmp_path, damage):
    import json

    from tests.application.test_graph_workflow import graph_archive

    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Entry", 2: "Parent", 3: "Child", 4: "Category!"},
        [(2, 3, 1, 1, -1), (4, 1, 1, 5, -1)],
        kinds={4: 4},
        notes={1: (b"Body.\r\n", 4)},
    )
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    check_vault(source, vault)
    if damage in {"body", "tag"}:
        path = vault / "Home — Entry.md"
        text = path.read_bytes().decode()
        text = (
            text.replace("Body.", "Changed.")
            if damage == "body"
            else text.replace("Category", "Wrong")
        )
        path.write_bytes(text.encode())
    elif damage == "graph":
        path = vault / "Notes/Parent.md"
        path.write_bytes(
            path.read_bytes().replace(b"Notes/Child.md", b"Notes/Wrong.md")
        )
    else:
        path = vault / (
            "migration-record.json" if damage == "target" else ".obsidian/app.json"
        )
        data = json.loads(path.read_bytes())
        if damage == "target":
            data["item_targets"][0]["original_identity"] = "unrelated"
        else:
            data["openBehavior"] = "file:Notes/Child.md"
        path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["link", "resource", "span"])
def test_checker_audits_actual_links_and_resource_presentation(tmp_path, damage):
    import json

    from tests.application.test_links_workflow import COMPACT, links_archive

    source = links_archive(
        tmp_path / "source.brz",
        "[Topic](brain://"
        + COMPACT
        + "/name)\r\n![photo](.data/md-images/photo.png)\n",
        resources=[
            ({"Type": 12, "Location": "photo.png"}, b"image"),
            ({"Type": 1, "Location": "data.bin"}, b"generic"),
        ],
    )
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "clean"
    check_vault(source, vault)
    if damage == "span":
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        record["item_targets"][1]["documents"][0]["references"][0]["start"] = 1
        path.write_text(json.dumps(record), encoding="utf-8")
    else:
        path = vault / "Home — Entry thought.md"
        data = path.read_bytes()
        data = (
            data.replace(b"Topic.v2.md", b"Wrong.md")
            if damage == "link"
            else data.replace(b"data.bin", b"missing.bin")
        )
        path.write_bytes(data)
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["warning", "accounting", "listing", "extra_file"])
def test_checker_proves_gap_predicate_accounting_and_conditional_support(
    tmp_path, damage
):
    import json

    from tests.application.test_verified_coverage import absent_parts, write_source

    source = write_source(tmp_path, absent_parts(tmp_path))
    vault = tmp_path / "vault"
    assert default_workflow().convert(source, vault).outcome == "warnings"
    check_vault(source, vault)
    if damage in {"warning", "accounting"}:
        path = vault / "migration-record.json"
        record = json.loads(path.read_bytes())
        if damage == "warning":
            next(a for a in record["asset_targets"] if a["source_findings"])[
                "source_findings"
            ][0]["observed_json"] = '{"state":1}'
        else:
            record["source_accounting"]["entries"].pop()
        path.write_text(json.dumps(record), encoding="utf-8")
    elif damage == "listing":
        (vault / "Tag memberships.md").write_text("Invented listing", encoding="utf-8")
    else:
        (vault / "extra.bin").write_bytes(b"unaccounted")
    with pytest.raises(AssertionError):
        check_vault(source, vault)


@pytest.mark.parametrize("damage", ["body", "record", "bookmark"])
def test_repeat_comparison_allows_only_provenance_and_run_clock_differences(
    tmp_path, damage
):
    import json

    from tests.local_acceptance.checker import compare_vaults
    from tests.local_acceptance.run import reordered_archive

    source = make_archive(tmp_path / "source.brz")
    other = tmp_path / "reordered.brz"
    reordered_archive(source, other)
    first, second = tmp_path / "first", tmp_path / "second"
    default_workflow().convert(source, first)
    default_workflow().convert(other, second)
    assert check_vault(source, first) == check_vault(other, second)
    compare_vaults(first, second)
    if damage == "body":
        (second / "Home — Entry thought.md").write_bytes(b"wrong")
    else:
        path = second / (
            "migration-record.json"
            if damage == "record"
            else ".obsidian/bookmarks.json"
        )
        value = json.loads(path.read_bytes())
        if damage == "record":
            value["item_targets"][0]["created"] = False
        else:
            value["items"][0]["path"] = "Wrong.md"
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(AssertionError):
        compare_vaults(first, second)


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
