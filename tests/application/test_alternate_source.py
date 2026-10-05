import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

import brz2obsidian
from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.contracts import FindingDisposition, MigrationRefused, RunResult
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import ObsidianRenderer, render
from brz2obsidian.publication import FilesystemPublisher, publish
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_module_seams import METADATA
from tests.support.folio_source import FOLIO_POLICY, FolioSourceModule
from tests.support.notes import note_body
from tests.support.paired_sources import paired_sources
from tests.support.paired_v2_sources import paired_v2_sources


def workflow(source, policy):
    return Workflow(
        SourceModuleBinding(source, policy),
        ObsidianRenderer(),
        FilesystemPublisher(),
        metadata_factory=lambda: METADATA,
    )


def test_opaque_source_and_real_brz_publish_corresponding_vaults(tmp_path, capsys):
    brz, folio = paired_sources(tmp_path)
    results = []
    vaults = []
    for index, (module, policy, source) in enumerate(
        (
            (BrzSourceModule(), BRZ_POLICY, brz),
            (FolioSourceModule(), FOLIO_POLICY, folio),
        )
    ):
        vault = tmp_path / f"vault-{index}"
        operation = workflow(module, policy)
        inspected = operation.inspect(source)
        assert inspected.outcome == "clean" and inspected.receipt is None
        result = operation.convert(source, vault)
        assert result.outcome == "clean" and result.receipt.verified
        assert result.counts.actual_notes == 3
        assert result.counts.actual_assets == 4
        assert result.counts.source_items == 10
        assert result.counts.source_relationships == 5
        assert result.counts.actual_references == 2
        results.append(result)
        vaults.append(vault)
    assert results[0].counts == results[1].counts
    assert results[0].source_identity != results[1].source_identity
    assert (
        results[0].source_identity.source_sha256
        != results[1].source_identity.source_sha256
    )
    for name in (
        "Home — Opening.md",
        "Notes/Middle.md",
        "Notes/Focus.md",
        "Uncreated targets.md",
        "Tag memberships.md",
        "MIGRATION REPORT.md",
        ".obsidian/app.json",
        ".obsidian/bookmarks.json",
        "Attachments/00000001/map.png",
        "Attachments/00000001/manual.bin",
        "Attachments/00000006/Notes.md.original",
    ):
        a, b = (vaults[0] / name).read_bytes(), (vaults[1] / name).read_bytes()
        if name in {"Home — Opening.md", "Notes/Middle.md", "Notes/Focus.md"}:
            assert note_body(a) == note_body(b)
            for index, data in enumerate((a, b)):
                assert (
                    json.dumps(results[index].source_identity.source_id).encode()
                    in data
                )
        else:
            assert a == b
    records = [json.loads((v / "migration-record.json").read_bytes()) for v in vaults]
    assert {t["item_key"] for t in records[1]["item_targets"]} == {
        "entry:opening",
        "empty:leaf",
        "chain:first",
        "chain:middle",
        "chain:last",
        "tag:focus",
        "tag:unused",
        "peer:left",
        "peer:right",
        "orphan:alone",
    }
    assert records[1]["source_identity"]["module_id"] == "synthetic-folio"
    assert records[1]["profile_id"] == "synthetic-folio-reviewed"
    assert records[1]["original_evidence"][0]["records"] == json.loads(
        folio.read_bytes()
    )
    assert len(records[0]["original_evidence"]) > 1
    for record in records:
        assert {t["relative_path"]: t["created"] for t in record["item_targets"]} == {
            "Home — Opening.md": True,
            "Notes/Empty.md": False,
            "Notes/First.md": False,
            "Notes/Middle.md": True,
            "Notes/Last.md": False,
            "Notes/Focus.md": True,
            "Notes/Unused.md": False,
            "Notes/Left.md": False,
            "Notes/Right.md": False,
            "Notes/Alone.md": False,
        }
        assert {
            (r["kind"], r["target_a"], r["target_b"]) for r in record["relationships"]
        } == {
            ("hierarchy", "Notes/First.md", "Notes/Middle.md"),
            ("hierarchy", "Notes/Middle.md", "Notes/Last.md"),
            ("related", "Notes/Left.md", "Notes/Right.md"),
            ("tag", "Notes/Focus.md", "Home — Opening.md"),
            ("tag", "Notes/Focus.md", "Notes/Empty.md"),
        }
        assert {
            (m["item_target"], m["token"], m["native"])
            for m in record["tag_memberships"]
        } == {
            ("Home — Opening.md", "Focus", True),
            ("Notes/Empty.md", "Focus", False),
        }
    assert note_body((vaults[1] / "Notes/Middle.md").read_bytes()) == (
        b"# Middle\n\n## Parents\n\n- [[Notes/First.md|First]]\n\n## Children\n\n- [[Notes/Last.md|Last]]\n"
    )
    assert (
        b"Welcome [[Notes/Empty.md|Empty]].\r\n![Map](Attachments/00000001/map.png)\r\n"
        in (vaults[1] / "Home — Opening.md").read_bytes()
    )
    assert (vaults[0] / "Attachments/00000001/Notes.md.original").read_bytes() != (
        vaults[1] / "Attachments/00000001/Notes.md.original"
    ).read_bytes()
    assert (vaults[1] / "Attachments/00000001/Notes.md.original").read_bytes() == (
        b"Welcome [Empty](folio:empty).\r\n![Map](folio:map)\r\n"
    )
    assert capsys.readouterr() == ("", "")


def update_folio(path, change):
    data = json.loads(path.read_bytes())
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("start", [None, "absent:key", "tag:focus"])
def test_alternate_entry_refusal_is_durable_and_does_not_publish(tmp_path, start):
    _, source = paired_sources(tmp_path)
    update_folio(source, lambda data: data.update(start=start))
    destination = tmp_path / "vault"
    result = workflow(FolioSourceModule(), FOLIO_POLICY).convert(source, destination)
    assert result.outcome == "refused"
    assert result.issues[0].code == "invalid_entry"
    assert result.counts.source_items == 10 and result.counts.planned_notes is None
    assert result.receipt is None and not destination.exists()


@pytest.mark.parametrize("invalid", ["endpoint", "target", "span"])
def test_invalid_alternate_normalized_references_refuse_before_publication(
    tmp_path, invalid
):
    _, source = paired_sources(tmp_path)

    def change(data):
        if invalid == "endpoint":
            data["connections"][0]["item_b"] = "absent:item"
        else:
            reference = data["documents"][0]["references"][0]
            reference["target" if invalid == "target" else "start"] = (
                "absent:item" if invalid == "target" else 0
            )

    update_folio(source, change)
    destination = tmp_path / "vault"
    result = workflow(FolioSourceModule(), FOLIO_POLICY).convert(source, destination)
    assert result.outcome == "refused" and result.issues[0].code == "invalid_reference"
    assert result.receipt is None and not destination.exists()


@pytest.mark.parametrize("field", ["module_id", "module_version", "format_version"])
def test_alternate_incompatible_reviewed_profile_refuses(tmp_path, field):
    _, source = paired_sources(tmp_path)
    policy = FOLIO_POLICY.model_copy(update={field: "incompatible"})
    result = workflow(FolioSourceModule(), policy).inspect(source)
    assert result.outcome == "refused" and result.issues[0].code == "unsupported_format"
    assert result.inspection is None and result.receipt is None


def add_finding(data):
    data["findings"] = [
        {
            "kind": "fixture_metadata_discrepancy",
            "rule_id": "folio.reviewed-length/v1",
            "affected": ["asset:104:file-manual"],
            "observed_json": '{"declared":90,"actual":19}',
        }
    ]


def test_alternate_unknown_finding_refuses_and_reviewed_rule_warns(tmp_path):
    _, source = paired_sources(tmp_path)
    update_folio(source, add_finding)
    operation = workflow(FolioSourceModule(), FOLIO_POLICY)
    refused = operation.convert(source, tmp_path / "refused")
    assert (
        refused.outcome == "refused" and refused.issues[0].code == "unsupported_feature"
    )
    assert refused.receipt is None and not (tmp_path / "refused").exists()
    disposition = FindingDisposition(
        rule_id="folio.reviewed-length/v1",
        kind="fixture_metadata_discrepancy",
        disposition="warning",
        issue_code="approved_metadata_discrepancy",
        message="Synthetic declared length differs; actual payload is intact.",
        guidance="Review the synthetic original evidence.",
    )
    policy = FOLIO_POLICY.model_copy(update={"finding_dispositions": (disposition,)})
    result = workflow(FolioSourceModule(), policy).convert(source, tmp_path / "warned")
    assert result.outcome == "warnings" and result.receipt.verified
    assert [i.code for i in result.issues] == ["approved_metadata_discrepancy"]
    assert result.issues[0].rule_id == "folio.reviewed-length/v1"


@pytest.mark.parametrize(
    "fault,code,outcome",
    [
        ({"stream_failure": True}, "write_failure", "failed"),
        ({"read_failure": True}, "write_failure", "failed"),
        ({"mutate_on_payload": True}, "source_changed", "refused"),
    ],
)
def test_alternate_source_and_stream_failures_leave_no_vault_or_staging(
    tmp_path, fault, code, outcome
):
    _, source = paired_sources(tmp_path)
    destination = tmp_path / "vault"
    result = workflow(FolioSourceModule(**fault), FOLIO_POLICY).convert(
        source, destination
    )
    assert result.outcome == outcome
    assert result.issues[0].code == code
    assert result.counts.planned_notes == 3 and result.counts.actual_notes is None
    assert result.receipt is None and not destination.exists()
    assert list(tmp_path.glob(".brz2obsidian-*")) == []


def test_alternate_teardown_failure_preserves_actual_verified_receipt(tmp_path):
    _, source = paired_sources(tmp_path)
    result = workflow(FolioSourceModule(teardown_failure=True), FOLIO_POLICY).convert(
        source, tmp_path / "vault"
    )
    assert (
        result.outcome == "failed"
        and result.receipt.published
        and result.receipt.verified
    )
    assert result.counts.actual_notes == 3 and result.counts.actual_assets == 4
    assert [i.code for i in result.issues] == [
        "session_teardown_failure",
        "publication_occurred",
    ]
    assert (
        tmp_path / "vault/Attachments/00000001/manual.bin"
    ).read_bytes() == b"\x00\x01synthetic manual\xff"


def test_alternate_session_revokes_streams_and_detects_later_source_changes(tmp_path):
    _, source = paired_sources(tmp_path)
    module = FolioSourceModule()
    with module.open(source) as session:
        manager = session.open_payload("asset:104:file-manual")
        stream = manager.__enter__()
        assert stream.read(2) == b"\x00\x01"
    with pytest.raises(ValueError):
        stream.read()
    with pytest.raises(OSError, match="closed"):
        session.verify_consistency()
    with pytest.raises(OSError, match="closed"):
        session.open_payload("asset:104:file-manual").__enter__()
    with pytest.raises(OSError, match="closed"):
        manager.__exit__(None, None, None)
    with module.open(source) as current:
        (source.parent / "payload-104").write_bytes(b"changed bytes")
        with pytest.raises(MigrationRefused) as changed:
            current.verify_consistency()
        assert changed.value.issues[0].code == "source_changed"


def test_alternate_public_modules_and_another_presentation_need_no_cli(
    tmp_path, monkeypatch, capsys
):
    _, source = paired_sources(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Library use must not parse arguments or exit the process")

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", forbidden)
    monkeypatch.setattr(sys, "exit", forbidden)
    with FolioSourceModule().open(source) as session:
        analysis = analyze(session.snapshot, FOLIO_POLICY)
        assert analysis.entry_key == "entry:opening"
        assert analysis.snapshot.items[0].original_identity == "entry:opening"
        prepared = render(plan(analysis), METADATA)
        receipt = publish(prepared, session, tmp_path / "direct")
    assert receipt.counts.actual_notes == 3
    result = workflow(FolioSourceModule(), FOLIO_POLICY).inspect(source)
    consumed = RunResult.model_validate_json(result.model_dump_json(by_alias=True))
    view = {"status": consumed.outcome, "notes": consumed.counts.planned_notes}
    assert view == {"status": "clean", "notes": 3}
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    "source_factory,notes", [(paired_sources, 3), (paired_v2_sources, 5)]
)
def test_generic_package_initializers_and_workflow_operate_with_source_and_cli_imports_blocked(
    tmp_path,
    source_factory,
    notes,
):
    _, source = source_factory(tmp_path)
    code = """
import importlib.abc, sys
class BlockOuter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith("brz2obsidian.sources") or fullname in {
            "brz2obsidian.cli", "brz2obsidian.__main__", "brz2obsidian.application.wiring"
        }:
            raise AssertionError("Forbidden outer import: " + fullname)
sys.meta_path.insert(0, BlockOuter())
from brz2obsidian.application import SourceModuleBinding, Workflow
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import ObsidianRenderer
from brz2obsidian.publication import FilesystemPublisher
from tests.support.folio_source import FolioSourceModule, FOLIO_POLICY
result = Workflow(SourceModuleBinding(FolioSourceModule(), FOLIO_POLICY), ObsidianRenderer(), FilesystemPublisher()).convert(sys.argv[1], sys.argv[2])
assert result.outcome == "clean" and result.receipt.verified
assert result.counts.actual_notes == int(sys.argv[3])
if int(sys.argv[3]) == 5:
    from pathlib import Path
    root = Path(sys.argv[2])
    assert result.counts.actual_category_notes == 1
    for name in ('Categories/Concept.md', 'Templates/Concept.md', 'Templates/Bases/Members.base', '.obsidian/templates.json'):
        assert (root / name).is_file()
    assert 'appearance_category: "[[Categories/Concept.md]]"' in (root / 'Notes/Empty.md').read_text()
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(source),
            str(tmp_path / "isolated"),
            str(notes),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""


def test_reusable_modules_import_only_inward_packages_including_initializers():
    root = Path(brz2obsidian.__file__).parent
    allowed = {
        "contracts": {"brz2obsidian", "brz2obsidian.contracts"},
        "core": {"brz2obsidian", "brz2obsidian.contracts", "brz2obsidian.core"},
        "obsidian": {
            "brz2obsidian",
            "brz2obsidian.contracts",
            "brz2obsidian.core",
            "brz2obsidian.obsidian",
        },
        "publication": {
            "brz2obsidian",
            "brz2obsidian.contracts",
            "brz2obsidian.publication",
        },
        "application": {
            "brz2obsidian",
            "brz2obsidian.contracts",
            "brz2obsidian.core",
            "brz2obsidian.application.workflow",
        },
        "vault_check": {
            "brz2obsidian",
            "brz2obsidian.contracts",
            "brz2obsidian.vault_check",
        },
    }
    for area, permitted in allowed.items():
        files = (
            [root / "contracts.py"]
            if area == "contracts"
            else sorted((root / area).rglob("*.py"))
        )
        for file in files:
            if file.name == "wiring.py":
                continue  # The outer composition explicitly selects implementations.
            relative = file.relative_to(root).with_suffix("")
            module = "brz2obsidian." + ".".join(relative.parts)
            package = (
                module.removesuffix(".__init__")
                if file.name == "__init__.py"
                else module.rsplit(".", 1)[0]
            )
            for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    imports = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = (
                        importlib.util.resolve_name(
                            "." * node.level + (node.module or ""), package
                        )
                        if node.level
                        else node.module
                    )
                    imports = [base] + [base + "." + alias.name for alias in node.names]
                else:
                    continue
                for imported in imports:
                    if imported.startswith("brz2obsidian"):
                        assert any(
                            imported == prefix or imported.startswith(prefix + ".")
                            for prefix in permitted
                            if prefix != "brz2obsidian"
                        ) or imported in {"brz2obsidian", "brz2obsidian.__version__"}, (
                            file,
                            imported,
                        )
