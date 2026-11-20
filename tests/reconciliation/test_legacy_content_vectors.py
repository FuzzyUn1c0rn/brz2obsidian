"""Frozen old-writer oracles at inline replay and public Git admission seams."""

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from brz2obsidian.contracts import ExactContent, ImmutableContentReference
from brz2obsidian.core import load_review, resume_review, select_review_effects
from tests.reconciliation.legacy_content_builder import (
    capture_checkpoint,
    git,
    retarget_checkpoint,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/saved_reviews/memory-347"
ATTACHMENT_OWNER = "ba1c4d1118161042cdba372561029f4e57204cdca8aa4a8645dc8d2e382b39cd"
NOTE_OWNER = "20d73125748080b88350a0def853caf4a625b0f1a4912152c4bb666d42ce8630"


def wire(family):
    return (FIXTURES / (family + ".inline.json")).read_bytes()


@pytest.fixture(scope="module")
def legacy_loaded():
    result = {}
    for family in ("attachment", "unknown", "checkpoint"):
        loaded = load_review(wire(family))
        assert loaded.status == "loaded" and loaded.code == "loaded"
        assert not loaded.ready and not loaded.loaded.ready
        assert loaded.loaded.readiness == "revalidation_required"
        result[family] = loaded.loaded
    return result


def effect_rows(effects):
    return [(row.path, row.subject_id, row.content.data) for row in effects.files]


def test_frozen_files_match_pinned_old_writer_inventory():
    provenance = json.loads((FIXTURES / "provenance.json").read_bytes())
    assert provenance["writer_commit"] == "02b2c9f94baf671c39b0cde41f3d3683a1e6c313"
    assert (
        provenance["python"],
        provenance["pydantic"],
        provenance["pydantic_core"],
    ) == ("3.14.8", "2.13.5", "2.46.5")
    assert set(provenance["families"]) == {"attachment", "unknown", "checkpoint"}
    assert sum(p.stat().st_size for p in FIXTURES.iterdir()) < 2 * 1024 * 1024
    for name, expected in provenance["files"].items():
        raw = (FIXTURES / name).read_bytes()
        assert len(raw) == expected["size"]
        assert hashlib.sha256(raw).hexdigest() == expected["sha256"]


def test_attachment_both_retains_original_epoch_and_exact_owned_effects(legacy_loaded):
    loaded = legacy_loaded["attachment"]
    plan = loaded.saved.plan
    change = plan.proposal.changes[0]
    assert (change.original.data, change.current.data, change.incoming.data) == (
        b"\x00original",
        b"\x00authored",
        b"abc",
    )
    assert plan.proposal.generation == 2 and plan.ready
    assert [
        (a.decision_id, a.domain, a.choice, a.expected_generation) for a in plan.actions
    ] == [
        ("legacy:both", "attachment", "both", 1),
        ("legacy:consent", "storage", "accept", 1),
    ]
    approval = plan.approvals[0]
    assert (
        approval.decision_id == "legacy:both" and approval.provenance == "explicit_user"
    )
    assert approval.attachment_selection.generation == 1
    assert approval.attachment_selection.provenance == "explicit_user"
    assert plan.consents[0].decision_id == "legacy:consent"
    assert plan.consents[0].provenance == "explicit_user"
    assert plan.history.initial_preflight.consents[0].subjects == (ATTACHMENT_OWNER,)
    refresh = plan.history.events[-1]
    assert refresh.expected_generation == 1 and refresh.invalidated_keys == ()
    assert [
        (r.decision_id, r.subject_id, r.domain, r.origin_generation)
        for r in refresh.retained
    ] == [("legacy:both", ATTACHMENT_OWNER, "attachment", 1)]
    resumed = resume_review(loaded, plan.producer_facts, preflight=plan.preflight)
    assert resumed.status == "resumed" and resumed.code == "unchanged" and resumed.ready
    assert resumed.plan == plan and not loaded.ready
    effects = select_review_effects(resumed.plan)
    assert effects.status == "selected" and effects.generation == 2
    assert effect_rows(effects) == [
        ("Assets/data (incoming-ba7816bf).bin", ATTACHMENT_OWNER, b"abc"),
        ("Assets/data.bin", ATTACHMENT_OWNER, b"\x00authored"),
    ]
    assert effects.remove_paths == ()


def test_unknown_original_format_transition_cannot_invent_authority(legacy_loaded):
    loaded = legacy_loaded["unknown"]
    plan = loaded.saved.plan
    assert not plan.ready and plan.actions == () and plan.approvals == ()
    assert {r.domain for r in plan.requirements} == {"format"}
    original = plan.producer_facts.subjects[0].baseline
    assert original.status == "unknown" and original.content is None
    assert original.unavailable_digest == "older:unavailable"
    assert plan.facts.format_operation.established_baseline is None
    assert (
        plan.facts.baseline_identity.output_format,
        plan.facts.incoming_identity.output_format,
    ) == (6, 7)
    change = plan.proposal.changes[0]
    assert change.original is None and change.result is None
    assert change.current.data == b"authored\xff"
    assert change.incoming.data == b"target format 7\n"
    resumed = resume_review(loaded, plan.producer_facts, preflight=plan.preflight)
    assert resumed.status == "resumed" and resumed.code == "unchanged"
    assert not resumed.ready and resumed.plan == plan
    effects = select_review_effects(resumed.plan)
    assert effects.status == "refused" and effects.code == "review_not_ready"
    assert effects.files == () and effects.remove_paths == ()


@pytest.mark.parametrize(
    "kind",
    (
        "byte",
        "choice",
        "dependency",
        "retention",
        "consent",
        "effect_owner",
        "removal",
        "ambiguous_join",
        "duplicate",
    ),
)
def test_inline_authority_corruptions_refuse_at_load(kind):
    raw = wire("attachment")
    fields = json.loads(raw)
    plan = fields["plan"]
    expected = "invalid_review"
    if kind == "byte":
        plan["actions"][0]["attachment_candidate"]["outputs"][0]["content"]["data"] = (
            "AGF1dGhvcmVl"
        )
        expected = "invalid_record"
    elif kind == "choice":
        plan["actions"][0]["choice"] = "current"
    elif kind == "dependency":
        plan["actions"][0]["reviewed_assumptions"][0]["fingerprint"] = "0" * 64
    elif kind == "retention":
        plan["history"]["events"][-1]["retained"][0]["origin_generation"] = 2
    elif kind == "consent":
        plan["history"]["initial_preflight"]["consents"][0]["subjects"] = [
            "unreviewed:subject"
        ]
    elif kind == "effect_owner":
        plan["proposal"]["changes"][0]["subject_id"] = "different:owner"
    elif kind == "removal":
        # No serialized caller-supplied effect/removal list is authoritative.
        plan["remove_paths"] = ["Assets/data.bin"]
        expected = "invalid_record"
    elif kind == "ambiguous_join":
        plan["approvals"].append(copy.deepcopy(plan["approvals"][0]))
    else:
        raw = raw[:-1] + b',"schema_version":1}'
        expected = "invalid_record"
    offered = raw if kind == "duplicate" else json.dumps(fields).encode()
    result = load_review(offered)
    assert result.status == "refused" and result.code == expected
    assert result.loaded is None and not result.ready


def test_literal_encodings_are_old_projection_inputs_not_current_writer_goldens():
    vectors = json.loads((FIXTURES / "encoding-vectors.json").read_bytes())
    for vector in vectors["content"]:
        content = ExactContent(data=bytes.fromhex(vector["hex"]))
        assert content.model_dump_json().encode() == vector["inline"].encode()
        assert content.model_dump(mode="json")["data"] == vector["base64"]
        dumped = content.model_dump(mode="json")
        assert (
            json.dumps(dumped, sort_keys=True, separators=(",", ":"))
            == vector["Jc"]["preimage"]
        )
        assert json.dumps(dumped, sort_keys=True) == vector["Js"]["preimage"]
        assert json.dumps(dumped) == vector["Ju"]["preimage"]
    for vector in vectors["chunk_residues"]["vectors"]:
        raw = b"".join(bytes.fromhex(part) for part in vector["partitions_hex"])
        assert (
            ExactContent(data=raw).model_dump(mode="json")["data"] == vector["base64"]
        )
    referenced = ExactContent(
        data=b"\xfb\xff",
        reference=ImmutableContentReference(
            content_id="literal:fbff",
            sha256="db8fed54159afe40ace5b49d702259fd88c9c4009307181824487baab5c6bdea",
            size=2,
        ),
    )
    assert (
        json.dumps(
            referenced.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        == vectors["reference_present"]["Jc"]["preimage"]
    )
    ordered = vectors["ordering_and_escaping"]
    assert (
        json.dumps(
            ordered["input_insertion_order"], sort_keys=True, separators=(",", ":")
        )
        == ordered["Jc"]["preimage"]
    )
    assert (
        json.dumps(ordered["input_insertion_order"], sort_keys=True)
        == ordered["Js"]["preimage"]
    )
    assert json.dumps(ordered["input_insertion_order"]) == ordered["Ju"]["preimage"]
    assert (
        json.dumps(
            ordered["input_insertion_order"], ensure_ascii=False, separators=(",", ":")
        )
        == ordered["compact_utf8"]["preimage"]
    )
    # Frozen data includes omitted operation_reversal but explicit reference:null.
    subject = json.loads(wire("unknown"))["plan"]["facts"]["subjects"][0]
    assert "operation_reversal" not in subject
    assert subject["incoming"]["reference"] is None


def test_raw_identity_and_direct_json_candidate_proofs_have_distinct_literal_meanings(
    legacy_loaded,
):
    proofs = json.loads((FIXTURES / "proof-vectors.json").read_bytes())
    plan = legacy_loaded["attachment"].saved.plan
    assumptions = {a.key: a.fingerprint for a in plan.approvals[0].assumptions}
    for proof in proofs:
        assert assumptions[proof["key"]] == proof["sha256"]


@pytest.fixture(scope="module")
def checkpoint_case(legacy_loaded):
    # Public admission rejects nested repositories. The accepted #350 exception
    # requires exclusive OS-temp roots; preserve them for review, never clean up.
    container = Path(tempfile.mkdtemp(prefix="brz2obsidian-r350-"))
    case = capture_checkpoint(container, legacy_loaded["checkpoint"].saved.plan)
    evidence = (
        Path(__file__).resolve().parents[2] / "tmp/r350-vectors/native-roots.jsonl"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    with evidence.open("a", encoding="utf-8") as out:
        out.write(
            json.dumps(
                {
                    "root": str(container),
                    "files": sum(p.is_file() for p in container.rglob("*")),
                    "bytes": sum(
                        p.stat().st_size for p in container.rglob("*") if p.is_file()
                    ),
                }
            )
            + "\n"
        )
    return case


def test_refs_envelope_uses_actual_storage_and_baseline_only_role_closure(
    checkpoint_case,
):
    operations, vault, source, captured = checkpoint_case
    raw = git(vault, "cat-file", "blob", captured.commit + ":review.json")
    assert raw == (FIXTURES / "checkpoint.review.json").read_bytes()
    assert json.loads(raw)["schema_id"] == "brz2obsidian.saved-review-refs"
    manifest = json.loads(
        git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
    )
    old_manifest = json.loads((FIXTURES / "checkpoint.manifest.json").read_bytes())
    assert (
        manifest["review_content"]
        == old_manifest["review_content"]
        == [
            {
                "path": "ea9d37a10d727f12e46633eab31204cddfd0f49defd5ac488c14edb66c50d1f1",
                "mode": "100644",
                "size": 14,
                "sha256": "ea9d37a10d727f12e46633eab31204cddfd0f49defd5ac488c14edb66c50d1f1",
                "object_id": "db3a4c5da5500c1187d24072e79f775c1a3f5cf9",
            }
        ]
    )
    assert (
        git(
            vault,
            "cat-file",
            "blob",
            captured.commit
            + ":review-content/"
            + manifest["review_content"][0]["path"],
        )
        == b"baseline-only\n"
    )
    before = (
        (vault / "Notes/Opening.md").read_bytes(),
        (source / "Notes/Opening.md").read_bytes(),
    )
    observed = operations.inspect_history(vault)
    reopened = operations.read_checkpoint(vault)
    assert observed.status == "intact" and observed.admission.status == "supported"
    assert reopened.status == "valid" and reopened == observed.checkpoint
    loaded = reopened.review
    assert not loaded.ready and loaded.readiness == "revalidation_required"
    assert loaded.saved.plan.actions[0].decision_id == "legacy:keep-current"
    assert loaded.saved.plan.actions[0].expected_generation == 3
    assert effect_rows(loaded.historical_effects) == [
        ("Notes/Opening.md", NOTE_OWNER, b"authored current\r\n")
    ]
    assert loaded.historical_effects.remove_paths == ()
    assert before == (b"authored current\r\n", b"incoming next\n")
    assert before == (
        (vault / "Notes/Opening.md").read_bytes(),
        (source / "Notes/Opening.md").read_bytes(),
    )

    from brz2obsidian.contracts import ContentIdentity, OpaqueContent, ReviewPlan

    original = loaded.saved.plan
    assert original.facts.subjects[0].baseline.content.data == b"baseline-only\n"
    opaque = OpaqueContent(
        identity=ContentIdentity(
            content_id="sha256:ea9d37a10d727f12e46633eab31204cddfd0f49defd5ac488c14edb66c50d1f1:14",
            sha256="ea9d37a10d727f12e46633eab31204cddfd0f49defd5ac488c14edb66c50d1f1",
            size=14,
        )
    )
    fields = original.model_dump()
    fields["facts"]["subjects"][0]["baseline"]["content"] = opaque
    declared = ReviewPlan.model_validate(fields)
    assert declared.facts.subjects[0].baseline.content == opaque

    def retained_bytes(root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    retained = retained_bytes(vault), retained_bytes(source)
    refs = git(vault, "for-each-ref", "--format=%(refname) %(objectname)")
    head = git(vault, "rev-parse", "HEAD")
    refused = operations.capture_checkpoint(
        vault,
        source,
        vault_id="legacy-vault",
        import_id="legacy-import",
        identity=original.facts.incoming_identity,
        admission=operations.inspect_vault(vault),
        review=declared,
    )
    assert (refused.status, refused.code) == ("refused", "invalid_current_review")
    assert refused.commit is None and refused.ref is None
    assert not refused.objects_written and refused.object_storage == "not_started"
    assert not refused.history_retained and not refused.authored_files_changed
    assert (retained_bytes(vault), retained_bytes(source)) == retained
    assert git(vault, "for-each-ref", "--format=%(refname) %(objectname)") == refs
    assert git(vault, "rev-parse", "HEAD") == head
    assert git(vault, "cat-file", "blob", captured.commit + ":review.json") == raw


@pytest.mark.parametrize(
    "kind",
    ("duplicate", "missing_role", "inline_envelope", "marker_shape", "unowned_role"),
)
def test_git_ingress_refuses_corrupt_envelope_or_missing_owned_role(
    checkpoint_case, kind
):
    operations, vault, source, captured = checkpoint_case
    locator = vault / ".brz2obsidian/locator.json"
    original_locator = locator.read_bytes()
    original_head = git(vault, "rev-parse", "HEAD")
    original_index = (vault / ".git/index").read_bytes()
    raw = (FIXTURES / "checkpoint.review.json").read_bytes()
    try:
        if kind == "duplicate":
            retarget_checkpoint(
                vault, captured, review=raw[:-1] + b',"schema_version":1}'
            )
        elif kind == "missing_role":
            retarget_checkpoint(vault, captured, review_content=[])
        elif kind == "inline_envelope":
            retarget_checkpoint(vault, captured, review=wire("checkpoint"))
        else:
            envelope = json.loads(raw)
            content = envelope["record"]["plan"]["facts"]["subjects"][0]["baseline"][
                "content"
            ]
            marker = "__brz2obsidian_review_blob__"
            assert isinstance(content["data"][marker], str)
            manifest = json.loads(
                git(vault, "cat-file", "blob", captured.commit + ":manifest.json")
            )
            assert "0" * 64 not in {
                row["sha256"]
                for role in (
                    "source",
                    "vault",
                    "preimage",
                    "proposed",
                    "review_content",
                )
                for row in manifest[role]
            }
            content["data"] = (
                {"unexpected": "value"}
                if kind == "marker_shape"
                else {marker: "0" * 64}
            )
            retarget_checkpoint(vault, captured, review=json.dumps(envelope).encode())
        before = locator.read_bytes()
        before_ref = git(vault, "rev-parse", captured.ref)
        result = operations.read_checkpoint(vault)
        assert result.status == "refused" and result.review is None
        history = operations.inspect_history(vault)
        assert history.checkpoint is None or history.checkpoint.review is None
        assert locator.read_bytes() == before
        assert git(vault, "rev-parse", captured.ref) == before_ref
        assert (vault / "Notes/Opening.md").read_bytes() == b"authored current\r\n"
        assert (source / "Notes/Opening.md").read_bytes() == b"incoming next\n"
    finally:
        git(vault, "update-ref", captured.ref, captured.commit)
        locator.write_bytes(original_locator)
    assert locator.read_bytes() == original_locator
    assert git(vault, "rev-parse", captured.ref).decode().strip() == captured.commit
    assert git(vault, "rev-parse", "HEAD") == original_head
    assert (vault / ".git/index").read_bytes() == original_index
