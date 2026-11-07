"""Small synthetic public-API recipes for the three #350 legacy families.

These helpers never invoke test bodies or production private encoders. They are
also the recorded old-writer generation recipe; frozen files are not regenerated
by compatibility tests.
"""

import json
import subprocess
from pathlib import Path

from brz2obsidian.application.operations import Operations
from brz2obsidian.contracts import ContentVersion, ReviewConsentRequirement
from brz2obsidian.core import prepare_review, refresh_review, resolve_review
from tests.reconciliation.test_attachments import (
    attachment_candidate,
    attachment_request,
)
from tests.reconciliation.test_formats import operation
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def attachment_plan():
    facts = attachment_request()
    selection, candidate = attachment_candidate(facts, "both")
    initial = prepare_review(facts, preflight=preflight())
    consent = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement",
        schema_version=1,
        consent_id="legacy:storage",
        kind="storage",
        requirement="required",
        policy="ordinary",
        fingerprint="legacy:storage-policy",
        disclosure="Retain both exact binary outputs",
        subjects=(initial.proposal.changes[0].subject_id,),
    )
    checks = preflight().model_copy(update={"consents": (consent,)})
    plan = prepare_review(facts, preflight=checks)
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="attachment",
            choice="both",
            decision_id="legacy:both",
            attachment_selection=selection,
            attachment_candidate=candidate,
        ),
    ).plan
    requirement = next(row for row in plan.requirements if row.domain == "storage")
    plan = resolve_review(
        plan,
        action(
            plan,
            domain="storage",
            choice="accept",
            decision_id="legacy:consent",
            change_id=requirement.change_id,
            reviewed_assumptions=requirement.assumptions,
        ),
    ).plan
    assert plan.ready
    refreshed = refresh_review(
        plan, facts.model_copy(update={"generation": 2}), preflight=checks
    )
    assert refreshed.status == "accepted" and refreshed.plan.ready
    return refreshed.plan


def unknown_plan():
    facts = request(current=b"authored\xff", incoming=b"target format 7\n")
    subject = facts.subjects[0].model_copy(
        update={
            "baseline": ContentVersion(
                status="unknown", content=None, unavailable_digest="older:unavailable"
            )
        }
    )
    facts = with_review_links(
        facts.model_copy(
            update={
                "subjects": (subject,),
                "baseline_identity": facts.baseline_identity.model_copy(
                    update={"output_format": 6}
                ),
                "format_operation": operation(
                    "onboarding",
                    recorded_generation="unavailable",
                    established_baseline=None,
                ),
            }
        ),
        opaque_link_free=True,
    )
    return prepare_review(facts, preflight=preflight())


def checkpoint_plan():
    facts = with_review_links(
        request(
            original=b"baseline-only\n",
            current=b"authored current\r\n",
            incoming=b"incoming next\n",
            generation=3,
        )
    )
    initial = prepare_review(facts, preflight=preflight())
    chosen = resolve_review(
        initial, action(initial, choice="current", decision_id="legacy:keep-current")
    )
    assert chosen.status == "accepted" and chosen.plan.ready
    return chosen.plan


def git(vault, *args, input=None):
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Legacy fixture",
            "-c",
            "user.email=legacy@example.invalid",
            "-C",
            str(vault),
            *args,
        ],
        input=input,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def capture_checkpoint(container, plan):
    """Capture real test-owned Git storage without replacing native authority."""
    container = Path(container).resolve()
    vault, source = container / "vault", container / "source"
    for root, raw in ((vault, b"authored current\r\n"), (source, b"incoming next\n")):
        (root / "Notes").mkdir(parents=True)
        (root / "Notes/Opening.md").write_bytes(raw)
    git(vault, "init", "-q")
    git(vault, "config", "core.autocrlf", "false")
    git(vault, "add", ".")
    git(vault, "commit", "-qm", "synthetic user checkpoint")
    operations = Operations()
    captured = operations.capture_checkpoint(
        vault,
        source,
        vault_id="legacy-vault",
        import_id="legacy-import",
        identity=plan.facts.incoming_identity,
        admission=operations.inspect_vault(vault),
        review=plan,
    )
    assert captured.status == "captured", captured.code
    return operations, vault, source, captured


def retarget_checkpoint(vault, captured, *, review=None, review_content=None):
    """Keep outer Git digests coherent so a deliberate inner corruption is tested."""
    import hashlib

    manifest = json.loads(
        git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
    )
    rows = {
        row.split(b"\t", 1)[1]: row
        for row in git(vault, "ls-tree", "-z", captured.commit).split(b"\0")
        if row
    }
    if review is not None:
        oid = git(
            vault, "hash-object", "-w", "--no-filters", "--stdin", input=review
        ).strip()
        rows[b"review.json"] = b"100644 blob " + oid + b"\treview.json"
        manifest.update(
            review_object=oid.decode(),
            review_size=len(review),
            review_sha256=hashlib.sha256(review).hexdigest(),
        )
    if review_content is not None:
        manifest["review_content"] = review_content
        assert review_content == []  # This recipe only removes the owned role.
        rows.pop(b"review-content")
    raw = json.dumps(manifest).encode()
    oid = git(vault, "hash-object", "-w", "--stdin", input=raw).strip()
    rows[b"manifest.json"] = b"100644 blob " + oid + b"\tmanifest.json"
    tree = (
        git(vault, "mktree", "-z", input=b"\0".join(rows.values()) + b"\0")
        .strip()
        .decode()
    )
    commit = (
        git(vault, "commit-tree", tree, input=b"controlled legacy negative\n")
        .strip()
        .decode()
    )
    locator_path = vault / ".brz2obsidian/locator.json"
    locator = json.loads(locator_path.read_bytes())
    locator["commit"] = commit
    git(vault, "update-ref", captured.ref, commit)
    locator_path.write_text(json.dumps(locator), encoding="utf-8")
