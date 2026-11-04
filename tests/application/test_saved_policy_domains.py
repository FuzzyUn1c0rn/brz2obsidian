"""Public admission preserves separate native policy domains across LOCAL roles."""

from brz2obsidian.application.checkpoint_contracts import (
    CheckpointLocator,
    CheckpointRead,
    VaultAssociation,
)
from brz2obsidian.application.operations import Operations
from brz2obsidian.application.vault_contracts import VaultSubject
from brz2obsidian.core import prepare_review, reconcile, resolve_review
from brz2obsidian.publication import vault_history
from brz2obsidian.publication.vault_native import verify_directory
from tests.application.test_vault_admission import fixture_root, git
from tests.application.test_vault_checkpoints import user_state
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, with_review_links


def _accepted_grants(facts, admission):
    plan = prepare_review(facts, preflight=admission.preflight)
    required = next(row for row in plan.requirements if row.domain == "storage")
    accepted = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="accept",
            change_id=required.change_id,
            reviewed_assumptions=required.assumptions,
        ),
    )
    assert accepted.status == "accepted"
    assert not any(row.domain == "storage" for row in accepted.plan.requirements)
    return accepted.plan.consents


def test_incomparable_missing_policy_queries_keep_their_own_consent(monkeypatch):
    # This controlled qualified-reader port supplies validated role metadata.
    # All policy observations below are real Native Git/attribute observations;
    # this test does not claim complete checkpoint graph validation.
    vault = fixture_root("saved-policy-domains")
    facts = with_review_links(request())
    owner = reconcile(facts).changes[0].subject_id
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    (vault / "Notes").mkdir()
    (vault / "Notes/Opening.md").write_bytes(facts.subjects[0].current.content.data)
    attributes = b"A.bin text eol=lf\nB.bin text eol=crlf\n"
    (vault / ".gitattributes").write_bytes(attributes)
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "First controlled role")
    parent_commit = git(vault, "rev-parse", "HEAD").decode().strip()
    git(vault, "commit", "--allow-empty", "-qm", "Second controlled role")
    child_commit = git(vault, "rev-parse", "HEAD").decode().strip()
    association = VaultAssociation(
        schema_id="brz2obsidian.vault-association",
        schema_version=1,
        association_id="a" * 64,
        vault_id="query-vault",
        import_id="query-import",
        collection_id="folio:collection",
        module_id="synthetic-folio",
        vault_anchor=verify_directory(vault),
        git_anchor=verify_directory(vault / ".git"),
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
    )
    parent = CheckpointLocator(
        schema_id="brz2obsidian.checkpoint-locator",
        schema_version=1,
        association=association,
        commit=parent_commit,
        generation=1,
    )
    child = parent.model_copy(update={"commit": child_commit, "generation": 2})
    role = vault_history._CheckpointRole(
        parent.commit,
        None,
        1,
        "local",
        None,
        None,
        None,
        None,
        None,
        "a" * 64,
    )
    active = {"locator": parent, "roles": (role,)}
    metadata = vault / ".brz2obsidian"
    metadata.mkdir()
    locator_file = metadata / "locator.json"
    locator_file.write_text(parent.model_dump_json())
    git(vault, "update-ref", association.ref, parent.commit)

    def read_validated(root, reader, **kwargs):
        assert root == vault
        kwargs["checkpoint_roles"].extend(active["roles"])
        return CheckpointRead(
            schema_id="brz2obsidian.checkpoint-read",
            schema_version=1,
            status="valid",
            code="controlled_validated_roles",
            locator=active["locator"],
            manifest=None,
            review=None,
            message="Controlled qualified history reader port",
        )

    monkeypatch.setattr(vault_history, "_read", read_validated)
    first = (VaultSubject(path="A.bin", subject_id=owner),)
    second = (VaultSubject(path="B.bin", subject_id=owner),)
    operations = Operations()
    first_policy = operations.inspect_vault(vault, subjects=first)
    second_policy = operations.inspect_vault(vault, subjects=second)
    assert first_policy.status == second_policy.status == "supported"
    assert first_policy.preflight.consents[0].subjects == (owner,)
    assert second_policy.preflight.consents[0].subjects == (owner,)
    assert first_policy.preflight.consents != second_policy.preflight.consents

    def policy(subjects, admission):
        return vault_history._RolePolicy(
            subjects,
            (admission.policy_fingerprint, admission.policy_continuity_fingerprint),
            admission.preflight.consents,
            _accepted_grants(facts, admission),
            "c" * 64,
            "d" * 64,
            None,
        )

    role = role._replace(policy_context=policy(first, first_policy))
    memo = vault_history._CheckpointRole(
        child.commit,
        parent.commit,
        2,
        "local",
        None,
        None,
        None,
        None,
        None,
        "b" * 64,
        first_policy.preflight.state_fingerprint,
        policy_context=policy(second, second_policy),
    )
    active.update(locator=child, roles=(memo, role))
    locator_file.write_text(child.model_dump_json())
    git(vault, "update-ref", association.ref, child.commit)
    before = user_state(vault)
    current = operations.inspect_vault(vault, subjects=second)
    assert current.status == "supported"
    assert (
        current.preflight.state_fingerprint == first_policy.preflight.state_fingerprint
    )
    assert current.preflight.consents == second_policy.preflight.consents
    assert current.policy_fingerprint == second_policy.policy_fingerprint
    assert (
        current.policy_continuity_fingerprint
        == second_policy.policy_continuity_fingerprint
    )
    assert user_state(vault) == before
    # A real rule edit invalidates the alias, even if a combined metadata query
    # could compare the two now-current scopes with one another.
    try:
        (vault / ".gitattributes").write_bytes(attributes + b"Notes/Opening.md text\n")
        changed = operations.inspect_vault(vault, subjects=second)
        assert (
            changed.preflight.state_fingerprint
            != first_policy.preflight.state_fingerprint
        )
    finally:
        (vault / ".gitattributes").write_bytes(attributes)
    assert user_state(vault) == before
    assert not (vault / "A.bin").exists() and not (vault / "B.bin").exists()
