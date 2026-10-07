"""Recheck the bounded native experiments without publishing source records.

Run with the project's .venv interpreter. This is evidence tooling, not a
source acceptance rule or production parser. JSON lines split only at LF.
"""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def records(archive, name):
    return [
        json.loads(line)
        for line in archive.read(name).decode("utf-8-sig").split("\n")
        if line.strip()
    ]


def snapshot(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "ZIP CRC failure"
        thoughts = records(archive, "thoughts.json")
        links = records(archive, "links.json")
        attachments = records(archive, "attachments.json")
        by_name = {thought["Name"]: thought for thought in thoughts}
        definition = by_name["V2_TYPE_CONTROL"]
        assert definition["Kind"] == 2
        members = [t for t in thoughts if t.get("TypeId") == definition["Id"]]
        for member in members:
            assignments = [
                link for link in links
                if link["ThoughtIdA"] == definition["Id"]
                and link["ThoughtIdB"] == member["Id"]
                and tuple(link.get(k) for k in ("Kind", "Relation", "Meaning", "Direction"))
                == (1, 1, 2, -1)
            ]
            assert len(assignments) == 1, "Assignment join differs from observed fixture"
        selected = {}
        for name in ("V2_TYPE_CONTROL", "CHILD", "PEER"):
            thought = by_name[name]
            icons = [a for a in attachments if a.get("SourceId") == thought["Id"] and a.get("IsIcon")]
            for icon in icons:
                payload = thought["Id"] + "/.data/" + icon["Location"]
                assert payload in archive.namelist()
                assert len(archive.read(payload)) == icon["DataLength"]
            selected[name] = {
                "kind": thought["Kind"],
                "assigned": thought.get("TypeId") == definition["Id"],
                "label": thought.get("Label"),
                "foreground": thought.get("ForegroundColor"),
                "background": thought.get("BackgroundColor"),
                "icon_info": thought.get("ThoughtIconInfo"),
                "owned_icon_count": len(icons),
                "owned_icon_bytes": [icon["DataLength"] for icon in icons],
            }
        return {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "zip_crc": "passed",
            "assignment_count": len(members),
            "thoughts": selected,
        }


def source_summary(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "Source ZIP CRC failure"
        meta = json.loads(archive.read("meta.json"))
        attachments = records(archive, "attachments.json")
        by_id = {a["Id"]: a for a in attachments}
        text_records = [a for a in attachments if a.get("Type") == 15]
        pairs = []
        for text in text_records:
            pdf = by_id.get(Path(text["Location"]).stem)
            assert pdf is not None and pdf["Location"].lower().endswith(".pdf")
            assert pdf["SourceId"] == text["SourceId"]
            txt_payload = text["SourceId"] + "/" + text["Location"]
            pdf_payload = pdf["SourceId"] + "/" + pdf["Location"]
            assert txt_payload not in archive.namelist()
            assert not any(
                n == text["Location"] or n.endswith("/" + text["Location"])
                for n in archive.namelist()
            )
            assert pdf_payload in archive.namelist()
            assert len(archive.read(pdf_payload)) == pdf["DataLength"]
            state = meta["AttachmentFileStates"][text["Id"]]
            assert text["DataLength"] == 0 and text["NoteType"] == 0 and state == 2
            pairs.append({
                "txt_absent": True,
                "declared_length": text["DataLength"],
                "file_state": state,
                "pdf_present": True,
            })
        videos = [a for a in attachments if a.get("Type") == 3 and a.get("VideoHtml")]
        return {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "zip_crc": "passed",
            "txt_pdf_identity_pairs": pairs,
            "url_records_with_video_html": len(videos),
        }


def pdf_control_summary(path, previous_path, original_pdf):
    """Check the observed PDF/TXT association without inferring missing bytes."""
    with zipfile.ZipFile(previous_path) as previous:
        old_ids = {a["Id"] for a in records(previous, "attachments.json")}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "PDF control ZIP CRC failure"
        meta = json.loads(archive.read("meta.json"))
        attachments = records(archive, "attachments.json")
        new = [a for a in attachments if a["Id"] not in old_ids]
        assert len(new) == 2, "Expected only the uploaded PDF and its TXT declaration"
        pdfs = [a for a in new if a.get("Location") == "pdf-control.pdf"]
        texts = [a for a in new if a.get("Type") == 15]
        assert len(pdfs) == len(texts) == 1
        pdf, text = pdfs[0], texts[0]
        assert pdf["Type"] == 1 and pdf["NoteType"] == text["NoteType"] == 0
        assert text["SourceId"] == pdf["SourceId"]
        assert text["Location"] == pdf["Id"] + ".txt"
        assert text["DataLength"] == 37
        assert meta["AttachmentFileStates"][pdf["Id"]] == 1
        assert meta["AttachmentFileStates"][text["Id"]] == 2
        pdf_payload = pdf["SourceId"] + "/" + pdf["Location"]
        pdf_bytes = archive.read(pdf_payload)
        assert pdf_bytes == original_pdf.read_bytes()
        assert len(pdf_bytes) == pdf["DataLength"] == 611
        assert not any(
            n == text["Location"] or n.endswith("/" + text["Location"])
            for n in archive.namelist()
        )
        sentinel = b"V2PDFCONTROL7429"
        assert sentinel in pdf_bytes
        assert all(
            sentinel not in archive.read(n)
            for n in archive.namelist() if n != pdf_payload
        ), "Search sentinel also appears in another exported resource"
        return {
            "pdf_byte_equal_to_uploaded_file": True,
            "pdf_bytes": len(pdf_bytes),
            "pdf_file_state": 1,
            "new_attachment_records": len(new),
            "txt_type": text["Type"],
            "txt_note_type": text["NoteType"],
            "txt_stem_matches_pdf_attachment_identity": True,
            "txt_same_owner_as_pdf": True,
            "txt_declared_length": text["DataLength"],
            "txt_file_state": 2,
            "txt_payload_present": False,
            "sentinel_in_other_exported_resources": False,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    result = {}
    paths = {}
    for stage in ("baseline", "overrides", "reset", "icon-reset", "pdf-import"):
        matches = list((args.evidence_directory / stage).glob("*.brz"))
        assert len(matches) == 1, "Expected one archive per experiment stage"
        paths[stage] = matches[0]
        result[stage] = snapshot(matches[0])
    baseline = result["baseline"]["thoughts"]["CHILD"]
    override = result["overrides"]["thoughts"]["CHILD"]
    reset = result["reset"]["thoughts"]["CHILD"]
    for field in ("label", "foreground", "background"):
        assert baseline[field] is None and override[field] is not None and reset[field] is None
    assert baseline["owned_icon_count"] == 0
    assert override["owned_icon_count"] == reset["owned_icon_count"] == 1
    icon_reset = result["icon-reset"]["thoughts"]["CHILD"]
    assert icon_reset["owned_icon_count"] == 0
    assert icon_reset["icon_info"] == baseline["icon_info"]
    assert icon_reset["assigned"]
    for field in ("label", "foreground", "background"):
        assert icon_reset[field] is None
    for name, before in result["icon-reset"]["thoughts"].items():
        after = result["pdf-import"]["thoughts"][name]
        for field, value in before.items():
            if name == "CHILD" and field == "icon_info":
                assert after[field] == "4:pdf-control.pdf:1:False:False:0:"
            else:
                assert after[field] == value
    assert result["pdf-import"]["assignment_count"] == result["icon-reset"]["assignment_count"]
    result["pdf-import"]["pdf_control"] = pdf_control_summary(
        paths["pdf-import"], paths["icon-reset"], args.evidence_directory / "pdf-control.pdf"
    )
    if args.source:
        result["source"] = source_summary(args.source)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
