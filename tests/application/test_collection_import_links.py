def test_import_links_preserve_exact_targets_and_require_each_explicit_connection():
    from brz2obsidian.obsidian.import_links import inspect_import_links

    existing = {
        "Journal/Manual.md": (
            b"[[Twin#Heading|Alias]]\n"
            b"[Relative](../Old/Twin.md#%5Eparagraph)\n"
            b"[[Imports/B/Notes/Waiting|Future]]\n"
            b"[[Unmade]]\n"
            b"[[Independent missing]]\n"
        ),
        "Old/Twin.md": b"# Heading\n\nText ^paragraph\n",
    }
    incoming = {"Imports/B/Notes/Waiting.md": b"# Waiting\n"}
    offered = inspect_import_links(
        existing, incoming, reserved_paths=("Old/Unmade.md",)
    )
    assert not offered.safe
    observations = {row.before.display_text: row for row in offered.observations}
    assert observations["Alias"].before.path == "Old/Twin.md"
    assert observations["Alias"].before.fragment.value == "Heading"
    assert observations["Alias"].after == observations["Alias"].before
    assert observations["Relative"].after.status == "resolved"
    assert observations["Relative"].after.fragment.value == "paragraph"
    assert observations["Unmade"].kind == "intentional_absence"
    assert observations["Independent missing"].kind == "preexisting_warning"
    decision = observations["Future"].connection
    assert decision.target_path == "Imports/B/Notes/Waiting.md"
    assert decision.document_path == "Journal/Manual.md"

    approved = inspect_import_links(
        existing, incoming, reserved_paths=("Old/Unmade.md",), connections=(decision,)
    )
    assert approved.safe
    assert (
        next(row for row in approved.observations if row.connection).kind
        == "approved_connection"
    )
    changed = existing | {
        "Journal/Manual.md": existing["Journal/Manual.md"] + b"Edit\r\n"
    }
    assert not inspect_import_links(
        changed, incoming, reserved_paths=("Old/Unmade.md",), connections=(decision,)
    ).safe
    collision = incoming | {"Imports/B/Notes/twin.md": b"# Heading\n"}
    assert not inspect_import_links(
        existing, collision, reserved_paths=("Old/Unmade.md",), connections=(decision,)
    ).safe


def test_shortest_relative_and_qualified_links_track_only_relevant_names():
    from brz2obsidian.obsidian.import_links import (
        inspect_import_links,
        reserved_import_names,
    )

    existing = {
        "Journal/Subject.md": (
            b"[[../Old/Twin#Heading|Wiki relative]]\n"
            b"[Markdown shortest](Twin.md)\n"
            b"[Markdown qualified](Old/Proof.pdf)\n"
            b"[[Notes/Waiting|Reserved suffix]]\n"
            b"[[Other/Fresh|Unrelated qualified warning]]\n"
            b"[[Known gap]]\n"
        ),
        "Old/Twin.md": b"# Heading\n",
        "Old/Proof.pdf": b"%PDF-1.7\x00\xff",
    }
    names = reserved_import_names(existing, "Imports/New")
    assert {"twin", "proof.pdf", "waiting", "known gap"} <= set(names)
    assert "fresh" not in names

    incoming = {"Imports/New/Notes/Fresh.md": b"# Fresh\n"}
    impact = inspect_import_links(existing, incoming, gap_paths=("Old/Known gap.md",))
    assert impact.safe
    by_display = {row.before.display_text: row for row in impact.observations}
    assert by_display["Wiki relative"].after.path == "Old/Twin.md"
    assert by_display["Wiki relative"].after.fragment.value == "Heading"
    assert by_display["Markdown shortest"].after.path == "Old/Twin.md"
    assert by_display["Markdown qualified"].after.path == "Old/Proof.pdf"
    assert by_display["Markdown qualified"].after.status == "resolved"
    assert by_display["Reserved suffix"].query.value == "Notes/Waiting"
    assert by_display["Unrelated qualified warning"].kind == "preexisting_warning"
    assert by_display["Known gap"].kind == "known_source_gap"


def test_import_link_audit_rejects_normalized_collisions_and_affected_unknown_syntax():
    from brz2obsidian.obsidian.import_links import inspect_import_links

    incoming = {"Imports/B/Notes/Caf\u00e9.md": b"# New\n"}
    existing = {"Imports/B/notes/Old.md": b"Existing\r\n"}
    assert inspect_import_links(existing, incoming).blockers == (
        "import_target_occupied",
    )
    existing = {"Imports/B/Notes/Cafe\u0301.md": b"Existing\r\n"}
    assert inspect_import_links(existing, incoming).blockers == (
        "import_target_occupied",
    )

    unrelated = {"Manual.md": b"[Reference][opaque]\n\n[opaque]: Other.md\n"}
    impact = inspect_import_links(unrelated, incoming)
    assert impact.safe and impact.warnings == ("Manual.md",)
    uncertain = {"Manual.md": b"[Reference][opaque]\n\n[opaque]: Caf%C3%A9.md\n"}
    assert inspect_import_links(uncertain, incoming).blockers == (
        "affected_link_uncertain",
    )


def test_operations_preview_renders_real_scope_from_a_verified_source_session(
    tmp_path, monkeypatch
):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from brz2obsidian.application.operations import Operations
    from brz2obsidian.application.workflow import SourceModuleBinding, Workflow
    from brz2obsidian.obsidian import ObsidianRenderer
    from brz2obsidian.publication import FilesystemPublisher
    from brz2obsidian.publication.vault_native import observe_file
    from tests.application.test_graph_modules import POLICY, edge, item, snapshot
    from tests.application.test_module_seams import METADATA

    vault = tmp_path / "vault"
    vault.mkdir()
    manual = vault / "Authored.md"
    authored = b"[[Future#Future|Connect only after review]]\r\n"
    manual.write_bytes(authored)
    info, digest, _, identity = observe_file(vault, manual, prefix_limit=0)
    inventory = (
        SimpleNamespace(
            path="Authored.md",
            size=info.st_size,
            sha256=digest,
            identity=identity,
            exclusion=None,
        ),
    )
    history = SimpleNamespace(
        admission=SimpleNamespace(
            vault=vault,
            inventory=inventory,
            inventory_complete=True,
            status="supported",
            repository=SimpleNamespace(kind="root"),
        ),
        status="absent",
        checkpoint=None,
    )
    facts = snapshot(
        (item("future", "Future"),), (edge("entry-future", "entry", "future"),)
    )
    session = SimpleNamespace(
        snapshot=facts,
        source_identity=facts.identity,
        verify_consistency=lambda: None,
    )
    module = SimpleNamespace(open=lambda source: nullcontext(session))
    workflow = Workflow(
        SourceModuleBinding(module, POLICY),
        ObsidianRenderer(),
        FilesystemPublisher(),
        metadata_factory=lambda: METADATA.model_copy(update={"renderer_version": "9"}),
    )
    operations = Operations(workflow=workflow)
    monkeypatch.setattr(operations, "inspect_history", lambda root: history)
    preview = operations.prepare_collection_import_from_source(
        vault,
        tmp_path / "opaque.brz",
        staging=tmp_path / "staging",
        preview_connections=True,
    )
    assert preview.code == "import_connection_preview", preview
    assert not preview.ready and preview.preparation is None
    (observed,) = preview.import_link_impact.observations
    assert observed.kind == "connection_required"
    assert observed.connection.target_path == "Imports/Graph/Notes/Future.md"
    assert observed.after.fragment.value == "Future"
    assert (tmp_path / "staging" / observed.connection.target_path).is_file()
    assert (tmp_path / "staging/Imports/Graph/migration-record.json").is_file()
    assert manual.read_bytes() == authored


def test_authored_base_fixed_targets_reserve_and_review_only_the_changed_links():
    from brz2obsidian.obsidian.import_links import (
        inspect_import_links,
        reserved_import_names,
    )

    existing = {
        "Index.base": (
            b"formulas:\n"
            b'  open: \'link("Imports/B/Notes/Future.md", "Open future")\'\n'
            b"  old: 'file(\"Old/Owned.md\")'\n"
            b'  elsewhere: \'file("Elsewhere/" + note.basename + ".md")\'\n'
            b"views: []\n"
        ),
        "Old/Owned.md": b"# Owned\n",
    }
    incoming = {"Imports/B/Notes/Future.md": b"# Future\n"}
    assert "future" in reserved_import_names(existing, "Imports/B")
    offered = inspect_import_links(existing, incoming)
    rows = {row.after.display_text: row for row in offered.observations}
    assert offered.blockers == ("connection_required",)
    assert rows["Old/Owned.md"].before == rows["Old/Owned.md"].after
    choice = rows["Open future"].connection
    assert choice.document_path == "Index.base"
    assert choice.target_path == "Imports/B/Notes/Future.md"
    assert inspect_import_links(existing, incoming, connections=(choice,)).safe

    relevant = existing | {
        "Index.base": existing["Index.base"].replace(b"Elsewhere/", b"Imports/B/Notes/")
    }
    assert (
        "affected_link_uncertain" in inspect_import_links(relevant, incoming).blockers
    )
