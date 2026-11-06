"""An unrelated ordinary resource keeps its metadata-only lookup through Undo."""

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_facts import assemble_facts
from brz2obsidian.application.update_lifecycle import text_choice_action
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from tests.application.test_vault_checkpoints import fixture_case, git
from tests.reconciliation.test_resolution import action
from tests.reconciliation.test_type_tag_dependencies import graph_payload


def test_current8_undo_retains_unaffected_metadata_only_resource_without_fabricating_state():
    baseline = {
        name: raw.replace(b"[[A.svg]]", b"[[Attachments/A.svg]]")
        for name, raw in graph_payload().items()
    }
    incoming = dict(baseline)
    incoming["Categories/C.md"] = baseline["Categories/C.md"].replace(
        b"Original.", b"Incoming C."
    )
    vault, source = fixture_case()
    for directory in (vault, source):
        for name, raw in baseline.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    manual = vault / "Attachments/manual.bin"
    manual.write_bytes(b"\x00unrelated ordinary user attachment")
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "Retained unrelated binary")
    operations = Operations()
    observed = operations.inspect_history(vault)
    facts = assemble_facts(
        baseline,
        incoming,
        baseline,
        proposal_id="metadata-only-undo",
        generation=1,
        current_inventory=tuple(
            row
            for row in observed.admission.inventory
            if row.path == "Attachments/manual.bin"
        ),
    )
    target_id = "physical:Attachments/manual.bin"
    assert any(t.target_id == target_id for t in facts.link_context.current_targets)
    assert not any(
        s.target_id == target_id for s in facts.link_context.current_target_facts
    )
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="metadata-only-vault",
        import_id="metadata-only-import",
        identity=facts.incoming_identity,
        admission=observed.admission,
    )
    assert captured.status == "captured", captured.code
    (source / "Categories/C.md").write_bytes(incoming["Categories/C.md"])
    plan = prepare_review(
        facts, preflight=operations.inspect_history(vault).admission.preflight
    )
    change = next(c for c in plan.proposal.changes if c.item_id == "category:C")
    chosen = resolve_review(
        plan,
        text_choice_action(plan, action(plan, change, choice="incoming")),
    )
    assert chosen.status == "accepted" and chosen.plan.ready, chosen.code
    applied = operations.apply_reviewed_update(
        vault,
        source,
        review=chosen.plan,
        source_binding=operations.observe_reviewed_source(source, chosen.plan),
        vault_id="metadata-only-vault",
        import_id="metadata-only-import",
    )
    assert applied.status == "applied" and applied.history == "terminal", applied.code
    before = (
        manual.read_bytes(),
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)"),
        operations.read_checkpoint(vault).locator,
    )
    offered = operations.prepare_undo(vault)
    assert (
        offered.status == "offered"
        and offered.checkpoint_commit == applied.result_commit
    ), offered.code
    assert offered.checkpoint_commit == before[-1].commit
    assert offered.generation == before[-1].generation
    assert offered.target_receipt_commit == applied.receipt_commit
    context = offered.review.producer_facts.link_context
    original = next(
        t for t in facts.link_context.current_targets if t.target_id == target_id
    )
    for stage in ("current", "incoming"):
        assert (
            next(
                t
                for t in getattr(context, stage + "_targets")
                if t.target_id == target_id
            )
            == original
        )
        assert not any(
            s.target_id == target_id for s in getattr(context, stage + "_target_facts")
        )
        owned_image = next(
            state
            for state in getattr(context, stage + "_target_facts")
            if state.target_id == "subject:image:a:asset"
        )
        assert owned_image.existence == "present" and owned_image.content is not None
        assert owned_image.file_roles is not None and owned_image.file_roles.image_path
    assert not any(
        s.current.path == "Attachments/manual.bin"
        for s in offered.review.producer_facts.subjects
    )
    assert not offered.review.ready
    assert select_review_effects(offered.review).status == "refused"
    requirement = offered.review.requirements[0]
    change = next(
        c
        for c in offered.review.proposal.changes
        if c.change_id == requirement.change_id
    )
    request = text_choice_action(
        offered.review,
        action(
            offered.review,
            change,
            domain=requirement.domain,
            choice="reverse" if "reverse" in requirement.choices else "incoming",
            decision_id="explicit-C-undo",
        ),
    )
    resolved = resolve_review(offered.review, request)
    assert resolved.status == "accepted" and resolved.plan.ready, resolved.code
    effects = select_review_effects(resolved.plan)
    assert effects.status == "selected" and not effects.remove_paths
    assert [(row.path, row.content.data) for row in effects.files] == [
        ("Categories/C.md", baseline["Categories/C.md"])
    ]
    assert (
        manual.read_bytes(),
        git(vault, "rev-parse", "HEAD"),
        (vault / ".git/index").read_bytes(),
        git(vault, "for-each-ref", "--format=%(refname) %(objectname)"),
        operations.read_checkpoint(vault).locator,
    ) == before
    assert (vault / "Categories/C.md").read_bytes() == incoming["Categories/C.md"]
