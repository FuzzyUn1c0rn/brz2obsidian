"""Full finite checking and native lookup bounds in editable vaults."""

import json

import pytest
import yaml

from brz2obsidian.application.checking import check_vault as check_application
from brz2obsidian.cli import main
from brz2obsidian.vault_check import check_vault
from tests.support.local_api_payloads import PNG


def write_note(vault, path, *, provider=None, categories=(), icon=None, role=False):
    target = vault / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\n"
        + yaml.safe_dump(
            {
                "categories": list(categories),
                "appearance_category": provider,
                "icon": icon,
                "tags": ["categories"] if role else [],
            },
            sort_keys=False,
        )
        + "---\n# Editable\n",
        encoding="utf-8",
    )


def chain_vault(vault):
    (vault / "Attachments").mkdir(parents=True)
    (vault / "Attachments/owned.png").write_bytes(PNG)
    for i in range(10):
        provider = f"[[Categories/H{i - 1}.md]]" if i else None
        write_note(
            vault,
            f"Categories/H{i}.md",
            provider=provider,
            categories=(provider,) if provider else (),
            icon="[[Attachments/owned.png]]" if i == 0 else None,
            role=True,
        )
    for name, provider in (
        ("N8", "[[Categories/H7.md]]"),
        ("N9", "[[Categories/H8.md]]"),
    ):
        write_note(vault, f"Notes/{name}.md", provider=provider, categories=(provider,))


def test_eight_link_success_nine_link_warning_is_readable_and_nonblocking(
    tmp_path, capsys
):
    chain_vault(tmp_path)
    before = {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    result = check_vault(tmp_path)
    assert result.outcome == "issues"
    assert {(i.code, i.artifact) for i in result.issues} == {
        ("icon_lookup_depth", "Categories/H9.md"),
        ("icon_lookup_depth", "Notes/N9.md"),
    }
    note = next(i for i in result.issues if i.artifact == "Notes/N9.md")
    assert note.message == "Icon lookup exceeds 8 links."
    assert "Categories/H0.md" in note.reference and "Notes/N9.md" in note.reference
    projected = check_application(tmp_path)
    assert projected.outcome == "issues" and not projected.field_errors
    assert all(
        f.severity == "warning" and f.code == "icon_lookup_depth"
        for f in projected.findings
    )
    assert main(["check-vault", str(tmp_path), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["outcome"] == "issues"
    assert {
        p.relative_to(tmp_path).as_posix(): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    } == before


def test_full_chain_cycle_is_diagnosed_even_when_nearer_owned_icon_wins(tmp_path):
    chain_vault(tmp_path)
    write_note(
        tmp_path,
        "Categories/H0.md",
        provider="[[H9]]",
        categories=("[[Categories/H9.md]]",),
        icon="[[Attachments/owned.png]]",
        role=True,
    )
    write_note(
        tmp_path,
        "Notes/N9.md",
        provider="[[H8]]",
        categories=("[[Categories/H8.md]]",),
        icon="[[Attachments/owned.png]]",
    )
    result = check_vault(tmp_path)
    assert result.outcome == "issues"
    cycles = [i for i in result.issues if i.code == "provider_cycle"]
    assert {i.artifact for i in cycles} == {
        f"Categories/H{i}.md" for i in range(10)
    } | {"Notes/N8.md", "Notes/N9.md"}
    assert {i.artifact for i in result.issues if i.code == "icon_lookup_depth"} == {
        "Categories/H9.md"
    }
    ordinary = next(i for i in cycles if i.artifact == "Notes/N9.md")
    assert ordinary.reference.count("[[Categories/H8.md]]") == 2
    assert (
        "Categories/H0.md" in ordinary.reference
        and "Categories/H9.md" in ordinary.reference
    )
    projected = check_application(tmp_path)
    assert not projected.field_errors and all(
        f.severity == "warning" for f in projected.findings
    )


def test_invalid_provider_chain_remains_diagnostic_after_nearer_icon_success(tmp_path):
    chain_vault(tmp_path)
    write_note(
        tmp_path,
        "Categories/H1.md",
        provider="[[Categories/Missing.md]]",
        categories=("[[Categories/H0.md]]",),
        role=True,
    )
    write_note(
        tmp_path,
        "Notes/N9.md",
        provider="[[H8]]",
        categories=("[[Categories/H8.md]]",),
        icon="[[Attachments/owned.png]]",
    )
    downstream_before = (tmp_path / "Notes/N9.md").read_bytes()
    result = check_vault(tmp_path)
    assert result.outcome == "issues"
    assert not any(i.code == "icon_lookup_depth" for i in result.issues)
    (direct,) = [
        i
        for i in result.issues
        if i.artifact == "Categories/H1.md" and i.code == "invalid_provider"
    ]
    assert direct.reference == "[[Categories/Missing.md]]"
    (affected,) = [
        i
        for i in result.issues
        if i.artifact == "Notes/N9.md" and i.code == "invalid_provider"
    ]
    assert affected.reference.startswith("[[Notes/N9.md]] -> [[Categories/H8.md]]")
    assert affected.reference.endswith("[[Categories/H1.md]]")
    assert "chain" in affected.message
    projected = check_application(tmp_path)
    assert not projected.field_errors
    (downstream,) = [
        f
        for f in projected.findings
        if f.code == "invalid_provider" and f.path == "Notes/N9.md"
    ]
    assert downstream.severity == "warning"
    assert downstream.message == (
        "Invalid appearance-category chain. Review the selected providers."
    )
    assert (
        "In the note with the invalid declaration, choose one of its category memberships"
        in projected.diagnostic_text
    )
    assert "Choose one of this note’s categories" not in projected.model_dump_json()
    # N9's own H8 choice is valid; repairing only upstream H1 clears its finding.
    assert (tmp_path / "Notes/N9.md").read_bytes() == downstream_before
    write_note(
        tmp_path,
        "Categories/H1.md",
        provider="[[Categories/H0.md]]",
        categories=("[[Categories/H0.md]]",),
        role=True,
    )
    repaired = check_application(tmp_path)
    assert not any(f.code == "invalid_provider" for f in repaired.findings)
    assert not any(f.path == "Notes/N9.md" for f in repaired.findings)
    assert (tmp_path / "Notes/N9.md").read_bytes() == downstream_before


@pytest.mark.parametrize("repeated", [False, True])
def test_blank_or_repeated_next_provider_is_not_a_depth_warning(tmp_path, repeated):
    chain_vault(tmp_path)
    provider = "[[H8]]" if repeated else None
    write_note(
        tmp_path,
        "Categories/H1.md",
        provider=provider,
        categories=("[[Categories/H8.md]]",) if repeated else (),
        role=True,
    )
    result = check_vault(tmp_path)
    assert not any(i.code == "icon_lookup_depth" for i in result.issues)
    if repeated:
        assert {i.code for i in result.issues} == {"provider_cycle"}
        assert {i.artifact for i in result.issues} == {
            f"Categories/H{i}.md" for i in range(1, 10)
        } | {"Notes/N8.md", "Notes/N9.md"}
        (affected,) = [i for i in result.issues if i.artifact == "Notes/N9.md"]
        assert affected.reference.endswith(
            "[[Categories/H1.md]] -> [[Categories/H8.md]]"
        )
    else:
        assert result.outcome == "clean" and result.issues == ()
