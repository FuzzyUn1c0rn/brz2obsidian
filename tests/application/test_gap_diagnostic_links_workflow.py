"""Canonical diagnostic links through actual public inspection and publication."""

import json
from zipfile import ZipFile

import pytest

from brz2obsidian.application.wiring import default_workflow
from tests.application.test_absent_note_images_workflow import png_bytes
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_verified_coverage import add_attachment, write_source
from tests.local_acceptance.checker import check_vault

BODY = "café source prose\r\n[authored brackets] | pipe\rUnchanged `literal`\n".encode()


def diagnostic_parts(tmp_path, role, title):
    names = {1: "Home", 2: "Card", 3: "Category", 4: "Member"}
    names[2 if role == "ordinary_note" else 3] = title
    if role == "definition_icon":
        names[4] = title
    source = graph_archive(
        tmp_path / "base.brz",
        names,
        [(3, 4, 1, 2, -1)],
        kinds={3: 2},
        notes={1: (BODY, 4), 2: (b"unknown card", 4), 3: (BODY, 4), 4: (BODY, 4)},
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    thoughts[-1]["TypeId"] = identity(3)
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    if role in {"ordinary_note", "definition_note"}:
        owner = 2 if role == "ordinary_note" else 3
        parts.pop(identity(owner) + "/Notes.md")
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"][identity(2000 + owner)] = 3
        parts["meta.json"] = json.dumps(meta).encode()
        if role == "ordinary_note":
            add_attachment(
                parts, identity(3001), 12, "card.png", png_bytes(), owner=identity(2)
            )
    else:
        add_attachment(
            parts, identity(3001), 5, "type.png", declared=7, state=3, owner=identity(3)
        )
    return parts


def test_bracket_title_gap_owner_uses_canonical_alias_without_changing_source(tmp_path):
    source = write_source(
        tmp_path, diagnostic_parts(tmp_path, "ordinary_note", "Card [Example]")
    )
    original = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    owner = next(
        t for t in inspected.inspection.item_targets if t.item_key == identity(2)
    )
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings" and result.receipt.verified
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert (
        f"- [ ] [[{owner.relative_path}|Card Example]]; thought ID {identity(2)};"
        in report
    )
    assert check_vault(source, vault)["source_gaps"] == 1
    assert source.read_bytes() == original


TITLE_ALIASES = [
    ("Plain card", "Plain card"),
    ("Card [Example]", "Card Example"),
    ("Card|Example", "Card Example"),
    ("Card  Example", "Card Example"),
    ("Card\r\nExample", "Card Example"),
    ("  Card Example  ", "Card Example"),
    ("Card\t[Example] | Details", "Card Example Details"),
    (" 雲\u3000[例]\t|\u00a0café ", "雲 例 café"),
]


@pytest.mark.parametrize("title,alias", TITLE_ALIASES)
@pytest.mark.parametrize(
    "role,outcome",
    [
        ("ordinary_note", "image_fallback"),
        ("definition_note", "unknown_note"),
        ("definition_icon", "neutral_icon"),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_gap_report_joins_canonical_owner_provider_and_member_aliases_to_raw_facts(
    tmp_path, title, alias, role, outcome, reverse
):
    parts = diagnostic_parts(tmp_path, role, title)
    if reverse:
        for key in ("thoughts.json", "attachments.json", "links.json"):
            parts[key] = b"\n".join(reversed(parts[key].splitlines()))
        parts = dict(reversed(list(parts.items())))
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    inspected = default_workflow().inspect(source)
    assert inspected.outcome == "warnings", inspected.issues
    assert inspected.receipt is None and inspected.counts.actual_notes is None
    owner_key = identity(2 if role == "ordinary_note" else 3)
    owner = next(
        t for t in inspected.inspection.item_targets if t.item_key == owner_key
    )
    assert owner.original_title == title
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert (
        result.outcome == "warnings"
        and result.receipt.published
        and result.receipt.verified
    )
    record = json.loads((vault / "migration-record.json").read_bytes())
    assert record["source_gaps"] == [
        g.model_dump(mode="json") for g in inspected.inspection.source_gaps
    ]
    diagnostic = record["source_gaps"][0]
    assert diagnostic["gap"]["owner"] == owner_key and diagnostic["gap"]["role"] == role
    assert (
        diagnostic["outcome"] == outcome
        and diagnostic["owner_target"] == owner.relative_path
    )
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    link = f"[[{owner.relative_path}|{alias}]]"
    assert (
        f"- [ ] {link}; thought ID {owner_key}; attachment {diagnostic['gap']['asset_id']}; role {role}; outcome {outcome}."
        in report
    )
    assert (vault / owner.relative_path).is_file()
    assert original == source.read_bytes()
    raw_thoughts = next(
        e["records"] for e in record["original_evidence"] if e["key"] == "thoughts.json"
    )
    assert next(t for t in raw_thoughts if t["Id"] == owner_key)["Name"] == title
    if role == "definition_icon":
        member = next(
            t for t in inspected.inspection.item_targets if t.item_key == identity(4)
        )
        assert member.original_title == title
        assert f"  Provider: {link}." in report
        assert (
            f"  - [[{member.relative_path}|{alias}]]; thought ID {identity(4)}"
            in report
        )
        assert diagnostic["affected_member_keys"] == [identity(4)]
    preserved = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(2004)
    )
    assert (vault / preserved["relative_path"]).read_bytes() == BODY
    member = next(t for t in record["item_targets"] if t["item_key"] == identity(4))
    assert BODY in (vault / member["relative_path"]).read_bytes()
    summary = check_vault(source, vault)
    assert summary["source_gaps"] == 1 and summary["references"] == 0
    assert summary["generated_embeds"] == (1 if role == "ordinary_note" else 0)


@pytest.mark.parametrize("role", ["ordinary_note", "definition_icon"])
def test_json_cli_publishes_canonical_diagnostic_links_and_verified_receipt(
    tmp_path, capsys, role
):
    from brz2obsidian.cli import main

    title = "Card [Example]" if role == "ordinary_note" else "Category"
    parts = diagnostic_parts(tmp_path, role, title)
    if role == "definition_icon":
        thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
        thoughts[-1]["Name"] = " Member [Example] "
        parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    assert main(["inspect", str(source), "--json"]) == 2
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["receipt"] is None and inspected["counts"]["actual_notes"] is None
    vault = tmp_path / "vault"
    assert main(["convert", str(source), str(vault), "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["receipt"]["published"] and result["receipt"]["verified"]
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    key = identity(2 if role == "ordinary_note" else 3)
    target = next(
        t for t in inspected["inspection"]["item_targets"] if t["item_key"] == key
    )
    alias = "Card Example" if role == "ordinary_note" else "Category"
    assert f"[[{target['relative_path']}|{alias}]]; thought ID {key}" in report
    if role == "definition_icon":
        member = next(
            t
            for t in inspected["inspection"]["item_targets"]
            if t["item_key"] == identity(4)
        )
        assert (
            f"[[{member['relative_path']}|Member Example]]; thought ID {identity(4)}"
            in report
        )
    assert check_vault(source, vault)["source_gaps"] == 1
    assert source.read_bytes() == original


def test_uncreated_txt_locator_keeps_plain_escaped_source_title(tmp_path):
    source = graph_archive(
        tmp_path / "base.brz", {1: "Home", 2: " Card  [Example] "}, notes={1: (BODY, 4)}
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    add_attachment(parts, identity(3001), 1, "empty.pdf", b"", owner=identity(2))
    add_attachment(
        parts,
        identity(3002),
        15,
        identity(3001) + ".txt",
        declared=0,
        state=2,
        owner=identity(2),
    )
    source = write_source(tmp_path, parts)
    inspected = default_workflow().inspect(source)
    owner = next(
        t for t in inspected.inspection.item_targets if t.item_key == identity(2)
    )
    assert not owner.created and owner.original_title == " Card  [Example] "
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings" and result.receipt.verified
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert (
        f"- [ ]  Card  \\[Example\\]  (uncreated target: {owner.relative_path}); thought ID {identity(2)}"
        in report
    )
    assert f"[[{owner.relative_path}|" not in report
    assert not (vault / owner.relative_path).exists()
    assert check_vault(source, vault)["zero_txt_gaps"] == 1


def test_neutral_provider_links_preserve_owned_override_and_excluded_member_privacy(
    tmp_path,
):
    source = graph_archive(
        tmp_path / "base.brz",
        {
            1: "Home",
            3: " Provider [Example] ",
            4: " Member  [Example] ",
            5: "Override [Example]",
            6: "Excluded [Example]",
        },
        [(3, 4, 1, 2, -1), (3, 5, 1, 2, -1), (3, 6, 1, 2, -1)],
        kinds={3: 2},
        notes={
            1: (BODY, 4),
            3: (BODY, 4),
            4: (BODY, 4),
            5: (BODY, 4),
            6: (b"private excluded body", 4),
        },
    )
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    thoughts = [json.loads(line) for line in parts["thoughts.json"].splitlines()]
    for thought in thoughts:
        if thought["Id"] in {identity(4), identity(5), identity(6)}:
            thought["TypeId"] = identity(3)
        if thought["Id"] == identity(6):
            thought["ForgottenDateTime"] = "2026-10-01T10:00:00Z"
    parts["thoughts.json"] = b"\n".join(json.dumps(t).encode() for t in thoughts)
    add_attachment(
        parts, identity(3001), 5, "missing.png", declared=7, state=3, owner=identity(3)
    )
    add_attachment(
        parts, identity(3002), 5, "owned.png", png_bytes(), owner=identity(5)
    )
    add_attachment(
        parts, identity(3003), 5, "excluded.png", png_bytes(), owner=identity(6)
    )
    source = write_source(tmp_path, parts)
    original = source.read_bytes()
    inspected = default_workflow().inspect(source)
    gap = inspected.inspection.source_gaps[0]
    assert gap.affected_member_keys == (identity(4),)
    vault = tmp_path / "vault"
    result = default_workflow().convert(source, vault)
    assert result.outcome == "warnings" and result.receipt.verified
    record = json.loads((vault / "migration-record.json").read_bytes())
    targets = {t["item_key"]: t for t in record["item_targets"]}
    report = (vault / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    provider_link = f"[[{targets[identity(3)]['relative_path']}|Provider Example]]"
    member_link = f"[[{targets[identity(4)]['relative_path']}|Member Example]]"
    assert f"  Provider: {provider_link}." in report
    assert f"  - {member_link}; thought ID {identity(4)}" in report
    member_bytes = (vault / targets[identity(4)]["relative_path"]).read_bytes()
    assert (
        f"> The inherited icon is unavailable from {provider_link}; appearance is neutral.".encode()
        in member_bytes
    )
    assert BODY in member_bytes
    override = next(
        a for a in record["asset_targets"] if a["asset_id"] == identity(3002)
    )
    assert (vault / override["relative_path"]).read_bytes() == png_bytes()
    override_note = (vault / targets[identity(5)]["relative_path"]).read_bytes()
    assert (
        b"The inherited icon is unavailable" not in override_note
        and BODY in override_note
    )
    assert identity(6) not in targets and "Excluded" not in report
    assert not any(
        a["asset_id"] in {identity(2006), identity(3003)}
        for a in record["asset_targets"]
    )
    assert check_vault(source, vault)["typed_members"] == 2
    assert source.read_bytes() == original
