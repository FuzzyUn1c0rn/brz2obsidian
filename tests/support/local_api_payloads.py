"""Synthetic owned payload declarations, independently fixed at HTTP boundary."""

import json
from pathlib import Path

from tests.support.local_api import BRAIN, HOME, MetadataApi
from tests.support.local_api_graph import DEFINITION, CompleteGraphApi

NOTE = "a1111111-1111-4111-8111-111111111111"
RAW_NOTE = b"Authored caf\xc3\xa9.\r\n\r\nExact source newline.\r\n"
FILE = "a2222222-2222-4222-8222-222222222222"
PNG = (
    Path(__file__).parents[1] / "fixtures/local_api_acceptance/red-pixel.png"
).read_bytes()
JPEG = (
    Path(__file__).parents[1] / "fixtures/local_api_acceptance/red-pixel.jpg"
).read_bytes()
IMAGE = "a3333333-3333-4333-8333-333333333333"
TYPE_ICON = "a4444444-4444-4444-8444-444444444444"
DIRECT_ICON = "a5555555-5555-4555-8555-555555555555"
WEBSITE = "a6666666-6666-4666-8666-666666666666"
URI = "https://example.invalid/Path?authored=value&token=AUTHORED_QUERY#part"
RICH_NOTE = (
    "# Authored\r\n\r\n![Red](.data/md-images/"
    + IMAGE
    + ".png)\r\n\r\n[Alone](brain://MzMzMzMzM0ODMzMzMzMzMw/Alone)\r\n"
).encode("utf-8")


def attachment(identity, owner, kind, location, *, is_notes=False, length=0):
    return {
        "id": identity,
        "brainId": BRAIN,
        "sourceId": owner,
        "sourceType": 2,
        "type": kind,
        "isNotes": is_notes,
        "location": location,
        "name": None,
        "position": 0,
        "dataLength": length,
    }


class PayloadApi(MetadataApi):
    def __init__(self):
        super().__init__()
        note = attachment(
            NOTE, HOME, 1, "Notes.md", is_notes=True, length=len(RAW_NOTE)
        )
        self.attachments = {NOTE: note}
        self.payloads = {NOTE: RAW_NOTE}

    def response(self, path, query):
        if path in self.overrides:
            return super().response(path, query)
        for key in self.thoughts:
            owned = [a for a in self.attachments.values() if a["sourceId"] == key]
            if path == f"/api/thoughts/{BRAIN}/{key}/attachments":
                return 200, owned
            if path == f"/api/thoughts/{BRAIN}/{key}/graph":
                status, graph = super().response(path, query)
                return status, dict(graph, attachments=owned)
        for key, value in self.attachments.items():
            if path == f"/api/attachments/{BRAIN}/{key}/metadata":
                return 200, value
            if path == f"/api/attachments/{BRAIN}/{key}/file-content":
                return 200, self.payloads[key]
        return super().response(path, query)


class FilePayloadApi(PayloadApi):
    def __init__(self):
        super().__init__()
        self.attachments[FILE] = attachment(
            FILE, HOME, 1, "generic.png", length=len(PNG)
        )
        self.payloads[FILE] = PNG


class RichPayloadApi(PayloadApi, CompleteGraphApi):
    def __init__(self, *, explicit=False, jpeg=False):
        super().__init__()
        self.payloads[NOTE] = RICH_NOTE
        self.attachments[NOTE]["dataLength"] = len(RICH_NOTE)
        for key, owner, kind, location in (
            (IMAGE, HOME, 12, IMAGE + ".png"),
            (TYPE_ICON, DEFINITION, 5, "Icon.png"),
            (WEBSITE, HOME, 3, URI),
        ):
            self.attachments[key] = attachment(
                key, owner, kind, location, length=len(PNG)
            )
            if kind != 3:
                self.payloads[key] = PNG
        if explicit:
            self.attachments[DIRECT_ICON] = attachment(
                DIRECT_ICON, HOME, 5, "Icon.png", length=len(PNG)
            )
            self.payloads[DIRECT_ICON] = PNG
        if jpeg:
            self.payloads[TYPE_ICON] = JPEG
        self.attachments[FILE] = attachment(
            FILE, HOME, 1, "generic.png", length=len(PNG)
        )
        self.payloads[FILE] = PNG


def assert_published_payloads(destination, *, explicit=False, jpeg=False):
    """Literal profile-derived vault assertions, shared by public delivery seams."""
    record = json.loads((destination / "migration-record.json").read_bytes())
    items = {t["item_key"]: t for t in record["item_targets"]}
    assert record["profile_version"] == "2"
    assert items[HOME]["icon_snapshot"]["effective_icon_asset_id"] == (
        DIRECT_ICON if explicit else TYPE_ICON
    )
    assert items[DEFINITION]["declared_appearance"]["icon_asset_id"] == TYPE_ICON
    assert (
        destination / "Attachments/22222222/Notes.md.original"
    ).read_bytes() == RICH_NOTE
    assert (destination / f"Attachments/22222222/{IMAGE}.png").read_bytes() == PNG
    assert (destination / "Attachments/22222222/generic.png").read_bytes() == PNG
    assert (
        destination / "Attachments/40000000000040008000000000000001/Icon.png"
    ).read_bytes() == (JPEG if jpeg else PNG)
    if explicit:
        assert (destination / "Attachments/22222222/Icon.png").read_bytes() == PNG
    text = (destination / "Home — Entry.md").read_text(encoding="utf-8")
    assert f"![Red](Attachments/22222222/{IMAGE}.png)" in text
    assert "[[Notes/Alone.md|Alone]]" in text
    assert "[[Attachments/22222222/generic.png" in text
    assert "![[Attachments/22222222/generic.png" not in text
    assert URI in text
    assert "CANARY" not in json.dumps(record)


TXT = "a7777777-7777-4777-8777-777777777777"
PDF = "a8888888-8888-4888-8888-888888888888"
PDF_BYTES = b"%PDF-1.7\r\nIndependent preserved PDF control.\r\n%%EOF\r\n"


class MissingTxtPdfApi(PayloadApi):
    def __init__(self):
        super().__init__()
        self.attachments[TXT] = attachment(TXT, HOME, 15, "authored.txt", length=987)
        self.attachments[PDF] = attachment(
            PDF, HOME, 1, "different-purpose.pdf", length=len(PDF_BYTES)
        )
        self.payloads[PDF] = PDF_BYTES
        self.overrides[f"/api/attachments/{BRAIN}/{TXT}/file-content"] = (
            404,
            b"REMOTE_ERROR_BODY_CANARY " + b"SERVICE_TOKEN_CANARY",
        )


def assert_published_txt_pdf_gap(destination):
    assert (
        destination / "Attachments/22222222/different-purpose.pdf"
    ).read_bytes() == PDF_BYTES
    assert not list(destination.rglob("*.txt"))
    note = (destination / "Home — Entry.md").read_text(encoding="utf-8")
    assert "Absent source file: authored.txt" in note
    assert "[[Attachments/22222222/different-purpose.pdf" in note
    assert "authored.txt|" not in note
    report = (destination / "MIGRATION REPORT.md").read_text(encoding="utf-8")
    assert "Conversion used captured source material only." in report
    assert "convert the updated source into a fresh vault" in report
    assert TXT in report and PDF in report
    record = json.loads((destination / "migration-record.json").read_bytes())
    absent = next(a for a in record["asset_targets"] if a["asset_id"] == TXT)
    assert absent["owner"] == HOME and absent["availability"] == "absent"
    assert absent["relative_path"] is absent["resource_link"] is None
    assert absent["actual_length"] is absent["actual_sha256"] is None
    assert absent["source_findings"][0]["rule_id"] == "local-api.missing-txt-pdf.v1"
    assert "CANARY" not in note + report + json.dumps(record)
