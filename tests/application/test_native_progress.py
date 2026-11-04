"""Actual observed native publication; transport progress never grants authority."""

import json
import time
from threading import Event, Thread

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.review_choices import attachment_reference_page
from brz2obsidian.publication.vault_replace import move_file
from tests.application.test_attachment_cleanup_history import (
    completed_native_ownership_case,
)
from tests.application.test_attachment_cleanup_lifecycle import user_git


def test_native_progress_observes_real_publication_and_existing_file_stop(tmp_path):
    started = time.monotonic()

    def phase(name, **facts):
        (tmp_path / "phase.json").write_text(
            json.dumps(
                {"phase": name, "elapsed_seconds": time.monotonic() - started, **facts}
            ),
            encoding="utf-8",
        )

    phase("native_seed")
    manual = (
        b"Before [[Assets/remove.bin|old]] after.\r\n`[[Assets/remove.bin|code]]`\r\n"
    )
    vault, source, original, _, _, user_before = completed_native_ownership_case(
        manual=manual
    )
    phase("cleanup_preparation", vault=str(vault))
    entered, release, stop, finished = Event(), Event(), Event(), Event()
    observations, results, errors = [], [], []

    class ActualFiles:
        def move(self, stage, target, *, replace):
            move_file(stage, target, replace=replace)

        def remove(self, target, destination):
            assert target == vault / "Assets/remove.bin"
            destination.parent.mkdir(parents=True, exist_ok=True)
            move_file(target, destination, replace=False)
            entered.set()
            assert release.wait(10), "Owned atomic file-return barrier exhausted"

        def directory(self, stage, target):
            move_file(stage, target, replace=False)

    operations = Operations(vault_executor=ActualFiles())
    opened = operations.prepare_attachment_cleanup(vault)
    assert opened.preparation is not None, opened.code
    preparation = opened.preparation
    from brz2obsidian.application.review_offers import choice_offers

    offers = choice_offers(preparation)
    assert len(offers) == 1 and "remove" in offers[0].choices
    offer = offers[0]
    references, count, following = attachment_reference_page(
        preparation, offer.requirement_id
    )
    assert count == 1 and following is None
    selected = operations.resolve_update_choice(
        preparation,
        requirement_id=offer.requirement_id,
        choice="remove",
        assumptions_digest=offer.assumptions_digest,
        references=tuple(
            {"reference_id": row.reference_id, "choice": "drop"} for row in references
        ),
    )
    assert selected.ready, (selected.code, selected.preparation.review.blockers)
    phase("ready", vault=str(vault))
    (vault.parent / "285-progress-ready.json").write_text(
        selected.preparation.model_dump_json(), encoding="utf-8"
    )

    def apply():
        try:
            results.append(
                operations.apply_update(
                    selected.preparation,
                    cancel=stop.is_set,
                    progress=observations.append,
                )
            )
        except BaseException as error:  # noqa: BLE001 -- preserve any publisher thread failure for the test assertion.
            errors.append(error)
        finally:
            finished.set()

    running = Thread(target=apply, daemon=True)
    phase("native_apply", vault=str(vault))
    running.start()
    deadline = time.monotonic() + 120
    try:
        while not entered.wait(0.02):
            assert time.monotonic() < deadline, (
                "Owned native publication diagnostic exhausted"
            )
            if finished.is_set():
                assert not errors, errors
                raise AssertionError(
                    "Native apply ended before actual file publication"
                )
        assert not (vault / "Assets/remove.bin").exists()
        assert (vault / "Manual.md").read_bytes() == manual
        stop.set()
        assert running.is_alive() and not finished.is_set()
        release.set()
        running.join(90)
        assert not running.is_alive() and not errors
    finally:
        stop.set()
        release.set()
        running.join(90)
    assert len(results) == 1
    result = results[0]
    assert result.status == "recovery_required" and result.publication == "partial"
    native = result.application
    phase(
        "stopped",
        vault=str(vault),
        status=native.status,
        code=native.code,
        operation_id=native.operation_id,
    )
    assert native.status == "cancelled" and native.code == "cancelled_after_intent"
    assert native.published_files == 1 and native.planned_files == 2
    assert native.checkpoint_commit and native.intent_commit and native.stop_commit
    assert native.history == "intent" and native.recovery_required
    published = [
        row
        for row in observations
        if row.phase == "publication" and row.completed_units == 1
    ]
    assert published and all(
        row.total_units == 2 and row.unit == "files" for row in published
    )
    assert (
        published[-1].operation_id == native.operation_id
        and published[-1].intent_commit == native.intent_commit
    )
    assert any(row.phase == "snapshot_preparation" for row in observations)
    assert native.result_commit is None and native.receipt_commit is None
    assert (vault / "Manual.md").read_bytes() == manual
    assert all(
        (vault / path).read_bytes() == raw
        for path, raw in original.items()
        if path != "Assets/remove.bin"
    )
    assert {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    } == original
    assert user_git(vault) == user_before
    restarted = Operations().inspect_update_status(vault)
    assert restarted.recovery_required and restarted.operation_id == native.operation_id
    assert (
        restarted.intent_commit == native.intent_commit
        and restarted.generation == native.generation
    )
    assert Operations().inspect_history_workflow(vault).next_actions == (
        "review_recovery",
    )
