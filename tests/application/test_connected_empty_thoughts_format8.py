"""Format 8's output before connected empty thoughts become generated notes."""

import hashlib
import json
from contextlib import closing

import pytest

from brz2obsidian.contracts import Asset, Document, SourceSnapshot
from brz2obsidian.core import analyze, plan
from brz2obsidian.obsidian import render
from brz2obsidian.sources.thebrain.local_api import (
    LOCAL_API_POLICY_V3,
    LOCAL_API_POLICY_V5,
    LocalApiSession,
)
from tests.application.test_graph_modules import POLICY, edge, generated, item, snapshot
from tests.application.test_module_seams import METADATA
from tests.sources.test_local_api import golden_inputs
from tests.sources.test_local_api_icons_v5 import vector_inputs


def test_format8_reserves_a_colliding_empty_hub_and_lists_uncreated_jump_pair():
    body = "The generated twin has source prose."
    digest = hashlib.sha256(body.encode()).hexdigest()
    facts = snapshot(
        (
            item("hub", "Twin", "111111111111"),
            item("child", "Twin", "222222222222", document_ids=("prose",)),
            item("second", "Child category", role="definition"),
            item("jump-a", "Jump A"),
            item("jump-b", "Jump B"),
        ),
        (
            edge("home-hub", "entry", "hub"),
            edge("hub-child", "hub", "child"),
            edge("hub-second", "hub", "second"),
            edge("jump", "jump-a", "jump-b", "related"),
        ),
        (
            Document(
                key="prose",
                owner="child",
                text=body,
                text_digest=digest,
                original_asset_id="prose-original",
            ),
        ),
        (
            Asset(
                asset_id="prose-original",
                owner="child",
                naming_seed="3333",
                original_name="Notes.md",
                role="note_original",
                availability="present",
                actual_length=len(body),
                actual_sha256=digest,
            ),
        ),
    )
    migration = plan(analyze(facts, POLICY), output_format=8)
    assert {
        row.item_key: (row.relative_path, row.created, row.creation_reasons)
        for row in migration.item_targets
    } == {
        "entry": ("Home — Entry.md", True, ("home",)),
        "hub": ("Notes/Twin — 11111111.md", False, ()),
        "child": ("Notes/Twin — 22222222.md", True, ("content",)),
        "second": ("Categories/Child category.md", True, ("definition",)),
        "jump-a": ("Notes/Jump A.md", False, ()),
        "jump-b": ("Notes/Jump B.md", False, ()),
    }

    vault = render(migration, METADATA)
    assert "Notes/Twin — 11111111.md" not in {
        output.relative_path for output in vault.generated_files
    }
    assert "## Children\n\n- [[Notes/Twin — 11111111.md|Twin]]\n" in generated(
        vault, "Home — Entry.md"
    )
    assert "## Parents\n\n- [[Notes/Twin — 11111111.md|Twin]]\n" in generated(
        vault, "Notes/Twin — 22222222.md"
    )
    assert generated(vault, "Uncreated targets.md") == (
        "# Uncreated targets\n\n"
        "## Related pairs\n\n"
        "- [[Notes/Jump A.md|Jump A]] — [[Notes/Jump B.md|Jump B]]\n"
    )
    record = json.loads(generated(vault, "migration-record.json"))
    assert (record["schema_version"], record["renderer_version"]) == (8, "8")
    assert record["source_identity"]["snapshot_digest"] == "b" * 64


@pytest.mark.parametrize(
    ("policy", "digest", "rendered_body"),
    (
        (
            LOCAL_API_POLICY_V3,
            "003c612704b201d187903d6e6bcb63e6ec62fe9199642a5a2e11bd9578979ece",
            "# Home\n\nA\nB\n",
        ),
        (
            LOCAL_API_POLICY_V5,
            "6425afb7e8f3d2a1339e641777090f84fbfe0af475e8e5ee2075139b6f64f603",
            "# Home\n\n![[Attachments/00000000/Icon.png]]\n\nA\nB\n",
        ),
    ),
    ids=("historical-profile3", "default-profile5"),
)
def test_format8_output_preserves_qualified_api_capture_identity(
    tmp_path, policy, digest, rendered_body
):
    if policy.profile_version == "5":
        _, _, arguments = vector_inputs()
    else:
        source, frozen, audit, payloads = golden_inputs("3")
        arguments = {
            "source": source,
            "snapshot": SourceSnapshot.model_validate_json(json.dumps(frozen)),
            "audit": audit,
            "payloads": payloads,
            "profile_version": "3",
        }
    with closing(LocalApiSession(**arguments, capture_parent=tmp_path)) as session:
        vault = render(
            plan(analyze(session.snapshot, policy), output_format=8), METADATA
        )
        session.verify_consistency()

    record = json.loads(generated(vault, "migration-record.json"))
    assert (record["schema_version"], record["renderer_version"]) == (8, "8")
    assert record["profile_version"] == policy.profile_version
    assert record["source_identity"]["format_version"] == "1"
    assert record["source_identity"]["snapshot_digest"] == digest
    (home,) = record["item_targets"]
    assert (
        home["original_identity"],
        home["relative_path"],
        home["created"],
        home["creation_reasons"],
    ) == (
        "00000000-0000-4000-8000-000000000002",
        "Home — Home.md",
        True,
        ["content", "home"],
    )
    assert rendered_body in generated(vault, "Home — Home.md")
