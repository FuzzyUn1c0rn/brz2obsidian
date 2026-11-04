"""Canonical review rows remain reachable and scoped choices use their owner."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QAbstractItemView, QApplication, QComboBox, QPlainTextEdit

from brz2obsidian.application.operations import Operations
from brz2obsidian.application.update_context_contracts import (
    UpdateChoiceOffer,
    UpdateConfigurationOffer,
    UpdateContextBinding,
    UpdateContextResult,
)
from brz2obsidian.core import prepare_review, resolve_review, select_review_effects
from tests.application.test_history_workflow import (
    absent_history,
    operation_state,
    ready_native_recovery,
)
from tests.gui.test_conversion_window import until, window_text
from tests.gui.update_projection_fixture import (
    ProjectedReviewTransport,
    ReviewControls,
    ReviewDialogs,
)
from tests.gui.update_worker_fixture import ReviewWorkerTransport
from tests.reconciliation.test_resolution import preflight
from tests.reconciliation.test_reversal_absence import reversal_facts

pytestmark = pytest.mark.gui


def test_actual_reversal_row_reaches_editor_and_commits_small_bytes_through_history_worker(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    personal = vault / "Personal.md"
    personal.write_bytes(b"Personal bytes stay unchanged\r\n")
    facts = reversal_facts(current=b"Later writing.\r\n")
    subject = facts.subjects[0]
    proof = subject.operation_reversal.model_copy(
        update={"operation_id": "1" * 32, "operation_generation": 7}
    )
    facts = facts.model_copy(
        update={
            "generation": 3,
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert plan.proposal.changes[0].disposition == "operation_reversal"
    assert (
        plan.requirements[0].domain == "reversal"
        and "edited" in plan.requirements[0].choices
    )
    native = ready_native_recovery(direction="restore").native.model_copy(
        update={"review": plan}
    )
    edited = "# Retained note\nLater writing.\n"
    selected = []

    class NativePorts(Operations):
        # Controlled outer storage observations; Core choices and worker leases are real.
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return operation_state("incomplete").model_copy(
                update={"direction": "restore"}
            )

        def prepare_recovery(self, path, *, direction=None):
            assert direction in (None, "restore")
            return (
                native.model_copy(update={"direction": None, "review": None})
                if direction is None
                else native
            )

        def resolve_recovery(self, path, previous, action):
            transition = resolve_review(previous.review, action)
            assert transition.status == "accepted", transition.code
            effects = select_review_effects(transition.plan)
            assert effects.status == "selected" and effects.remove_paths == ()
            assert [(row.path, row.content.data) for row in effects.files] == [
                ("Notes/Opening.md", edited.encode())
            ]
            selected.append(action)
            return previous.model_copy(
                update={"review": transition.plan, "code": "recovery_choice_recorded"}
            )

        def execute_recovery(self, *args, **kwargs):
            raise AssertionError("Editor review cannot publish automatically")

    transport = ReviewWorkerTransport(NativePorts())
    window = MainWindow(
        supervisor=transport, dialogs=ReviewDialogs(tmp_path / "unused.brz", vault)
    )
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        controls.click("Inspect history and recovery")
        controls.click("Review interrupted update")
        controls.click("Review restore direction")
        until(
            app,
            lambda: (
                window.workbench.snapshot.binding is not None
                and window.workbench.snapshot.binding.proposal_id is not None
                and not window.workbench.busy
            ),
        )
        controls.select("Other choices")
        until(
            app,
            lambda: (
                "Reversal choice 1" in window_text(window) and not window.workbench.busy
            ),
        )
        assert controls.button("Review references for reversal choice 1") is None
        queue = next(
            w
            for w in window.findChildren(QAbstractItemView)
            if w.accessibleName() == "Review queue"
        )
        assert any(
            queue.model().index(i, 0).data() == "All changes"
            for i in range(queue.model().rowCount())
        ), (
            "Canonical reversal comparisons must remain reachable through the review queue"
        )
        controls.select("All changes")
        controls.click("Edit result for Notes/Opening.md")
        editor = next(
            w
            for w in window.findChildren(QPlainTextEdit)
            if w.accessibleName() == "Edited result for Notes/Opening.md"
        )
        assert editor.toPlainText() == "Later writing.\n"
        editor.setPlainText(edited)
        controls.click("Use edited result")
        until(
            app,
            lambda: (
                selected
                and window.runner.session.update_snapshot.ready
                and not window.workbench.busy
            ),
        )
        assert (
            len(selected) == 1
            and selected[0].domain == "reversal"
            and selected[0].choice == "edited"
        )
        writes = [row for row in transport.commands if row.command == "write_edit"]
        assert (
            len(writes) == 1
            and writes[0].offset == 0
            and writes[0].data == edited.encode()
        )
        assert sum(row.command == "choose_history" for row in transport.commands) == 1
        assert not any(row.command == "execute_history" for row in transport.commands)
        assert personal.read_bytes() == b"Personal bytes stay unchanged\r\n" and list(
            vault.iterdir()
        ) == [personal]
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_actual_binary_reversal_reaches_reference_choices_and_keeps_owned_bytes(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow
    from tests.reconciliation.test_attachments import linked_attachment_request
    from tests.reconciliation.test_reversal_absence import single_proof

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    literal = b"Before [[Assets/data.bin|Keep first]] and [[Assets/data.bin|Redirect second]] after.\r\n`[[Assets/data.bin|code]]`"
    personal = vault / "Manual.md"
    personal.write_bytes(literal)
    facts = linked_attachment_request(raw=literal)
    subject = facts.subjects[0]
    proof = single_proof(facts, produced=None, target=subject.incoming).model_copy(
        update={"operation_id": "1" * 32, "operation_generation": 7}
    )
    facts = facts.model_copy(
        update={
            "generation": 3,
            "subjects": (subject.model_copy(update={"operation_reversal": proof}),),
        }
    )
    plan = prepare_review(facts, preflight=preflight())
    assert [(row.domain, row.choices) for row in plan.requirements] == [
        ("reversal", ("current", "reverse"))
    ]
    native = ready_native_recovery(direction="restore").native.model_copy(
        update={"review": plan}
    )
    selected = []

    class NativePorts(Operations):
        def inspect_history(self, path, **kwargs):
            return absent_history()

        def inspect_update_status(self, path):
            return operation_state("incomplete").model_copy(
                update={"direction": "restore"}
            )

        def prepare_recovery(self, path, *, direction=None):
            assert direction in (None, "restore")
            return (
                native.model_copy(update={"direction": None, "review": None})
                if direction is None
                else native
            )

        def resolve_recovery(self, path, previous, action):
            transition = resolve_review(previous.review, action)
            assert transition.status == "accepted", transition.code
            effects = select_review_effects(transition.plan)
            assert effects.status == "selected" and effects.remove_paths == ()
            files = {row.path: row.content.data for row in effects.files}
            assert (
                files["Assets/data.bin"] == b"abc"
                and files.get("Notes/Owner.md", literal) == literal
            )
            assert (
                action.choice == "reverse"
                and action.attachment_selection.choice == "incoming"
            )
            assert len(action.attachment_selection.link_choices) == 2
            assert [
                (row.source_path, row.content.data)
                for row in action.attachment_candidate.documents
            ] == [("Notes/Owner.md", literal)]
            selected.append(action)
            return previous.model_copy(
                update={"review": transition.plan, "code": "recovery_choice_recorded"}
            )

        def execute_recovery(self, *args, **kwargs):
            raise AssertionError("Reference review cannot publish automatically")

    transport = ReviewWorkerTransport(NativePorts())
    window = MainWindow(
        supervisor=transport, dialogs=ReviewDialogs(tmp_path / "unused.brz", vault)
    )
    window.show()
    controls = ReviewControls(window, app)
    try:
        controls.click("Choose update vault")
        controls.click("Inspect history and recovery")
        controls.click("Review interrupted update")
        controls.click("Review restore direction")
        until(
            app,
            lambda: (
                window.workbench.snapshot.binding is not None
                and window.workbench.snapshot.binding.proposal_id is not None
                and not window.workbench.busy
            ),
        )
        controls.select("Other choices")
        until(
            app,
            lambda: (
                "Reversal choice 1" in window_text(window) and not window.workbench.busy
            ),
        )
        reference_button = controls.button("Review references for reversal choice 1")
        assert reference_button is not None, (
            "Binary history choices must expose the shared reference review"
        )
        controls.click("Review references for reversal choice 1")
        until(
            app,
            lambda: (
                len(
                    [
                        row
                        for row in window.findChildren(QComboBox)
                        if row.isVisible()
                        and row.accessibleName().startswith("Reference target for ")
                    ]
                )
                == 2
            ),
        )
        for combo in (
            row
            for row in window.findChildren(QComboBox)
            if row.isVisible()
            and row.accessibleName().startswith("Reference target for ")
        ):
            assert combo.findData("use_incoming") >= 0
            combo.setCurrentIndex(combo.findData("use_incoming"))
        controls.click("Stage reference choices")
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.draft_pending
                and not window.workbench.busy
            ),
        )
        assert not window.runner.session.update_snapshot.ready
        controls.click("Reverse reviewed change for reversal choice 1")
        until(
            app,
            lambda: (
                selected
                and window.runner.session.update_snapshot.ready
                and not window.workbench.busy
            ),
        )
        staged = [
            row for row in transport.commands if row.command == "stage_references"
        ]
        chosen = [row for row in transport.commands if row.command == "choose_history"]
        assert len(staged) == len(chosen) == 1 and len(staged[0].choices) == 2
        assert len({row.reference_id for row in staged[0].choices}) == 2
        assert {row.choice for row in staged[0].choices} == {"use_incoming"}
        assert chosen[0].binding.revision > staged[0].binding.revision
        assert not any(row.command == "execute_history" for row in transport.commands)
        assert personal.read_bytes() == literal and list(vault.iterdir()) == [personal]
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_format_configuration_uses_supplied_group_scope_and_keeps_other_choice_unresolved(
    tmp_path,
):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Source.brz"
    source.write_bytes(b"source")

    class Projection:
        binding = None
        config = UpdateConfigurationOffer(
            group_id="a" * 64,
            member_count=2,
            choices=("current", "incoming"),
            selected=None,
        )

        def __call__(self, actual, callbacks):
            args = actual.arguments
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()),
                    selection_id=args.selection_id,
                    vault=str(vault),
                    revision=1,
                    association_id="b" * 64,
                    checkpoint_commit="b" * 40,
                    checkpoint_generation=1,
                    proposal_id="format-review",
                    generation=1,
                )
                return self.review()
            assert args.binding == self.binding
            if args.command == "page":
                return UpdateContextResult(
                    status="available",
                    code="available",
                    kind="format_transition",
                    binding=self.binding,
                    configuration=self.config,
                )
            if args.command == "choices":
                return UpdateContextResult(
                    status="available",
                    code="available",
                    kind="format_transition",
                    binding=self.binding,
                    total_choices=2,
                    offers=(
                        UpdateChoiceOffer(
                            requirement_id="config-row",
                            change_id="config-row",
                            domain="configuration",
                            choices=("current", "incoming"),
                            assumptions_digest="c" * 64,
                            selected=self.config.selected,
                            decision_id="config-decision"
                            if self.config.selected
                            else None,
                        ),
                        UpdateChoiceOffer(
                            requirement_id="text-row",
                            change_id="text-row",
                            domain="text",
                            choices=("current", "incoming"),
                            assumptions_digest="d" * 64,
                        ),
                    ),
                )
            assert args.command == "choose_configuration", (
                "Individual configuration actions are not admitted by the format operation"
            )
            assert (args.group_id, args.choice) == ("a" * 64, "current")
            self.config = self.config.model_copy(update={"selected": "current"})
            self.binding = self.binding.model_copy(
                update={"revision": self.binding.revision + 1}
            )
            return self.review()

        def review(self):
            return UpdateContextResult(
                status="unresolved",
                code="controlled_format_review",
                kind="format_transition",
                binding=self.binding,
                unresolved=2 if self.config.selected is None else 1,
                ready=False,
                next_actions=("save_update", "refresh_update"),
            )

    projection = Projection()
    transport = ProjectedReviewTransport(projection)
    window = MainWindow(supervisor=transport)
    window.show()
    controls = ReviewControls(window, app)
    try:
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "format_transition",
                "vault": str(vault),
                "source": str(source),
                "selection_id": selection,
            }
        )
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.binding is not None
                and not window.workbench.busy
            ),
        )
        controls.select("Other choices")
        until(app, lambda: "Text choice 2" in window_text(window))
        assert controls.button("Keep vault version for configuration choice 1") is None
        assert (
            controls.button("Use incoming version for configuration choice 1") is None
        )
        controls.click("Review vault configuration")
        controls.click("Keep current configuration")
        until(
            app,
            lambda: (
                projection.config.selected == "current" and not window.workbench.busy
            ),
        )
        assert (
            window.runner.session.update_snapshot.unresolved == 1
            and not window.runner.session.update_snapshot.ready
        )
        assert not any(row.command == "choose" for row in transport.commands)
        assert (
            sum(row.command == "choose_configuration" for row in transport.commands)
            == 1
        )
        assert list(vault.iterdir()) == [] and source.read_bytes() == b"source"
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()


def test_format_worker_card_names_note_and_preserves_separate_configuration_choice(
    tmp_path,
):
    from types import SimpleNamespace

    from brz2obsidian.application.update_contracts import UpdateResult
    from brz2obsidian_ui.window import MainWindow
    from tests.application.test_format_configuration import configuration_preparation

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    personal = vault / "Personal.md"
    personal.write_bytes(b"Personal writing.\r\n")
    source = tmp_path / "source.brz"
    source.write_bytes(b"Controlled source boundary")
    prepared = configuration_preparation().model_copy(update={"vault": str(vault)})

    class NativePorts(Operations):
        # Source/history acquisition is controlled; Core preparation, offers,
        # choices, worker protocol, session and Qt are the production path.
        def prepare_format_transition(self, path, reference):
            assert str(path) == str(vault) and str(reference) == str(source)
            return UpdateResult(
                status="unresolved",
                code="format_review",
                kind="format_transition",
                preparation=prepared,
                changes=3,
                unresolved=3,
                next_actions=("save_update", "resolve_update"),
            )

        def read_checkpoint(self, path, **kwargs):
            return SimpleNamespace(status="valid", locator=prepared.locator)

    transport = ReviewWorkerTransport(NativePorts())
    window = MainWindow(supervisor=transport)
    window.show()
    controls = ReviewControls(window, app)
    try:
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update(
            {
                "command": "prepare",
                "kind": "format_transition",
                "vault": str(vault),
                "source": str(source),
                "selection_id": selection,
            }
        )
        until(
            app,
            lambda: (
                window.workbench.snapshot is not None
                and window.workbench.snapshot.binding is not None
                and not window.workbench.busy
            ),
        )
        controls.select("Other choices")
        until(
            app,
            lambda: (
                "Format choice 1" in window_text(window) and not window.workbench.busy
            ),
        )
        text = window_text(window)
        assert "Notes/Opening.md" in text
        assert "Keep vault version preserves the current vault content" in text
        assert (
            "Use incoming version replaces it with the reviewed generated content"
            in text
        )
        assert (
            "Recorded output format: 7" in text and "Incoming output format: 7" in text
        )
        controls.click("Review vault configuration")
        controls.click("Keep current configuration")
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.unresolved == 1
                and not window.workbench.busy
            ),
        )
        assert not window.runner.session.update_snapshot.ready
        controls.select("Other choices")
        until(
            app,
            lambda: (
                "Chosen: current" in window_text(window) and not window.workbench.busy
            ),
        )
        assert "Notes/Opening.md" in window_text(window)
        controls.click("Use incoming version for format choice 1")
        until(
            app,
            lambda: (
                window.runner.session.update_snapshot.ready
                and not window.workbench.busy
            ),
        )
        assert window.runner.session.update_snapshot.unresolved == 0
        controls.select("All changes")
        controls.select("Other choices")
        until(
            app,
            lambda: (
                "Chosen: incoming" in window_text(window) and not window.workbench.busy
            ),
        )
        assert window_text(window).count("Chosen: current") == 2
        assert "Notes/Opening.md" in window_text(window)
        assert not any(row.command in ("save", "apply") for row in transport.commands)
        assert personal.read_bytes() == b"Personal writing.\r\n" and list(
            vault.iterdir()
        ) == [personal]
    finally:
        window.shutdown()
        transport.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
