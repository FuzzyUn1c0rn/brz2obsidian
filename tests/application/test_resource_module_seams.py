import pytest
from pydantic import ValidationError

from brz2obsidian.contracts import Asset, Item, MigrationRefused, SourceAccounting
from brz2obsidian.core import analyze, plan
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_minimal_workflow import make_archive


def generic_snapshot(tmp_path):
    with BrzSourceModule().open(make_archive(tmp_path / "source.brz")) as session:
        snapshot = session.snapshot
    items = (
        Item(
            key="entry",
            original_identity="other:entry",
            naming_seed="abcdabcd00000000",
            title="Entry",
        ),
        Item(
            key="resource-owner",
            original_identity="other:resource",
            naming_seed="abcdabcd11111111",
            title="Files",
            resource_ids=("binary",),
        ),
    )
    asset = Asset(
        asset_id="binary",
        owner="resource-owner",
        naming_seed="123456789abcdef0",
        original_name="report.pdf",
        role="file",
        availability="present",
        actual_length=4,
        actual_sha256="0" * 64,
    )
    return snapshot.model_copy(
        update={
            "entry_key": "entry",
            "items": items,
            "documents": (),
            "assets": (asset,),
            "accounting": SourceAccounting(entries=()),
        }
    )


def test_public_planner_groups_resources_without_uuid_identity_assumptions(tmp_path):
    snapshot = generic_snapshot(tmp_path)
    planned = plan(analyze(snapshot, BRZ_POLICY))
    assert (
        planned.asset_targets[0].relative_path == "Attachments/abcdabcd1111/report.pdf"
    )
    assert (
        planned.asset_targets[0].resource_link == "Attachments/abcdabcd1111/report.pdf"
    )
    assert {target.item_key: target.created for target in planned.item_targets} == {
        "entry": True,
        "resource-owner": True,
    }


def test_public_analysis_refuses_resource_references_assigned_to_another_owner(
    tmp_path,
):
    snapshot = generic_snapshot(tmp_path)
    entry, owner = snapshot.items
    snapshot = snapshot.model_copy(
        update={
            "items": (entry.model_copy(update={"resource_ids": ("binary",)}), owner)
        }
    )
    with pytest.raises(MigrationRefused) as refused:
        analyze(snapshot, BRZ_POLICY)
    assert refused.value.issues[0].code == "invalid_reference"


def test_owner_tokens_handle_short_seed_that_prefixes_another_generic_seed(tmp_path):
    snapshot = generic_snapshot(tmp_path)
    entry, owner = snapshot.items
    snapshot = snapshot.model_copy(
        update={"items": (entry.model_copy(update={"naming_seed": "abcdabcd"}), owner)}
    )
    planned = plan(analyze(snapshot, BRZ_POLICY))
    assert (
        planned.asset_targets[0].relative_path == "Attachments/abcdabcd1111/report.pdf"
    )


def test_resource_contract_requires_safe_stable_hexadecimal_naming_seed():
    with pytest.raises(ValidationError):
        Asset(
            asset_id="opaque",
            owner="owner",
            naming_seed="../unsafe",
            original_name="file.pdf",
            role="file",
            availability="present",
            actual_length=1,
            actual_sha256="0" * 64,
        )
