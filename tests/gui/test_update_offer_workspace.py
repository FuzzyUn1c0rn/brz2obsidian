"""Offer-driven controls and bounded navigation at the typed worker boundary."""

import os
from uuid import uuid4

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QPushButton, QTabBar

from brz2obsidian.application.contracts import WorkerResponse
from brz2obsidian.application.review_choices import attachment_reference_page
from brz2obsidian.application.review_offers import choice_detail_page, choice_offers
from brz2obsidian.application.transport import Terminal
from brz2obsidian.application.update_context_contracts import UpdateContextBinding, UpdateContextResult
from brz2obsidian.application.update_lifecycle import review_plan_page
from brz2obsidian.contracts import ReviewConsentRequirement
from brz2obsidian.core import prepare_review
from tests.application.test_update_lifecycle_contracts import preparation
from tests.gui.test_conversion_window import until, window_text
from tests.gui.test_update_workbench import _visible_text
from tests.reconciliation.test_attachments import attachment_request, binary_context, linked_attachment_request
from tests.reconciliation.test_identity import with_subjects
from tests.reconciliation.test_proposals import request
from tests.reconciliation.test_refresh import two_items
from tests.reconciliation.test_resolution import preflight, with_review_links

pytestmark = pytest.mark.gui


def test_offer_workspace_routes_admitted_choices_and_reaches_bounded_review_pages(tmp_path):
    from brz2obsidian_ui.window import MainWindow

    app = QApplication.instance() or QApplication([])
    vault = tmp_path / "Vault"
    vault.mkdir()
    source = tmp_path / "Incoming.brz"
    source.write_bytes(b"Declared worker source; no Native preparation is claimed")
    binary = preparation(linked_attachment_request())
    binary_offer = next(row for row in choice_offers(binary) if row.domain == "attachment")
    compatible = preparation(with_review_links(two_items()))
    group_offer = next(row for row in choice_offers(compatible) if row.domain == "compatible_group")
    storage = ReviewConsentRequirement(
        schema_id="brz2obsidian.review-consent-requirement", schema_version=1,
        consent_id="storage", kind="storage", requirement="required",
        policy="builtin_transform", fingerprint="current-storage-policy",
        disclosure="Built-in text storage may change line endings; exact owned preimages are retained.",
        subjects=(),
    )
    consent_review = prepare_review(
        with_review_links(request()),
        preflight=preflight().model_copy(update={"consents": (storage,)}),
    )
    consent = compatible.model_copy(update={"review": consent_review})
    consent_offer = next(row for row in choice_offers(consent) if row.domain == "storage")
    unsafe_facts = attachment_request()
    subject = unsafe_facts.subjects[0]
    destination = subject.attachment.allocation_candidates[0]
    unsafe_current = subject.current.model_copy(update={"path": "Assets/unsafe.bin"})
    unsafe_target = subject.source_target.model_copy(update={"normalized_path": "assets/unsafe.bin"})
    unsafe_subject = subject.model_copy(update={
        "item_id": "entry:unsafe", "path": "Assets/unsafe.bin",
        "current": unsafe_current, "source_target": unsafe_target,
        "attachment": subject.attachment.model_copy(update={
            "current_target_id": "resource:unsafe",
            "allocation_candidates": (destination.model_copy(update={
                "path": "Assets/unsafe (incoming-ba7816bf).bin",
                "target": destination.target.model_copy(update={
                    "normalized_path": "assets/unsafe (incoming-ba7816bf).bin", "status": "unsafe",
                }),
            }),),
        }),
    })
    entry = unsafe_facts.identity_inventory[0]
    unsafe_entry = entry.model_copy(update={
        "entry_id": "unsafe-entry", "identity": entry.identity.model_copy(update={"item_id": "entry:unsafe"}),
        "current": unsafe_current, "target": unsafe_target,
    })
    unsafe_facts = with_subjects(unsafe_facts, (unsafe_subject,), (unsafe_entry,))
    unsafe_facts = unsafe_facts.model_copy(update={"link_context": binary_context(unsafe_facts)})
    unsafe = preparation(unsafe_facts)
    unsafe_offer = next(row for row in choice_offers(unsafe) if row.domain == "attachment")
    assert unsafe_offer.change_id != binary_offer.change_id
    assert unsafe_offer.requirement_id != binary_offer.requirement_id
    assert "both" not in unsafe_offer.choices
    assert any(row.choice == "both" and not row.enabled for row in unsafe_offer.unavailable_choices)
    text = preparation(with_review_links(request(current=b"authored")))
    text_offer = next(row for row in choice_offers(text) if row.domain == "text")
    assert text_offer.detail_count == 0
    offers = (group_offer, consent_offer, binary_offer, unsafe_offer, text_offer)
    calls = []

    class Channel:
        # Controlled typed worker projections from canonical public producers.
        # The declared composite projection tests UI presentation/routing only;
        # it does not claim one freshly qualified Core or Native proposal.
        closed = False
        poisoned = False
        binding = None
        selected = None

        def run(self, actual, **callbacks):
            if callbacks.get("on_dispatched") is not None:
                callbacks["on_dispatched"](actual)
            args = actual.arguments
            calls.append(args)
            if args.command == "prepare":
                self.binding = UpdateContextBinding(
                    context_id=str(uuid4()), selection_id=args.selection_id, vault=str(vault),
                    association_id="a" * 64, checkpoint_commit="b" * 40,
                    checkpoint_generation=1, proposal_id="declared-ui-projection", generation=1, revision=1,
                )
                result = UpdateContextResult(
                    status="unresolved", code="prepared", kind="source_update", binding=self.binding,
                    changes=2, unresolved=5, history_retained=True, checkpoint_commit="b" * 40,
                    next_actions=("resolve_update", "save_update"),
                )
            else:
                assert args.binding == self.binding, "Navigation/actions must use the current binding"
                common = dict(kind="source_update", binding=self.binding)
                if args.command == "page":
                    index = args.offset
                    assert index in (0, 1)
                    plan = text.review if index == 0 else binary.review
                    local = review_plan_page(
                        plan, proposal_id=plan.proposal.proposal_id, generation=1,
                        offset=0, limit=1, byte_offset=args.byte_offset, byte_limit=12,
                    )
                    page = local.model_copy(update={
                        "proposal_id": self.binding.proposal_id, "total": 2,
                        "offset": index, "next_offset": 1 if index == 0 else None,
                        "omitted": local.omitted or index == 0,
                    })
                    result = UpdateContextResult(status="available", code="available", page=page, **common)
                elif args.command == "choices":
                    row = offers[args.offset]
                    if self.selected is not None and row.requirement_id == consent_offer.requirement_id:
                        row = row.model_copy(update={"selected": "accept", "decision_id": "retained-storage-decision"})
                    result = UpdateContextResult(
                        status="available", code="available", offers=(row,), total_choices=5,
                        next_choice_offset=args.offset + 1 if args.offset < 4 else None, **common,
                    )
                elif args.command == "choice_details":
                    assert args.requirement_id in (binary_offer.requirement_id, text_offer.requirement_id)
                    owner = binary if args.requirement_id == binary_offer.requirement_id else text
                    rows, total, following = choice_detail_page(owner, requirement_id=args.requirement_id, offset=args.offset, limit=2)
                    result = UpdateContextResult(
                        status="available", code="available", choice_details=rows,
                        total_choice_details=total, next_choice_detail_offset=following, **common,
                    )
                elif args.command == "references":
                    assert args.requirement_id in (binary_offer.requirement_id, unsafe_offer.requirement_id)
                    owner = binary if args.requirement_id == binary_offer.requirement_id else unsafe
                    rows, total, following = attachment_reference_page(owner, args.requirement_id, offset=args.offset, limit=1)
                    result = UpdateContextResult(
                        status="available", code="available", references=rows,
                        total_references=total, next_reference_offset=following, **common,
                    )
                elif args.command == "choose":
                    assert (args.requirement_id, args.choice, args.assumptions_digest) == (
                        consent_offer.requirement_id, "accept", consent_offer.assumptions_digest,
                    )
                    self.selected = "accept"
                    self.binding = self.binding.model_copy(update={"revision": self.binding.revision + 1})
                    result = UpdateContextResult(
                        status="unresolved", code="accepted", kind="source_update", binding=self.binding,
                        unresolved=4, changes=2, history_retained=True,
                        checkpoint_commit="b" * 40, next_actions=("resolve_update", "save_update"),
                    )
                else:
                    raise AssertionError("This workspace must only issue its admitted bounded requests")
            return Terminal(phase="completed", response=WorkerResponse(
                operation="update", request_id=actual.request_id, sequence=actual.sequence, result=result,
            ))

        def close(self):
            self.closed = True

    channel = Channel()

    class Transport:
        def open_update(self, **kwargs):
            return channel

        def run(self, actual):
            raise AssertionError("Review navigation must use the update worker boundary")

    window = MainWindow(supervisor=Transport())
    window.show()

    def button(name):
        return next((row for row in window.findChildren(QPushButton) if row.isVisible() and row.accessibleName() == name), None)

    def click(name):
        until(app, lambda: button(name) is not None and button(name).isEnabled())
        button(name).click()

    def select(name):
        index = next((queue.model().index(i, 0) for i in range(queue.model().rowCount())
                      if queue.model().index(i, 0).data() == name), None)
        assert index is not None, "The queue must expose " + name
        QTest.mouseClick(queue.viewport(), Qt.MouseButton.LeftButton, pos=queue.visualRect(index).center())
        app.processEvents()

    try:
        tabs = window.findChild(QTabBar)
        tabs.setCurrentIndex(next(i for i in range(tabs.count()) if tabs.tabText(i) == "Update vault"))
        selection = str(uuid4())
        window.runner.select_update(str(vault), selection_id=selection)
        window.runner.submit_update({"command": "prepare", "kind": "source_update",
                                     "vault": str(vault), "source": str(source), "selection_id": selection})
        queue = next(row for row in window.findChildren(QAbstractItemView) if row.accessibleName() == "Review queue")
        select("Other choices")
        until(app, lambda: button("Approve compatible group") is not None and button("Approve compatible group").isEnabled())
        click("Next review choices")
        until(app, lambda: "Built-in text storage may change line endings" in window_text(window))
        click("Accept storage policy")
        until(app, lambda: channel.selected == "accept")
        until(app, lambda: window.runner.session.update_snapshot.binding.revision == 2)
        click("Next review choices")
        until(app, lambda: "Chosen: accept" in window_text(window))
        click("Next review choices")
        click("Review details for attachment choice 3")
        until(app, lambda: "Output for: Vault version" in window_text(window))
        assert "Output for: Incoming version" in window_text(window)
        click("Next choice details")
        until(app, lambda: "Assets/data (incoming-ba7816bf).bin" in window_text(window))
        assert "Output for: Both versions" in window_text(window)
        assert "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" in window_text(window)
        assert "3 bytes" in window_text(window)
        click("Review references for attachment choice 3")
        until(app, lambda: "Reference text: Keep first" in window_text(window))
        click("Next reference page")
        until(app, lambda: "Reference text: Redirect second" in window_text(window))
        assert "Notes/Owner.md" in window_text(window)
        click("Next review choices")
        until(app, lambda: "Unavailable" in window_text(window))
        both = button("Keep both versions for attachment choice 4")
        assert both is not None and not both.isEnabled()
        click("Review references for attachment choice 4")
        until(app, lambda: "No reference occurrences for this choice." in window_text(window))
        click("Next review choices")
        click("Review details for text choice 5")
        until(app, lambda: "No additional details for this choice." in window_text(window))
        select("Conflicts")
        until(app, lambda: "auth" in _visible_text(window))
        click("More comparison bytes for Notes/Opening.md")
        until(app, lambda: "ored" in _visible_text(window))
        click("Next comparison items")
        until(app, lambda: "Assets/data.bin" in window_text(window))
        assert window.runner.session.update_snapshot.binding.revision == 2
        assert calls[-1].command == "page" and calls[-1].offset == 1 and calls[-1].byte_offset == 0
        assert any(row.command == "page" and row.byte_offset == 4 for row in calls)
        assert any(row.command == "choice_details" and row.offset == 2 for row in calls)
        assert any(row.command == "references" and row.offset == 1 for row in calls)
        assert sum(row.command == "choose" for row in calls) == 1
        assert not window.runner.session.update_snapshot.ready
        assert list(vault.iterdir()) == []
        assert source.read_bytes() == b"Declared worker source; no Native preparation is claimed"
    finally:
        window.shutdown()
        channel.close()
        window.hide()
        window.deleteLater()
        app.processEvents()
