"""Unavailable local image policy through public source sessions."""

import json
import tempfile
from contextlib import closing
from hashlib import sha256

import pytest

from brz2obsidian.sources.thebrain import BrzSourceModule
from brz2obsidian.contracts import MigrationRefused
from brz2obsidian.sources.thebrain.local_api import (
    LocalApiConfig, LocalApiSession, LocalApiSourceModule, LocalApiSourceRef,
)
from tests.sources.test_local_api_bom import note_api
from tests.support.local_api import BRAIN, HOME, KEY, api_server
from tests.application.test_literal_angles_workflow import literal_archive
from tests.application.test_forgotten_workflow import rewrite
from tests.support.local_api_payloads import PNG, IMAGE, attachment


def test_two_missing_images_keep_four_present_controls_and_exact_original(tmp_path):
    missing = "![Lost](.data/md-images/lost.png)"
    sized = "![Sized](.data/md-images/sized.png#$width=70p$)"
    controls = [f"![Kept {i}](.data/md-images/kept{i}.png)" for i in range(4)]
    raw = ("Café *before*.\r\n" + missing + "\r\n" + "\r\n".join(controls) + "\r\n" + sized + "\r\nAfter.\r\n").encode()
    source = literal_archive(
        tmp_path / "source.brz",
        raw,
        resources=tuple(({"Type": 12, "Location": f"kept{i}.png"}, PNG) for i in range(4)),
    )
    expected = raw.decode().replace(missing, "Image unavailable: Lost").replace(sized, "Image unavailable: Sized")
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [(edit.kind, edit.before, edit.after) for edit in document.text_adaptations] == [
            ("image_unavailable", missing, "Image unavailable: Lost"),
            ("image_unavailable", sized, "Image unavailable: Sized"),
        ]
        assert all(edit.source_digest == sha256(raw).hexdigest() for edit in document.text_adaptations)
        assert [reference.expected_original for reference in document.references] == controls
        findings = [f for f in session.snapshot.findings if f.kind == "unavailable_image_reference"]
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


def test_current_api_unavailable_image_without_companions_replays_exact_bom(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    raw = b"\xef\xbb\xbfBefore ![Lost](.data/md-images/lost.png) after.\r\n"
    api = note_api(raw)
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(LocalApiConfig(api_url=address), credentials=lambda: KEY, profile_version="4")
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            document = session.snapshot.documents[0]
            assert document.text == "Before Image unavailable: Lost after.\r\n"
            assert [e.kind for e in document.text_adaptations] == ["literal_text", "image_unavailable"]
            payloads = {}
            for asset in session.snapshot.assets:
                if asset.availability == "present":
                    with session.open_payload(asset.asset_id) as stream:
                        payloads[asset.asset_id] = stream.read()
            assert payloads[document.original_asset_id] == raw
            capture = next(tmp_path.glob("brz2obsidian-api-*"))
            source = json.loads((capture / "source.json").read_bytes())
            audit = json.loads((capture / "audit.json").read_bytes())
            with closing(LocalApiSession(source=source, snapshot=session.snapshot, audit=audit,
                                 payloads=payloads, profile_version="4")) as replay:
                assert replay.snapshot == session.snapshot
                replay.verify_consistency()
    assert not any("lost.png" in path for path, _, _ in api.requests)


def test_two_identical_missing_images_inside_rewritten_row_keep_generated_code(tmp_path):
    missing = "![Lost](.data/md-images/lost.png)"
    raw = (f"Café <X/>\r\n\r\n|{missing}|{missing}|`x|y`|:(table=\"column-widths:-1,0,0,0;justification:default\"):\r\n|a|b|c|\r\n").encode()
    expected = "Café \\<X/>\r\n\r\n| | | |\n|---|---|---|\n|Image unavailable: Lost|Image unavailable: Lost|<code>x&#124;y</code>|\r\n|a|b|c|\r\n"
    source = literal_archive(tmp_path / "source.brz", raw)
    with BrzSourceModule().open(source) as session:
        document = session.snapshot.documents[0]
        assert document.text == expected
        assert [e.kind for e in document.text_adaptations] == ["literal_text", "markdown_insert_image_unavailable"]
        occurrences = [json.loads(f.observed_json) for f in session.snapshot.findings if f.kind == "unavailable_image_reference"]
        assert len(occurrences) == 2
        assert [o["source_reference"]["start"] for o in occurrences] == [raw.decode().index(missing), raw.decode().index(missing) + len(missing) + 1]
        assert occurrences[0]["notice"]["end"] < occurrences[1]["notice"]["start"]
        assert all(o["composition"]["base_edits"][0]["kind"] == "markdown_insert" for o in occurrences)
        assert document.references == ()
        restored = document.text
        for edit in reversed(document.text_adaptations):
            restored = restored[:edit.adapted_start] + edit.before + restored[edit.adapted_end:]
        assert restored.encode() == raw


def test_heading_toc_and_callout_keep_contained_literals_and_notice_occurrence(tmp_path):
    phrase = "![Lost <X/>](.data/md-images/lost.png)"
    raw = f"[/toc/]\n\n# {phrase}\n\n> [!tip|icon:😂] {phrase}\n> Body\n".encode()
    with BrzSourceModule().open(literal_archive(tmp_path / "source.brz", raw)) as session:
        document = session.snapshot.documents[0]
        assert "# Image unavailable: Lost &#60;X&#47;&#62; ^brz-toc-heading-1" in document.text
        assert "> [!tip] 😂 Image unavailable: Lost &#60;X&#47;&#62;" in document.text
        assert document.text.count("Image unavailable:") == 2
        occurrences = [json.loads(f.observed_json) for f in session.snapshot.findings if f.kind == "unavailable_image_reference"]
        assert len(occurrences) == 2
        assert all(o["source_reference"]["before"] == phrase for o in occurrences)
        assert all(e.kind != "literal_text" for e in document.text_adaptations)


@pytest.mark.parametrize("profile", ("1", "2", "3"))
def test_historical_api_profiles_keep_missing_image_refusal(profile):
    api = note_api(b"![Lost](.data/md-images/lost.png)\n")
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(LocalApiConfig(api_url=address), credentials=lambda: KEY, profile_version=profile)
        with pytest.raises(MigrationRefused, match="one preserved owner image"), module.open(LocalApiSourceRef(BRAIN)):
            pass


@pytest.mark.parametrize("referenced", (True, False))
def test_declared_archive_state3_image_needs_active_reference_and_has_no_measured_bytes(tmp_path, referenced):
    raw = b"![Lost](.data/md-images/lost.png)\n" if referenced else b"Plain note.\n"
    source = literal_archive(tmp_path / "source.brz", raw, resources=(({
        "Type":12,"Location":"lost.png","DataLength":17},None),))
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
        assert (image.availability,image.actual_length,image.actual_sha256) == ("absent",None,None)
        assert session.snapshot.documents[0].text == "Image unavailable: Lost\n"
        finding = next(f for f in session.snapshot.findings if f.kind == "unavailable_image_reference")
        assert finding.affected == (image.asset_id,)
        assert json.loads(finding.observed_json)["absence"] == {
            "basis":"archive_declared_state3_no_payload","location":"lost.png",
            "asset_id":image.asset_id,"state":3,
        }


def test_current_api_declared_image_content404_is_classified_and_reference_bound():
    api = note_api(f"![Lost](.data/md-images/{IMAGE}.png)\n".encode())
    api.attachments[IMAGE] = attachment(IMAGE, HOME, 12, IMAGE + ".png", length=123)
    api.overrides[f"/api/attachments/{BRAIN}/{IMAGE}/file-content"] = (404, {"error":"not retained"})
    with api_server(api) as (_, address):
        module = LocalApiSourceModule(LocalApiConfig(api_url=address), credentials=lambda: KEY, profile_version="4")
        with module.open(LocalApiSourceRef(BRAIN)) as session:
            image = next(a for a in session.snapshot.assets if a.role == "image")
            assert (image.availability,image.actual_length,image.actual_sha256) == ("absent",None,None)
            finding = next(f for f in session.snapshot.findings if f.rule_id == "thebrain.unavailable-declared-image.v1")
            assert finding.affected == (IMAGE,)
            assert json.loads(finding.observed_json)["absence"]["basis"] == "api_declared_content404"
            assert session.snapshot.documents[0].text == "Image unavailable: Lost\n"
            session.verify_consistency()
