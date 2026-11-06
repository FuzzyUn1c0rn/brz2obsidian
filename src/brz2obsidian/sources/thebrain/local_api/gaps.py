"""The reviewed TXT404 exception requires independently preserved owner PDF bytes."""

from brz2obsidian.contracts import SourceFinding

from .errors import refuse

RULE = "local-api.missing-txt-pdf.v1"


def gap_projections(assets, declarations, *, profile_version="1"):
    from .capture import canonical

    findings, decisions = [], []
    for asset in sorted(assets, key=lambda a: a.asset_id):
        if asset.availability != "absent":
            continue
        value = declarations[asset.asset_id]
        if profile_version == "4" and asset.role == "image":
            continue
        if (
            asset.role != "file"
            or value["type"] != 15
            or value["isNotes"] is not False
            or not value["location"].lower().endswith(".txt")
        ):
            refuse("Unavailable payload is outside the reviewed TXT exception")
        pdfs = sorted(
            a.asset_id
            for a in assets
            if a.owner == asset.owner
            and a.role == "file"
            and a.availability == "present"
            and declarations[a.asset_id]["type"] == 1
            and declarations[a.asset_id]["isNotes"] is False
            and declarations[a.asset_id]["location"].lower().endswith(".pdf")
            and a.actual_length is not None
            and a.actual_sha256 is not None
        )
        if not pdfs:
            refuse("Unavailable TXT lacks a qualified preserved same-owner PDF")
        keys = [asset.asset_id, *pdfs]
        decision_key = "scope:missing-txt404:" + asset.asset_id
        evidence = sorted("attachment:" + k for k in keys)
        decisions.append(
            {
                "key": decision_key,
                "rule_id": RULE,
                "outcome": "missing_txt404",
                "subjects": evidence,
                "evidence": sorted(evidence + ["payload:" + k for k in keys]),
            }
        )
        findings.append(
            SourceFinding(
                rule_id=RULE,
                kind="known_absent_payload",
                affected=(asset.asset_id,),
                evidence=tuple(sorted(evidence + [decision_key])),
                observed_json=canonical(
                    {
                        "asset_id": asset.asset_id,
                        "owner_id": asset.owner,
                        "filename": value["location"],
                        "retrieval": {"status": 404, "outcome": "missing_txt_404"},
                        "preserved_same_owner_pdf_ids": pdfs,
                    }
                ).decode("utf-8"),
            )
        )
    return findings, decisions


def validate_gap_audit(assets, audit, decisions, *, profile_version="1"):
    by_id = {a.asset_id: a for a in assets}
    absent = {
        asset.asset_id
        for asset in assets
        if asset.availability == "absent" and asset.role != "image"
    }
    if profile_version != "4" and any(
        request.outcome == "missing_image_404" for request in audit.requests
    ):
        refuse("Historical profiles do not admit image404")
    pdf_ids = {
        subject.removeprefix("attachment:")
        for decision in decisions
        for subject in decision["subjects"]
    } - absent
    outcomes = {}
    for request in audit.requests:
        if request.outcome == "missing_txt_404" and request.subject_id not in absent:
            refuse("A missing TXT request has no qualified absent asset")
        if request.operation == "attachment-content":
            outcomes.setdefault(request.subject_id, []).append(request)
    if not absent <= outcomes.keys() or any(
        r.status != 404 or r.outcome != "missing_txt_404" or r.actual_length != 0
        for key in absent
        for r in outcomes[key]
    ):
        refuse("Absent TXT is not bound to an exact classified HTTP404 retrieval")
    if not pdf_ids <= outcomes.keys() or any(
        r.status != 200
        or r.outcome != "success"
        or r.actual_length != by_id[key].actual_length
        for key in pdf_ids
        for r in outcomes[key]
    ):
        refuse("The qualification PDF lacks a complete measured HTTP200 retrieval")


def image_absence_facts(assets, declarations, requests, profile):
    """Bind declared absence to metadata200 and exactly one content404."""
    from .resources import role

    result = {}
    for asset in assets:
        if asset.role != "image" or asset.availability != "absent":
            continue
        value = declarations[asset.asset_id]
        content = [
            request
            for request in requests
            if request["operation"] == "attachment-content"
            and request["subject_id"] == asset.asset_id
        ]
        metadata = [
            request
            for request in requests
            if request["operation"] == "attachments"
            and request["subject_id"] == asset.asset_id
        ]
        if (
            profile != "4"
            or role(value, profile) != "image"
            or asset.owner != value["sourceId"]
            or asset.actual_length is not None
            or asset.actual_sha256 is not None
            or len(content) != 1
            or len(metadata) != 1
            or metadata[0]["status"] != 200
            or metadata[0]["outcome"] != "success"
            or content[0]["status"] != 404
            or content[0]["outcome"] != "missing_image_404"
            or content[0]["actual_length"] != 0
            or content[0]["brain_id"] != value["brainId"]
            or metadata[0]["brain_id"] != value["brainId"]
        ):
            refuse(
                "Unavailable image lacks exact qualified metadata200/content404 binding"
            )
        result[asset.asset_id] = {
            "basis": "api_declared_content404",
            "request_sequence": content[0]["sequence"],
            "metadata_sequence": metadata[0]["sequence"],
            "status": 404,
        }
    if any(
        request["outcome"] == "missing_image_404"
        and request["subject_id"] not in result
        for request in requests
    ):
        refuse("An image404 request has no qualified declared image")
    return result
