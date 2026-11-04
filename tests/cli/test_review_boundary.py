"""Public CLI routing over controlled, typed review observations."""

import json

import pytest

from brz2obsidian.application.checkpoint_contracts import CheckpointResult
from brz2obsidian.application.source_payload_contracts import ReviewedSourceBinding
from brz2obsidian.application.update_contracts import (
    UpdateComparison,
    UpdatePreparation,
    UpdateResult,
    UpdateReviewPage,
)
from brz2obsidian.application.vault_update_contracts import VaultApplyResult
from brz2obsidian.cli import main
from brz2obsidian.contracts import ReconciliationInput
from brz2obsidian.core import (
    load_review,
    prepare_review,
    resolve_review,
    resume_review,
    save_review,
)
from tests.application.test_update_lifecycle_contracts import preparation
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_resolution import action, preflight, with_review_links


def prepared_for(kind, vault, payload_directory, *, conflict=True):
    facts = with_review_links(request(current=b"local\n") if conflict else request())
    raw_facts = facts.model_dump(mode="python")
    raw_facts["format_operation"]["kind"] = kind
    facts = ReconciliationInput.model_validate(raw_facts)
    plan = prepare_review(facts, preflight=preflight())
    raw = preparation().model_dump(mode="python")
    binding = raw["source_binding"]
    binding.update(
        proposal_id=plan.proposal.proposal_id,
        generation=plan.proposal.generation,
        incoming_identity=plan.facts.incoming_identity.model_dump(mode="python"),
    )
    raw.update(
        kind=kind,
        vault=str(vault),
        payload_directory=str(payload_directory),
        source_binding=ReviewedSourceBinding.model_validate(binding),
        review=plan.model_dump(mode="python"),
    )
    return UpdatePreparation.model_validate(raw)


@pytest.mark.parametrize(
    ("kind", "options", "route", "arguments", "keywords"),
    [
        (
            "source_update",
            ["--source", "incoming.brz"],
            "prepare_update",
            ("incoming.brz",),
            {},
        ),
        (
            "onboarding",
            [
                "--kind",
                "onboarding",
                "--source",
                "incoming.brz",
                "--original-source",
                "original.brz",
            ],
            "prepare_onboarding",
            ("incoming.brz",),
            {"original_source": "original.brz"},
        ),
        (
            "format_transition",
            ["--kind", "format-transition", "--source", "reference.brz"],
            "prepare_format_transition",
            ("reference.brz",),
            {},
        ),
        (
            "attachment_cleanup",
            ["--kind", "attachment-cleanup"],
            "prepare_attachment_cleanup",
            (),
            {},
        ),
    ],
)
def test_prepare_routes_save_same_preparation(
    tmp_path, monkeypatch, capsys, kind, options, route, arguments, keywords
):
    vault = tmp_path / "vault"
    vault.mkdir()
    sentinel = vault / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    payload_directory = tmp_path / "private-payload-marker"
    prepared = prepared_for(kind, vault, payload_directory)
    assert not prepared.review.ready
    locator = prepared.locator
    capture = CheckpointResult(
        schema_id="brz2obsidian.checkpoint-result",
        schema_version=1,
        status="captured",
        code="retained",
        commit="b" * 40,
        ref="refs/brz2obsidian/imports/" + "a" * 64 + "/checkpoints",
        history_retained=True,
        objects_written=True,
        object_storage="verified",
        authored_files_changed=False,
        message="Saved review.",
        locator=locator,
    )
    calls = []
    prepared_result = UpdateResult(
        status="prepared_review", code="prepared", kind=kind, preparation=prepared
    )
    assert prepared_result.preparation == prepared

    class Ports:
        def prepare_update(self, *args, **kwargs):
            return self.prepare("prepare_update", args, kwargs)

        def prepare_onboarding(self, *args, **kwargs):
            return self.prepare("prepare_onboarding", args, kwargs)

        def prepare_format_transition(self, *args, **kwargs):
            return self.prepare("prepare_format_transition", args, kwargs)

        def prepare_attachment_cleanup(self, *args, **kwargs):
            return self.prepare("prepare_attachment_cleanup", args, kwargs)

        def prepare(self, name, args, kwargs):
            calls.append((name, args, kwargs))
            return prepared_result

        def save_update(self, value):
            assert value is prepared_result.preparation
            calls.append(("save_update",))
            return UpdateResult(
                status="prepared_review",
                code="saved",
                kind=kind,
                preparation=value,
                operation_id=value.review.proposal.proposal_id,
                generation=value.review.proposal.generation,
                changes=1,
                unresolved=1,
                history_retained=True,
                checkpoint=locator,
                checkpoint_commit="b" * 40,
                capture=capture,
            )

        def apply_update(self, value):
            pytest.fail("prepare must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert main(["review", "prepare", str(vault), *options, "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert calls == [(route, (str(vault), *arguments), keywords), ("save_update",)]
    assert result["command"] == "prepare"
    assert result["kind"] == kind
    assert result["status"] == "prepared_review" and result["code"] == "saved"
    assert result["ready"] is False and result["unresolved"] == 1
    assert result["proposal_id"] == prepared.review.proposal.proposal_id
    assert result["generation"] == prepared.review.proposal.generation
    assert result["checkpoint"]["commit"] == "b" * 40
    assert result["checkpoint_commit"] == "b" * 40
    assert result["history_retained"] is True and result["publication"] == "not_started"
    assert result["capture"]["status"] == "captured"
    assert result["capture"]["authored_files_changed"] is False
    assert "preparation" not in result and str(payload_directory) not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_prepare_recovery_without_preparation_skips_save_and_apply(
    tmp_path, monkeypatch, capsys
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")

    class Ports:
        def prepare_update(self, vault, source):
            assert (vault, source) == (str(tmp_path), "incoming.brz")
            return UpdateResult(
                status="recovery_required",
                code="history_recovery_required",
                history_retained=True,
                next_actions=("inspect_history",),
                summary="History requires recovery.",
            )

        def save_update(self, value):
            pytest.fail("a missing preparation must not be saved")

        def apply_update(self, value):
            pytest.fail("a missing preparation must not be applied")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(["review", "prepare", str(tmp_path), "--source", "incoming.brz", "--json"])
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["command"] == "prepare"
    assert result["status"] == "recovery_required"
    assert result["code"] == "history_recovery_required"
    assert result["ready"] is False and result["history_retained"] is True
    assert result["next_actions"] == ["inspect_history"]
    assert result["capture"] is None and result["publication"] == "not_started"
    assert "preparation" not in result
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_prepare_failed_save_reports_operational_failure(tmp_path, monkeypatch, capsys):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    payload_directory = tmp_path / "private-payload-marker"
    prepared = prepared_for("source_update", tmp_path, payload_directory)
    prepared_result = UpdateResult(
        status="prepared_review", code="prepared", preparation=prepared
    )
    failed_capture = CheckpointResult(
        schema_id="brz2obsidian.checkpoint-result",
        schema_version=1,
        status="failed",
        code="capture_failed",
        commit=None,
        ref=None,
        history_retained=True,
        objects_written=False,
        object_storage="possible",
        authored_files_changed=False,
        message="Capture failed.",
    )
    saves = []

    class Ports:
        def prepare_update(self, vault, source):
            assert (vault, source) == (str(tmp_path), "incoming.brz")
            return prepared_result

        def save_update(self, value):
            assert value is prepared_result.preparation
            saves.append(value)
            return UpdateResult(
                status="failed",
                code="capture_failed",
                preparation=value,
                operation_id=value.review.proposal.proposal_id,
                generation=value.review.proposal.generation,
                capture=failed_capture,
                history_retained=True,
                publication="not_started",
                summary="Capture failed.",
            )

        def apply_update(self, value):
            pytest.fail("failed save must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(["review", "prepare", str(tmp_path), "--source", "incoming.brz", "--json"])
        == 1
    )
    captured = capsys.readouterr()
    assert captured.err == "" and len(saves) == 1
    result = json.loads(captured.out)
    assert result["command"] == "prepare"
    assert result["status"] == "failed" and result["code"] == "capture_failed"
    assert result["ready"] is False and result["publication"] == "not_started"
    assert result["history_retained"] is True
    assert result["capture"]["status"] == "failed"
    assert result["capture"]["object_storage"] == "possible"
    assert result["capture"]["authored_files_changed"] is False
    assert "preparation" not in result and str(payload_directory) not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_inspect_matching_review_exposes_bounded_metadata(
    tmp_path, monkeypatch, capsys
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    payload_directory = tmp_path / "private-payload-marker"
    historical = prepared_for("source_update", tmp_path, payload_directory)
    saved = save_review(historical.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded" and not loaded.ready
    current = prepared_for("source_update", tmp_path, payload_directory)
    resumed = resume_review(
        loaded.loaded, current.review.facts, preflight=current.review.preflight
    )
    assert resumed.status == "resumed" and resumed.plan == current.review
    proposal = current.review.proposal
    assert len(proposal.changes) == 1
    change = proposal.changes[0]
    comparison = UpdateComparison(
        change_id=change.change_id,
        item_id="entry:opening",
        facet="content",
        current_path="Notes/Opening.md",
        incoming_path="Notes/Opening.md",
        disposition="conflict",
        original=None,
        current=None,
        incoming=None,
        result=None,
        offset=0,
        next_byte_offset=None,
        omitted=True,
    )
    page = UpdateReviewPage(
        status="available",
        code="available",
        proposal_id=proposal.proposal_id,
        generation=proposal.generation,
        total=1,
        offset=0,
        next_offset=None,
        items=(comparison,),
        omitted=True,
    )
    load_result = UpdateResult(
        status="prepared_review",
        code="loaded",
        loaded=loaded.loaded,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=historical.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    current_result = UpdateResult(
        status="prepared_review",
        code="resumed",
        preparation=current,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        changes=1,
        unresolved=1,
        checkpoint=current.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    calls = []

    class Ports:
        def load_update(self, vault):
            calls.append(("load", vault))
            return load_result

        def resume_update(self, vault):
            calls.append(("resume", vault))
            return current_result

        def inspect_update_review(self, value, **kwargs):
            assert value is current_result.preparation
            calls.append(("page", kwargs))
            return page

        def save_update(self, value):
            pytest.fail("inspection must not save")

        def apply_update(self, value):
            pytest.fail("inspection must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(
            [
                "review",
                "inspect",
                str(tmp_path),
                "--proposal-id",
                proposal.proposal_id,
                "--generation",
                str(proposal.generation),
                "--checkpoint",
                "b" * 40,
                "--byte-limit",
                "0",
                "--json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert calls == [
        ("load", str(tmp_path)),
        ("resume", str(tmp_path)),
        (
            "page",
            {
                "proposal_id": proposal.proposal_id,
                "generation": proposal.generation,
                "offset": 0,
                "limit": 100,
                "byte_offset": 0,
                "byte_limit": 0,
            },
        ),
    ]
    assert result["command"] == "inspect" and result["status"] == "prepared_review"
    assert result["proposal_id"] == proposal.proposal_id and result["generation"] == 1
    assert result["checkpoint"]["commit"] == "b" * 40
    assert result["ready"] is False and result["changes"] == result["unresolved"] == 1
    assert result["page"]["status"] == "available" and result["page"]["total"] == 1
    assert result["page"]["offset"] == 0 and result["page"]["next_offset"] is None
    assert result["page"]["omitted"] is True
    item = result["page"]["items"][0]
    assert item["current_path"] == "Notes/Opening.md" and item["omitted"] is True
    assert all(
        item[field] is None for field in ("original", "current", "incoming", "result")
    )
    assert result["choices_total"] == 1 and result["choices_next_offset"] is None
    assert len(result["choices"]) == 1 and result["choices"][0]["domain"] == "text"
    assert result["choices"][0]["disclosure"] == "Current file: Notes/Opening.md"
    assert result["omissions"] == ["attachment_alternative_outputs"]
    assert "preparation" not in result and "loaded" not in result
    assert str(payload_directory) not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


@pytest.mark.parametrize("command", ["inspect", "apply"])
@pytest.mark.parametrize(
    ("wrong_selector", "wrong_value"),
    [
        ("--proposal-id", "review:other"),
        ("--generation", "2"),
        ("--checkpoint", "c" * 40),
    ],
)
def test_identity_mismatch_refuses_before_current_review(
    tmp_path, monkeypatch, capsys, command, wrong_selector, wrong_value
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    prepared = prepared_for(
        "source_update", tmp_path, tmp_path / "private-payload-marker"
    )
    saved = save_review(prepared.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded" and not loaded.ready
    proposal = prepared.review.proposal
    load_result = UpdateResult(
        status="prepared_review",
        code="loaded",
        loaded=loaded.loaded,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=prepared.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    reads = []

    class Ports:
        def load_update(self, vault):
            reads.append(vault)
            return load_result

        def resume_update(self, vault):
            pytest.fail("mismatched caller identity must not resume")

        def inspect_update_review(self, *args, **kwargs):
            pytest.fail("mismatched caller identity must not inspect a page")

        def apply_update(self, value):
            pytest.fail("mismatched caller identity must not apply")

    selectors = {
        "--proposal-id": proposal.proposal_id,
        "--generation": str(proposal.generation),
        "--checkpoint": "b" * 40,
    }
    selectors[wrong_selector] = wrong_value
    options = [argument for pair in selectors.items() for argument in pair]
    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert main(["review", command, str(tmp_path), *options, "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == "" and reads == [str(tmp_path)]
    result = json.loads(captured.out)
    assert result["command"] == command
    assert result["status"] == "stale_review"
    assert result["code"] == "review_identity_changed"
    assert result["ready"] is False
    assert result["next_actions"] == ["inspect_saved_review"]
    assert result["page"] is None and result["choices"] == []
    assert "loaded" not in result and "preparation" not in result
    assert "private-payload-marker" not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


@pytest.mark.parametrize("command", ["inspect", "apply"])
def test_changed_current_checkpoint_refuses_before_page_or_apply(
    tmp_path, monkeypatch, capsys, command
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    historical = prepared_for(
        "source_update", tmp_path, tmp_path / "private-payload-marker"
    )
    saved = save_review(historical.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded" and not loaded.ready
    raw_current = prepared_for(
        "source_update", tmp_path, tmp_path / "private-payload-marker"
    ).model_dump(mode="python")
    raw_current["locator"]["commit"] = "c" * 40
    current = UpdatePreparation.model_validate(raw_current)
    proposal = current.review.proposal
    load_result = UpdateResult(
        status="prepared_review",
        code="loaded",
        loaded=loaded.loaded,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=historical.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    current_result = UpdateResult(
        status="prepared_review",
        code="resumed",
        preparation=current,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=current.locator,
        checkpoint_commit="c" * 40,
        history_retained=True,
    )
    reads = []

    class Ports:
        def load_update(self, vault):
            reads.append(("load", vault))
            return load_result

        def resume_update(self, vault):
            reads.append(("resume", vault))
            return current_result

        def inspect_update_review(self, *args, **kwargs):
            pytest.fail("changed current checkpoint must not expose a page")

        def apply_update(self, value):
            pytest.fail("changed current checkpoint must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(
            [
                "review",
                command,
                str(tmp_path),
                "--proposal-id",
                proposal.proposal_id,
                "--generation",
                str(proposal.generation),
                "--checkpoint",
                "b" * 40,
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    assert reads == [("load", str(tmp_path)), ("resume", str(tmp_path))]
    result = json.loads(captured.out)
    assert result["command"] == command
    assert result["status"] == "stale_review" and result["code"] == (
        "review_identity_changed"
    )
    assert result["ready"] is False and result["next_actions"] == ["review_update"]
    assert result["checkpoint"]["commit"] == "c" * 40
    assert result["page"] is None and result["choices"] == []
    assert "preparation" not in result and "private-payload-marker" not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


def observations(tmp_path):
    prepared = prepared_for(
        "source_update", tmp_path, tmp_path / "private-payload-marker"
    )
    saved = save_review(prepared.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded" and not loaded.ready
    proposal = prepared.review.proposal
    historical = UpdateResult(
        status="prepared_review",
        code="loaded",
        loaded=loaded.loaded,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=prepared.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    current = UpdateResult(
        status="prepared_review",
        code="resumed",
        preparation=prepared,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=prepared.locator,
        checkpoint_commit="b" * 40,
        changes=1,
        unresolved=1,
        history_retained=True,
    )
    return prepared, historical, current


@pytest.mark.parametrize(
    ("command", "options"),
    [
        ("inspect", ["--offset", "-1"]),
        ("inspect", ["--byte-limit", "65537"]),
        (
            "apply",
            [
                "--proposal-id",
                "review:one",
                "--generation",
                "0",
                "--checkpoint",
                "b" * 40,
            ],
        ),
    ],
)
def test_invalid_bounds_and_generation_refuse_before_read(
    tmp_path, monkeypatch, capsys, command, options
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")

    class Ports:
        def load_update(self, vault):
            pytest.fail("invalid arguments must not read a saved review")

        def resume_update(self, vault):
            pytest.fail("invalid arguments must not resume")

        def inspect_update_review(self, *args, **kwargs):
            pytest.fail("invalid arguments must not inspect a page")

        def apply_update(self, value):
            pytest.fail("invalid arguments must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert main(["review", command, str(tmp_path), *options, "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["command"] == command
    assert result["status"] == "refused" and result["code"] == (
        "invalid_review_arguments"
    )
    assert result["page"] is None and result["choices"] == []
    assert sentinel.read_bytes() == b"owned sentinel\n"


@pytest.mark.parametrize("missing", ["load", "resume"])
def test_inspect_projects_missing_review_observation(
    tmp_path, monkeypatch, capsys, missing
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    _, historical, _ = observations(tmp_path)
    unavailable = UpdateResult(
        status="recovery_required",
        code="review_unavailable",
        history_retained=True,
        next_actions=("inspect_history",),
        summary="Review is unavailable.",
    )
    calls = []

    class Ports:
        def load_update(self, vault):
            calls.append("load")
            return unavailable if missing == "load" else historical

        def resume_update(self, vault):
            if missing == "load":
                pytest.fail("missing load must not resume")
            calls.append("resume")
            return unavailable

        def inspect_update_review(self, *args, **kwargs):
            pytest.fail("missing review must not expose a page")

        def apply_update(self, value):
            pytest.fail("missing review must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert main(["review", "inspect", str(tmp_path), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert calls == (["load"] if missing == "load" else ["load", "resume"])
    result = json.loads(captured.out)
    assert result["command"] == "inspect" and result["status"] == "recovery_required"
    assert result["code"] == "review_unavailable" and result["history_retained"] is True
    assert result["next_actions"] == ["inspect_history"]
    assert result["page"] is None and result["choices"] == []
    assert "preparation" not in result and "loaded" not in result
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_inspect_refused_page_does_not_invent_choices(tmp_path, monkeypatch, capsys):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    prepared, historical, current = observations(tmp_path)
    proposal = prepared.review.proposal
    refused_page = UpdateReviewPage(
        status="refused",
        code="page_unavailable",
        proposal_id=proposal.proposal_id,
        generation=proposal.generation,
        total=0,
        offset=0,
        next_offset=None,
        items=(),
        omitted=False,
    )

    class Ports:
        def load_update(self, vault):
            return historical

        def resume_update(self, vault):
            return current

        def inspect_update_review(self, value, **kwargs):
            assert value is current.preparation
            return refused_page

        def apply_update(self, value):
            pytest.fail("inspection must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(["review", "inspect", str(tmp_path), "--byte-limit", "0", "--json"]) == 2
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["status"] == "refused" and result["code"] == "page_unavailable"
    assert result["next_actions"] == ["inspect_saved_review"]
    assert result["page"] is None and result["choices"] == []
    assert result["choices_total"] is None and result["choices_next_offset"] is None
    assert "preparation" not in result and "private-payload-marker" not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_apply_unresolved_current_review_requires_resolution(
    tmp_path, monkeypatch, capsys
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    prepared, historical, current = observations(tmp_path)
    proposal = prepared.review.proposal
    assert not current.ready and not current.preparation.review.ready

    class Ports:
        def load_update(self, vault):
            return historical

        def resume_update(self, vault):
            return current

        def apply_update(self, value):
            pytest.fail("unresolved review must not apply")

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(
            [
                "review",
                "apply",
                str(tmp_path),
                "--proposal-id",
                proposal.proposal_id,
                "--generation",
                str(proposal.generation),
                "--checkpoint",
                "b" * 40,
                "--json",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["command"] == "apply" and result["status"] == "unresolved"
    assert result["code"] == "review_not_ready" and result["ready"] is False
    assert result["next_actions"] == ["resolve_update", "save_update"]
    assert result["publication"] == "not_started" and result["operation"] is None
    assert "preparation" not in result and "private-payload-marker" not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"


def test_apply_exact_ready_review_dispatches_controlled_no_content_outcome(
    tmp_path, monkeypatch, capsys
):
    sentinel = tmp_path / "note.md"
    sentinel.write_bytes(b"owned sentinel\n")
    prepared = prepared_for(
        "source_update", tmp_path, tmp_path / "private-payload-marker", conflict=False
    )
    resolved = resolve_review(prepared.review, action(prepared.review))
    assert resolved.status == "accepted" and resolved.plan.ready
    raw = prepared.model_dump(mode="python")
    raw["review"] = resolved.plan.model_dump(mode="python")
    ready = UpdatePreparation.model_validate(raw)
    saved = save_review(ready.review)
    assert saved.status == "saved"
    loaded = load_review(saved.record)
    assert loaded.status == "loaded" and not loaded.ready
    proposal = ready.review.proposal
    historical = UpdateResult(
        status="prepared_review",
        code="loaded",
        loaded=loaded.loaded,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=ready.locator,
        checkpoint_commit="b" * 40,
        history_retained=True,
    )
    current = UpdateResult(
        status="prepared_review",
        code="resumed",
        preparation=ready,
        ready=True,
        operation_id=proposal.proposal_id,
        generation=proposal.generation,
        checkpoint=ready.locator,
        checkpoint_commit="b" * 40,
        changes=1,
        unresolved=0,
        history_retained=True,
    )
    outcome = VaultApplyResult(
        schema_id="brz2obsidian.vault-apply-result",
        schema_version=1,
        status="no_content_change",
        code="no_content_change",
        operation_id="1" * 32,
        kind="apply",
        direction="finish",
        review_generation=1,
        generation=1,
        phase="terminal",
        publication="complete",
        history="terminal",
        planned_files=0,
        published_files=0,
        authored_files_changed=False,
        checkpoint_commit="b" * 40,
        intent_commit="d" * 40,
        result_commit="e" * 40,
        receipt_commit="f" * 40,
        recovery_required=False,
        elapsed_ms=0,
        message="No content change.",
    )
    calls = []

    class Ports:
        def load_update(self, vault):
            return historical

        def resume_update(self, vault):
            return current

        def apply_update(self, value):
            assert value is current.preparation
            calls.append("apply")
            return UpdateResult(
                status="no_content_change",
                code="no_content_change",
                application=outcome,
                publication="complete",
                history_retained=True,
            )

    monkeypatch.setattr("brz2obsidian.cli_review.Operations", Ports)
    assert (
        main(
            [
                "review",
                "apply",
                str(tmp_path),
                "--proposal-id",
                proposal.proposal_id,
                "--generation",
                str(proposal.generation),
                "--checkpoint",
                "b" * 40,
                "--json",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    assert captured.err == "" and calls == ["apply"]
    result = json.loads(captured.out)
    assert result["command"] == "apply" and result["status"] == "no_content_change"
    assert result["code"] == "no_content_change" and result["publication"] == "complete"
    assert result["proposal_id"] == proposal.proposal_id and result["generation"] == 1
    assert result["operation"]["status"] == "no_content_change"
    assert result["operation"]["published_files"] == 0
    assert result["operation"]["authored_files_changed"] is False
    assert result["operation"]["history"] == "terminal"
    assert "preparation" not in result and "private-payload-marker" not in captured.out
    assert sentinel.read_bytes() == b"owned sentinel\n"
