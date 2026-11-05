"""Public BRZ update journeys for direct type members and provider chains."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.wiring import default_workflow
from brz2obsidian.contracts import OutputIdentity
from tests.application.test_update_lifecycle import git
from tests.support.type_tag_sources import BRAIN, ICON, PNG, brz_source


@pytest.fixture
def update_root():
    # The supported history route requires a vault outside the parent repository.
    # Retain every run, including failed admission/publication evidence.
    root = Path(tempfile.mkdtemp(prefix="brz2obsidian-r292-m4-"))
    evidence = Path(__file__).resolve().parents[2] / "tmp/r292-m4/fixtures"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / (root.name + ".json")).write_text(
        json.dumps({"root": str(root), "purpose": "synthetic public update journey"}),
        encoding="utf-8",
    )
    return root


def seed_current(root):
    source = brz_source(root / "v1.brz")
    vault = root / "vault"
    converted = default_workflow().convert(source, vault)
    assert converted.outcome == "clean", converted.issues
    original = root / "original-v1"
    shutil.copytree(vault, original)
    identity = OutputIdentity(
        collection_id=BRAIN,
        module_id="thebrain-brz",
        module_version="11",
        profile_id="thebrain-format5-reviewed",
        profile_version="11",
        output_format=8,
        settings_digest=hashlib.sha256(b"{}").hexdigest(),
    )
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        original,
        vault_id="r292-vault",
        import_id="r292-import",
        identity=identity,
        admission=operations.inspect_history(vault).admission,
    )
    assert captured.status == "captured", captured
    return operations, vault, source, original


def test_current_type_tag_vault_prepares_same_source_without_format_transition(
    update_root,
):
    operations, vault, source, original = seed_current(update_root)
    icon_path = "Attachments/0000000000000000000000000000000a/Icon.png"
    with operations.inspect_update_inputs(vault) as observed:
        proofs = observed.read_attachment_ownership(
            locator=observed.history.checkpoint.locator, paths=(icon_path,)
        )
    assert len(proofs) == 1
    assert proofs[0].identity.item_id == ICON and proofs[0].facet == "asset"
    assert proofs[0].payload_sha256 == hashlib.sha256(PNG).hexdigest()
    assert proofs[0].source_path == icon_path
    result = operations.prepare_update(vault, source)
    assert result.status == "prepared_review", result
    assert result.ready, (
        result.preparation.review.blockers,
        result.preparation.review.requirements,
    )
    assert result.preparation.review.facts.baseline_identity.output_format == 8
    assert result.preparation.review.facts.incoming_identity.output_format == 8
    assert result.preparation.retained_source_provenance
    assert all(
        c.disposition == "no_change" for c in result.preparation.review.proposal.changes
    )
    applied = operations.apply_update(result.preparation)
    assert (applied.status, applied.publication) == (
        "no_content_change",
        "not_published",
    )
    assert (vault / "Categories/B.md").read_bytes() == (
        original / "Categories/B.md"
    ).read_bytes()
