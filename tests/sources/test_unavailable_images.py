"""Unavailable local image policy through public source sessions."""

import json
import tempfile
from contextlib import closing
from hashlib import sha256

import pytest

from brz2obsidian.contracts import ExactContent, MigrationError, MigrationRefused
from brz2obsidian.core import analyze
from brz2obsidian.obsidian import interpret_links
from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig,
    LocalApiSession,
    LocalApiSourceModule,
    LocalApiSourceRef,
)
from brz2obsidian.sources.thebrain.profile import BRZ_POLICY
from tests.application.test_forgotten_workflow import forget, rewrite
from tests.application.test_graph_workflow import graph_archive, identity
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_resources_workflow import thought
from tests.sources.test_current_literal_tokens import historical_note_capture
from tests.sources.test_local_api_bom import note_api
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.support.local_api_payloads import IMAGE, NOTE, PNG, attachment

UNDECLARED_API_IMAGE = "bbbbbbbb-4444-4444-8444-444444444444.png"


def test_two_missing_images_keep_four_present_controls_and_exact_original(tmp_path):
    missing = "![Lost](.data/md-images/lost.png)"
    sized = "![Sized](.data/md-images/sized.png#$width=70p$)"
    controls = [f"![Kept {i}](.data/md-images/kept{i}.png)" for i in range(4)]
    raw = (
        "Café *before*.\r\n"
        + missing
        + "\r\n"
        + "\r\n".join(controls)
        + "\r\n"
        + sized
        + "\r\nAfter.\r\n"
    ).encode()
    source = literal_archive(
        tmp_path / "source.brz",
        raw,
        resources=tuple(
            ({"Type": 12, "Location": f"kept{i}.png"}, PNG) for i in range(4)
        ),
    )
    expected = (
        raw.decode()
        .replace(missing, "Image unavailable: Lost")
        .replace(sized, "Image unavailable: Sized")
    )
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [
            (edit.kind, edit.before, edit.after) for edit in document.text_adaptations
        ] == [
            ("image_unavailable", missing, "Image unavailable: Lost"),
            ("image_unavailable", sized, "Image unavailable: Sized"),
        ]
        assert all(
            edit.source_digest == sha256(raw).hexdigest()
            for edit in document.text_adaptations
        )
        assert [
            reference.expected_original for reference in document.references
        ] == controls
        findings = [
            finding
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        ]
        assert len(findings) == 2
        for finding, phrase in zip(findings, (missing, sized), strict=True):
            observed = json.loads(finding.observed_json)
            assert observed["source_reference"]["before"] == phrase
            assert observed["absence"]["basis"] == "archive_undeclared_no_payload"
        with session.open_payload(document.original_asset_id) as stream:
            assert stream.read() == raw
        images = [asset for asset in session.snapshot.assets if asset.role == "image"]
        assert len(images) == 4
        for asset in images:
            with session.open_payload(asset.asset_id) as stream:
                assert stream.read() == PNG


def test_current_api_unavailable_image_without_companions_replays_exact_bom(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = (
        b"\xef\xbb\xbf"
        + (
            f"Before ![Lost](.data/md-images/{UNDECLARED_API_IMAGE}) after.\r\n"
        ).encode()
    )
    api = note_api(raw)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == "Before Image unavailable: Lost after.\r\n"
            assert [edit.kind for edit in document.text_adaptations] == [
                "literal_text",
                "image_unavailable",
            ]
            payloads = {}
            for asset in session.snapshot.assets:
                if asset.availability == "present":
                    with session.open_payload(asset.asset_id) as stream:
                        payloads[asset.asset_id] = stream.read()
            assert payloads[document.original_asset_id] == raw
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            with closing(
                LocalApiSession(
                    source=source,
                    snapshot=session.snapshot,
                    audit=audit,
                    payloads=payloads,
                    profile_version="4",
                )
            ) as replay:
                assert replay.snapshot == session.snapshot
                replay.verify_consistency()
            for malformed in ("null", "{broken"):
                finding = session.snapshot.findings[0].model_copy(
                    update={"observed_json": malformed}
                )
                forged = session.snapshot.model_copy(
                    update={
                        "findings": (finding,),
                        "identity": session.snapshot.identity.model_copy(
                            update={"snapshot_digest": ""}
                        ),
                    }
                )
                with pytest.raises(MigrationError):
                    LocalApiSession(
                        source=source,
                        snapshot=forged,
                        audit=audit,
                        payloads=payloads,
                        profile_version="4",
                    )
    assert not any(UNDECLARED_API_IMAGE in path for path, _, _ in api.requests)


def test_two_identical_missing_images_inside_rewritten_row_keep_generated_code(
    tmp_path,
):
    missing = "![Lost](.data/md-images/lost.png)"
    raw = (
        f'Café <X/>\r\n\r\n|{missing}|{missing}|`x|y`|:(table="column-widths:-1,0,0,0;justification:default"):\r\n|a|b|c|\r\n'
    ).encode()
    expected = "Café \\<X/>\r\n\r\n| | | |\n|---|---|---|\n|Image unavailable: Lost|Image unavailable: Lost|<code>x&#124;y</code>|\r\n|a|b|c|\r\n"
    source = literal_archive(tmp_path / "source.brz", raw)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [edit.kind for edit in document.text_adaptations] == [
            "literal_text",
            "markdown_insert_image_unavailable",
        ]
        occurrences = [
            json.loads(finding.observed_json)
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        ]
        assert len(occurrences) == 2
        assert [row["source_reference"]["start"] for row in occurrences] == [
            raw.decode().index(missing),
            raw.decode().index(missing) + len(missing) + 1,
        ]
        assert occurrences[0]["notice"]["end"] < occurrences[1]["notice"]["start"]
        assert all(
            row["composition"]["base_edits"][0]["kind"] == "markdown_insert"
            for row in occurrences
        )
        assert document.references == ()
        restored = document.text
        for edit in reversed(document.text_adaptations):
            restored = (
                restored[: edit.adapted_start]
                + edit.before
                + restored[edit.adapted_end :]
            )
        assert restored.encode() == raw


def test_heading_toc_and_callout_keep_contained_literals_and_notice_occurrence(
    tmp_path,
):
    phrase = "![Lost <X/>](.data/md-images/lost.png)"
    raw = f"[/toc/]\n\n# {phrase}\n\n> [!tip|icon:😂] {phrase}\n> Body\n".encode()
    source = literal_archive(tmp_path / "source.brz", raw)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert (
            "# Image unavailable: Lost &#60;X&#47;&#62; ^brz-toc-heading-1"
            in document.text
        )
        assert "> [!tip] 😂 Image unavailable: Lost &#60;X&#47;&#62;" in document.text
        assert document.text.count("Image unavailable:") == 2
        occurrences = [
            json.loads(finding.observed_json)
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        ]
        assert len(occurrences) == 2
        assert all(o["source_reference"]["before"] == phrase for o in occurrences)
        assert all(e.kind != "literal_text" for e in document.text_adaptations)


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_historical_api_profiles_keep_missing_image_refusal(profile):
    api = note_api(b"![Lost](.data/md-images/lost.png)\n")
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version=profile,
        )
        with (
            pytest.raises(MigrationRefused, match="one preserved owner image"),
            module.open(LocalApiSourceRef(BRAIN)),
        ):
            pass


@pytest.mark.parametrize("referenced", (True, False))
def test_declared_archive_state3_image_needs_active_reference_and_has_no_measured_bytes(
    tmp_path, referenced
):
    raw = b"![Lost](.data/md-images/lost.png)\n" if referenced else b"Plain note.\n"
    source = literal_archive(
        tmp_path / "source.brz",
        raw,
        resources=(({"Type": 12, "Location": "lost.png", "DataLength": 17}, None),),
    )

    def state(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000001"] = 3
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, state)
    if not referenced:
        with pytest.raises(MigrationRefused), BrzSourceModule().open(source):
            pass
        return
    with BrzSourceModule().open(source) as session:
        image = next(a for a in session.snapshot.assets if a.role == "image")
        assert (image.availability, image.actual_length, image.actual_sha256) == (
            "absent",
            None,
            None,
        )
        assert session.snapshot.documents[0].text == "Image unavailable: Lost\n"
        finding = next(
            finding
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        )
        assert finding.affected == (image.asset_id,)
        assert json.loads(finding.observed_json)["absence"] == {
            "basis": "archive_declared_state3_no_payload",
            "location": "lost.png",
            "asset_id": image.asset_id,
            "state": 3,
        }


def test_current_api_declared_image_content404_is_classified_and_reference_bound():
    api = note_api(f"![Lost](.data/md-images/{IMAGE}.png)\n".encode())
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, IMAGE + ".png", length=123)
    api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
        404,
        {"error": "not retained"},
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            image = next(a for a in session.snapshot.assets if a.role == "image")
            assert (image.availability, image.actual_length, image.actual_sha256) == (
                "absent",
                None,
                None,
            )
            finding = next(
                finding
                for finding in session.snapshot.findings
                if finding.rule_id == "thebrain.unavailable-declared-image.v1"
            )
            assert finding.affected == (IMAGE,)
            assert (
                json.loads(finding.observed_json)["absence"]["basis"]
                == "api_declared_content404"
            )
            assert session.snapshot.documents[0].text == "Image unavailable: Lost\n"
            session.verify_consistency()


def test_core_requires_source_bound_occurrence_evidence_for_image_edits(tmp_path):
    source = literal_archive(
        tmp_path / "source.brz", b"![Lost](.data/md-images/lost.png)\n"
    )
    with BrzSourceModule().open(source) as session:
        snapshot = session.snapshot
        assert analyze(snapshot, BRZ_POLICY).issues[0].severity == "warning"
        with pytest.raises(MigrationRefused, match="notice.*evidence"):
            analyze(snapshot.model_copy(update={"findings": ()}), BRZ_POLICY)
        finding = snapshot.findings[0]
        with pytest.raises(MigrationRefused, match="notice.*evidence"):
            analyze(
                snapshot.model_copy(
                    update={
                        "findings": (
                            finding.model_copy(
                                update={"affected": (snapshot.documents[0].key,)}
                            ),
                        )
                    }
                ),
                BRZ_POLICY,
            )
        evidence = json.loads(finding.observed_json)
        evidence["notice"]["start"] += 1
        with pytest.raises(MigrationRefused, match="notice.*evidence"):
            analyze(
                snapshot.model_copy(
                    update={
                        "findings": (
                            finding.model_copy(
                                update={"observed_json": json.dumps(evidence)}
                            ),
                        )
                    }
                ),
                BRZ_POLICY,
            )


@pytest.mark.parametrize(
    "destination",
    (
        ".data/md-images/lost.png?query=1",
        ".data/md-images/lost.png#$width=0p$",
        ".data/md-images/lost.png#",
        ".data/md-images/a%2fb.png",
        ".data/md-images/%ff.png",
        ".data/md-images/../lost.png",
        ".data/md-images/lost.unknown",
        ".data/md-images/lost.ico",
        ".data/md-images/a:b.png",
        ".data/md-images/a%00.png",
    ),
)
def test_missing_image_keeps_strict_destination_and_kind_guards(tmp_path, destination):
    source = literal_archive(
        tmp_path / "source.brz", f"![Lost]({destination})\n".encode()
    )
    with pytest.raises(MigrationRefused), BrzSourceModule().open(source):
        pass


@pytest.mark.parametrize("identity_named", (False, True, "embedded"))
def test_other_owner_same_basename_is_not_borrowed_but_foreign_identity_refuses(
    tmp_path, identity_named
):
    other = "77777777-7777-4777-8777-777777777777"
    image_id = "aaaaaaaa-0000-4000-8000-000000000001"
    filename = image_id + ".png" if identity_named is True else "diagram.png"
    if identity_named == "embedded":
        filename = "diagram-" + image_id + ".png"
    source = literal_archive(
        tmp_path / "source.brz",
        f"![Lost](.data/md-images/{filename})\n".encode(),
        resources=(({"SourceId": other, "Type": 12, "Location": filename}, PNG),),
        thoughts=(thought(other, "Other owner"),),
    )
    if identity_named is True:
        with (
            pytest.raises(MigrationRefused, match="another owner's asset"),
            BrzSourceModule().open(source),
        ):
            pass
    else:
        with BrzSourceModule().open(source) as session:
            assert session.snapshot.documents[0].text == "Image unavailable: Lost\n"
            assert session.snapshot.documents[0].references == ()
            image = next(a for a in session.snapshot.assets if a.role == "image")
            assert image.owner == other


def test_protected_images_and_unsafe_original_omission_precede_notices(tmp_path):
    missing = "![Lost](.data/md-images/lost.png)"
    protected = (
        "`"
        + missing
        + "`\n<!-- "
        + missing
        + " -->\n"
        + missing.replace("![", "\\!\\[").replace("](", "\\](")
        + "\n"
    )
    raw = (
        protected
        + "[Private](brain://AAAAAAAAAAAAAAAAAAAAAg/Private)\n"
        + missing
        + "\n"
    ).encode()
    source = graph_archive(
        tmp_path / "source.brz",
        {1: "Home", 2: "Private"},
        notes={1: (raw, 4)},
    )
    rewrite(source, lambda parts: forget(parts, 2))
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.original_copy_omitted and document.original_asset_id is None
        assert document.text == protected + "\nImage unavailable: Lost\n"
        assert (
            len(
                [
                    finding
                    for finding in session.snapshot.findings
                    if finding.kind == "unavailable_image_reference"
                ]
            )
            == 1
        )
        assert not any(a.role == "note_original" for a in session.snapshot.assets)
    private_label = graph_archive(
        tmp_path / "private.brz",
        {1: "Home", 2: "Private"},
        notes={1: (f"![{identity(2)}](.data/md-images/lost.png)\n".encode(), 4)},
    )
    rewrite(private_label, lambda parts: forget(parts, 2))
    with pytest.raises(MigrationRefused), BrzSourceModule().open(private_label):
        pass


@pytest.mark.parametrize(
    "failure",
    ("metadata404", "content403", "content500", "invalid200", "unreferenced404"),
)
def test_current_api_image_errors_are_not_blanket_absence(failure):
    raw = (
        f"![Lost](.data/md-images/{IMAGE}.png)\n".encode()
        if failure != "unreferenced404"
        else b"Plain note.\n"
    )
    api = note_api(raw)
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, IMAGE + ".png", length=13)
    api.payloads[IMAGE] = b"not image data"
    route = f"/api/attachments/{BRAIN}/{IMAGE}/"
    if failure == "metadata404":
        api.overrides[route + "metadata"] = (404, {"error": "missing"})
    elif failure != "invalid200":
        status = {"content403": 403, "content500": 500, "unreferenced404": 404}[failure]
        api.overrides[route + "file-content"] = (status, {"error": "unavailable"})
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with pytest.raises(MigrationError), module.open(LocalApiSourceRef(BRAIN)):
            pass


@pytest.mark.parametrize("profile", ("1", "2", "3"))
@pytest.mark.parametrize(
    "kind", ("image_unavailable", "markdown_insert_image_unavailable")
)
def test_historical_constructor_rejects_coherent_notice_kind(profile, kind):
    raw = b"![Lost](.data/md-images/lost.png)\n"
    notice = "Image unavailable: Lost\n"
    arguments = historical_note_capture(
        profile,
        raw,
        normalized=notice,
        edits=(
            {
                "kind": kind,
                "start": 0,
                "end": len(raw) - 1,
                "before": raw.decode()[:-1],
                "after": notice[:-1],
                "adapted_start": 0,
                "adapted_end": len(notice) - 1,
                "source_digest": sha256(raw).hexdigest(),
            },
        ),
    )
    with pytest.raises(MigrationRefused):
        LocalApiSession(**arguments)


def test_notice_label_entities_keep_following_real_references_visible_to_updates(
    tmp_path,
):
    raw = (
        b"![`odd` &#96; \\|\r\nlabel](.data/md-images/lost.png)\r\n"
        b"![Kept](.data/md-images/kept.png)\r\n"
    )
    source = literal_archive(
        tmp_path / "source.brz",
        raw,
        resources=(({"Type": 12, "Location": "kept.png"}, PNG),),
    )
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text.startswith("Image unavailable: odd &#96; &#124; label\r\n")
        assert len(document.references) == 1
        links = interpret_links(
            ExactContent(data=document.text.encode()),
            document_id="notice",
            source_path="Home.md",
            path_mode="relative",
            targets=(),
            target_facts=(),
            inventory="partial",
            output_format=8,
        )
        assert links.status == "supported" and len(links.occurrences) == 1


def test_current_api_bom_compound_row_and_declared_absence_bind_together():
    missing = f"![Lost *label*](.data/md-images/{UNDECLARED_API_IMAGE}#$width=70p$)"
    raw = (
        "\ufeffCafé <X/>\r\n\r\n"
        + f"|{missing}|{missing}|`![code](.data/md-images/code.png) x|y`|"
        + ':(table="column-widths:-1,0,0,0;justification:default"):\r\n|a|b|c|\r\n'
        + f"\r\n![Declared](.data/md-images/{IMAGE}.png)\r\n"
    ).encode()
    api = note_api(raw)
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, IMAGE + ".png", length=17)
    api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
        404,
        {"error": "missing"},
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.documents[0].text.count("Image unavailable:") == 3
            session.verify_consistency()


def test_quoted_multiline_setext_keeps_parser_owned_heading_and_image_origin(tmp_path):
    raw = b"[/toc/]\n\n> First ![Lost](.data/md-images/lost.png)  \n> second\n> ---\n"
    source = literal_archive(tmp_path / "source.brz", raw)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == (
            "- [First Lost second](#^brz-toc-heading-1)\n\n"
            "> ## First Image unavailable: Lost   second ^brz-toc-heading-1\n"
        )
        finding = next(
            finding
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        )
        occurrence = json.loads(finding.observed_json)
        assert (
            occurrence["source_reference"]["before"]
            == "![Lost](.data/md-images/lost.png)"
        )
        assert occurrence["source_reference"]["start"] == raw.decode().index("![Lost]")


@pytest.mark.parametrize(
    "state,present",
    ((1, False), (2, False), (True, False), (None, False), (7, False), (3, True)),
)
def test_declared_archive_image_inconsistent_states_do_not_become_absence(
    tmp_path, state, present
):
    source = literal_archive(
        tmp_path / "source.brz",
        b"![Lost](.data/md-images/lost.png)\n",
        resources=(({"Type": 12, "Location": "lost.png"}, PNG if present else None),),
    )

    def alter(parts):
        meta = json.loads(parts["meta.json"])
        if state is not None:
            meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000001"] = state
        parts["meta.json"] = json.dumps(meta).encode()

    rewrite(source, alter)
    with pytest.raises(MigrationRefused), BrzSourceModule().open(source):
        pass


def test_api_notice_evidence_is_canonical_when_document_sorts_before_owner():
    raw = f"![Lost](.data/md-images/{UNDECLARED_API_IMAGE})\n".encode()
    api = note_api(raw)
    note_id = "00000001-1111-4111-8111-111111111111"
    value = api.attachments.pop(NOTE)
    api.attachments[note_id] = dict(value, id=note_id)
    api.payloads[note_id] = api.payloads.pop(NOTE)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            assert session.snapshot.findings[0].affected == (note_id, HOME)
            session.verify_consistency()


def test_absent_ordinary_note_cannot_use_an_unreferenced_absent_image(tmp_path):
    source = literal_archive(
        tmp_path / "source.brz",
        b"Unavailable authored note.\n",
        resources=(({"Type": 12, "Location": "lost.png", "DataLength": 17}, None),),
    )

    def absent(parts):
        meta = json.loads(parts["meta.json"])
        meta["AttachmentFileStates"] = {key: 3 for key in meta["AttachmentFileStates"]}
        meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000001"] = 3
        parts["meta.json"] = json.dumps(meta).encode()
        parts.pop(HOME + "/Notes.md")

    rewrite(source, absent)
    with pytest.raises(MigrationRefused) as error, BrzSourceModule().open(source):
        pass
    assert error.value.issues[0].code == "missing_required_payload"


@pytest.mark.parametrize("declared", (False, True))
def test_brz_missing_svg_is_a_notice_without_claiming_decoded_pixels(
    tmp_path, declared
):
    resources = (
        (({"Type": 12, "Location": "lost.svg", "DataLength": 17}, None),)
        if declared
        else ()
    )
    source = literal_archive(
        tmp_path / "source.brz",
        b"![Vector](.data/md-images/lost.svg)\n",
        resources=resources,
    )
    if declared:

        def absent(parts):
            meta = json.loads(parts["meta.json"])
            meta["AttachmentFileStates"]["aaaaaaaa-0000-4000-8000-000000000001"] = 3
            parts["meta.json"] = json.dumps(meta).encode()

        rewrite(source, absent)
    with BrzSourceModule().open(source) as session:
        assert session.snapshot.documents[0].text == "Image unavailable: Vector\n"
        images = [asset for asset in session.snapshot.assets if asset.role == "image"]
        assert len(images) == int(declared)
        assert all(
            asset.actual_length is None and asset.actual_sha256 is None
            for asset in images
        )


@pytest.mark.parametrize("backend", ("brz", "api"))
def test_undeclared_known_image_families_need_no_invented_asset_or_fetch(
    tmp_path, backend
):
    locations = (
        "generic.png",
        "sub/diagram.jpeg",
        "UPPER.JPG",
        "00000000-0000-0000-0000-000000000000.webp",
        "generic.GIF",
        "diagram.bmp",
        "nested/path/diagram.avif",
        "Vector.svg",
    )
    raw = "".join(
        f"![Missing {index}](.data/md-images/{location})\n"
        for index, location in enumerate(locations)
    ).encode()
    expected = "".join(f"Image unavailable: Missing {index}\n" for index in range(8))

    def check(session):
        assert session.snapshot.documents[0].text == expected
        assert not any(asset.role == "image" for asset in session.snapshot.assets)
        findings = [
            finding
            for finding in session.snapshot.findings
            if finding.kind == "unavailable_image_reference"
        ]
        assert len(findings) == 8
        observations = sorted(
            (json.loads(finding.observed_json) for finding in findings),
            key=lambda value: value["source_reference"]["start"],
        )
        assert [value["absence"]["location"] for value in observations] == list(
            locations
        )
        original_id = session.snapshot.documents[0].original_asset_id
        with session.open_payload(original_id) as stream:
            assert stream.read() == raw

    if backend == "brz":
        source = literal_archive(tmp_path / "source.brz", raw)
        with BrzSourceModule().open(source) as session:
            check(session)
    else:
        api = note_api(raw)
        with api_server(api) as (_, address):
            module = LocalApiSourceModule(
                LocalApiConfig(api_url=address),
                credentials=lambda: KEY,
                profile_version="4",
            )
            with module.open(LocalApiSourceRef(BRAIN)) as session:
                check(session)
                session.verify_consistency()
        assert not any(
            location in path for location in locations for path, _, _ in api.requests
        )


def test_actual_api_jpeg_alias_declaration_cannot_fall_through_to_undeclared_notice():
    location = IMAGE + ".jpeg"
    api = note_api(f"![Declared](.data/md-images/{location})\n".encode())
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, location, length=17)
    api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (
        404,
        {"error": "missing"},
    )
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(
            LocalApiConfig(api_url=address),
            credentials=lambda: KEY,
            profile_version="4",
        )
        with pytest.raises(MigrationRefused), module.open(LocalApiSourceRef(BRAIN)):
            pass
