"""Deliberate, source-neutral explanations; arbitrary error text is never trusted."""

import unicodedata

from brz2obsidian.contracts import DiagnosticSubject

# A reason is admitted with its original code. The pair prevents a foreign rule
# or a familiar rule on an unrelated failure from inventing an explanation.
REASONS = {
    ("unsupported_feature", "note_html"): (
        "the converter does not support this HTML (web-page formatting) in a thought note.",
        "Report this limitation with the diagnostic report so the converter can be improved.",
    ),
    ("invalid_source", "note_target_missing"): (
        "a link in a thought note points to a thought that could not be found in this Brain.",
        "Open the thought note in TheBrain and check the link. If its target is present, report the problem with the diagnostic report.",
    ),
    ("invalid_reference", "note_target_missing"): (
        "a link in a thought note does not point to a live thought included in this Brain.",
        "Check the link in TheBrain. If its target is present, report the problem with the diagnostic report.",
    ),
    ("invalid_source", "note_encoding"): (
        "a thought note is not valid UTF-8, the text encoding required by this converter.",
        "Keep the original note and report this limitation with the diagnostic report.",
    ),
    ("invalid_source", "api_ownership"): (
        "the local API returned an item assigned to a different Brain or owner.",
        "Check that the selected Brain is correct. If it is, report the problem with the diagnostic report.",
    ),
    ("invalid_source", "api_response"): (
        "the local API returned data in a form the converter could not read.",
        "Check that the configured address is TheBrain's local API. If it is, report this limitation with the diagnostic report.",
    ),
    ("invalid_source", "thought_conflict"): (
        "the local API returned conflicting details for the same thought.",
        "Let changes in TheBrain finish, then inspect again. If the problem continues, report it with the diagnostic report.",
    ),
    ("invalid_source", "attachment_conflict"): (
        "the local API returned different details for the same attachment.",
        "Let changes in TheBrain finish, then inspect again. If the problem continues, report it with the diagnostic report.",
    ),
    ("invalid_source", "relationship_conflict"): (
        "the local API returned conflicting information about a relationship between thoughts.",
        "Let changes in TheBrain finish, then inspect again. If the problem continues, report it with the diagnostic report.",
    ),
    ("invalid_source", "relationship_unsupported"): (
        "the converter could not interpret a relationship between thoughts.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    ("invalid_source", "attachment_unsupported"): (
        "the converter could not interpret an attachment's type or details.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    ("invalid_source", "attachment_content"): (
        "an attachment's contents do not match a file format the converter can verify.",
        "Try opening the attachment in TheBrain. If it opens, report this converter limitation with the diagnostic report.",
    ),
    ("api_request_failed", "attachment_unavailable"): (
        "TheBrain's local API could not find a required attachment.",
        "Check that the attachment opens in TheBrain. If it opens, report the problem with the diagnostic report.",
    ),
    ("write_failure", "archive_missing"): (
        "the selected BRZ archive could not be found.",
        "Choose an existing BRZ archive and inspect it again.",
    ),
    ("write_failure", "source_access_denied"): (
        "the application does not have permission to read the selected BRZ archive.",
        "Choose an archive you can read or update its file permissions, then inspect again.",
    ),
    ("write_failure", "source_read_failed"): (
        "the selected BRZ archive could not be read.",
        "Check that the file is available and readable, then inspect again.",
    ),
    ("invalid_source", "archive_invalid"): (
        "the selected file could not be read as a supported BRZ archive.",
        "Check that this is a complete BRZ export from TheBrain. If it is, report this limitation with the diagnostic report.",
    ),
    ("invalid_source", "thought_metadata"): (
        "the converter could not interpret the details of a thought returned by the local API.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
}

_KNOWN_MESSAGES = {
    "HTML note content is outside reviewed Markdown coverage": "note_html",
    "HTML declarations are outside reviewed Markdown coverage": "note_html",
    "HTML processing instructions are outside reviewed Markdown coverage": "note_html",
    "A note reference has no included source target": "note_target_missing",
    "Local thought reference does not identify a live navigable thought": "note_target_missing",
    "Required authored text is not strict UTF-8": "note_encoding",
    "A required local API response is malformed": "api_response",
    "Local API JSON contains an invalid number": "api_response",
    "Accessible Brain inventory is malformed or exceeds its bound": "api_response",
    "Accessible Brain metadata is malformed": "api_response",
    "Source statistics have missing or foreign Brain ownership": "api_ownership",
    "A wildcard candidate has foreign or invalid ownership": "api_ownership",
    "An attachment declaration has foreign ownership": "api_ownership",
    "A relationship has foreign or invalid ownership": "api_ownership",
    "Repeated authoritative thought observations disagree": "thought_conflict",
    "Authoritative attachment declarations disagree": "attachment_conflict",
    "Graph and owned attachment inventories disagree": "attachment_conflict",
    "Repeated authoritative relationship observations disagree": "relationship_conflict",
    "Relationship endpoints do not agree with graph adjacency": "relationship_conflict",
    "A relationship is missing from its endpoint graph": "relationship_conflict",
    "An included relationship declaration is incomplete or unsupported": "relationship_unsupported",
    "An included relationship meaning is not qualified": "relationship_unsupported",
    "An attachment declaration is incomplete or unsupported": "attachment_unsupported",
    "Required image/icon bytes do not match the qualified signature": "attachment_content",
    "Required image/icon bytes are not fully decodable": "attachment_content",
    "Required JPEG image bytes cannot be decoded without recovery": "attachment_content",
    "Required PDF bytes do not match the qualified signature": "attachment_content",
    "Required ZIP bytes have no valid central directory": "attachment_content",
    "Required image bytes do not match the finite SVG qualification": "attachment_content",
    "Required icon bytes do not match the finite ICO qualification": "attachment_content",
    "Invalid BRZ data": "archive_invalid",
    "A required attachment was not found by the local API": "attachment_unavailable",
    "An authoritative thought has an unsupported declaration": "thought_metadata",
    "An authoritative thought role is not qualified": "thought_metadata",
    "An authored metadata value has an unsupported type": "thought_metadata",
    "An authored alias declaration is malformed": "thought_metadata",
    "An appearance declaration is not qualified": "thought_metadata",
    "An authoritative thought has foreign or conflicting ownership": "api_ownership",
    "A relationship colour is not qualified": "relationship_unsupported",
    "A relationship thickness is malformed": "relationship_unsupported",
    "An authored relationship value is malformed": "relationship_unsupported",
    "Graph adjacency is not completely explained by qualified relationships": "relationship_conflict",
    "Type field, graph type and assignment links disagree": "relationship_conflict",
}

# Broad codes remain compatible. Their explanation states only facts supported by
# that code; detailed causes require a reviewed (code, reason) above.
CODE_EXPLANATIONS = {
    "api_credentials_missing": (
        "the local API key has not been configured.",
        "Set THE_BRAIN_LOCAL_API_KEY in the application's launch environment or configure its credential provider, then try again.",
    ),
    "api_authentication_failed": (
        "TheBrain's local API denied access.",
        "Check the current API key in TheBrain settings and update THE_BRAIN_LOCAL_API_KEY or the credential provider, then try again.",
    ),
    "api_transport_failed": (
        "the connection to TheBrain's local API could not complete.",
        "Check that TheBrain is running, its local API is enabled and the configured address is correct, then try again.",
    ),
    "api_request_timeout": (
        "TheBrain's local API did not respond within the allowed time.",
        "Check that TheBrain is responding. Try again, or increase the request time limit if needed.",
    ),
    "api_request_failed": (
        "TheBrain's local API did not supply required data.",
        "Check that the selected Brain is available in TheBrain. If it is, report the problem with the diagnostic report.",
    ),
    "api_origin_refused": (
        "the API address did not connect to this computer.",
        "Use the local API address shown in TheBrain settings.",
    ),
    "api_redirect_refused": (
        "the API address redirected the request to another address.",
        "Use the direct local API address shown in TheBrain settings.",
    ),
    "api_search_shape_unsupported": (
        "the converter does not support the search results returned by the local API.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    "api_relationship_shape_unsupported": (
        "the converter does not support a relationship returned by the local API.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    "api_resource_shape_unsupported": (
        "the converter does not support an attachment description returned by the local API.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    "api_capture_cleanup_failed": (
        "the temporary copy used to read the Brain could not be removed.",
        "Check temporary-folder access and the reported vault publication status before another attempt.",
    ),
    "api_capture_failed": (
        "the temporary copy used to inspect the Brain could not be saved or verified. The underlying cause is not known.",
        "Check temporary-folder access and free disk space. If the problem continues, save the diagnostic report and report it.",
    ),
    "api_capture_read_failed": (
        "the temporary copy used to read the Brain could not be checked completely. The underlying cause is not known.",
        "Check temporary-folder access. Save the diagnostic report and report the problem if it continues.",
    ),
    "api_payload_read_failed": (
        "an attachment in the temporary copy of the Brain could not be read completely.",
        "Check temporary-folder access. Save the diagnostic report and report the problem if it continues.",
    ),
    "api_capture_storage_changed": (
        "the temporary storage changed while the Brain was being read.",
        "Inspect again to create a fresh temporary copy. Report the problem if it continues.",
    ),
    "api_acquisition_failed": (
        "reading the Brain through the local API did not complete. The underlying cause is not known.",
        "Check TheBrain and save the diagnostic report. Report the problem if it continues.",
    ),
    "api_listing_failed": (
        "reading the available Brain names did not complete. The underlying cause is not known.",
        "Check TheBrain and save the diagnostic report. Report the problem if it continues.",
    ),
    "api_acquisition_context_missing": (
        "the converter has no active copy of the Brain to read.",
        "Save the diagnostic report and report this converter problem.",
    ),
    "incomplete_source": (
        "the complete Brain could not be read within the configured acquisition limits.",
        "Review the local API time, size and request limits before inspecting again.",
    ),
    "invalid_source": (
        "the converter could not verify the Brain's data.",
        "The available details do not establish whether the cause is the Brain or a converter limitation. Report the problem with the diagnostic report.",
    ),
    "invalid_entry": (
        "the Brain does not identify a valid Home thought.",
        "Set Home to a live ordinary thought in TheBrain, then inspect again. For a BRZ archive, export it again first.",
    ),
    "invalid_reference": (
        "the converter could not safely prepare some of the Brain's content.",
        "Save the diagnostic report and report the problem. The available details do not establish whether the cause is the Brain or a converter limitation.",
    ),
    "unsupported_feature": (
        "the converter does not support a feature used by this Brain.",
        "Report this limitation with the diagnostic report so support can be assessed.",
    ),
    "unsupported_format": (
        "the converter does not support this source format with the selected conversion settings.",
        "Review the supported source formats and conversion settings. Report the limitation if you need this format.",
    ),
    "source_changed": (
        "the Brain or its retained copy changed while it was being read.",
        "Let edits finish, then inspect the current Brain again before conversion.",
    ),
    "review_changed": (
        "the Brain or conversion settings no longer match the inspection you reviewed.",
        "Inspect the current Brain again before conversion.",
    ),
    "missing_required_payload": (
        "required thought-note or attachment contents are unavailable in the BRZ archive.",
        "Check that the contents open in TheBrain, then export the Brain again. If they open there but are still absent from the export, report the problem with the diagnostic report.",
    ),
    "payload_read_failure": (
        "a required attachment could not be read completely.",
        "Check that it is available and opens in TheBrain, then inspect again. If it opens there, report the problem with the diagnostic report.",
    ),
    "operation_failure": (
        "an unexpected error occurred. The cause is not known.",
        "Save the diagnostic report and report the problem before trying again.",
    ),
    "session_teardown_failure": (
        "the application could not finish closing the source after reading it.",
        "Save the diagnostic report and report the problem. Check whether a vault was published before another conversion.",
    ),
    "target_path_too_long": (
        "a planned vault path exceeds the supported Windows path length.",
        "Choose a shorter output parent folder or vault name, then try conversion again.",
    ),
    "unsafe_target_path": (
        "a planned vault path is unsafe or conflicts with another path.",
        "Save the diagnostic report and report the problem. Use another destination if an existing folder link causes the conflict.",
    ),
    "unsafe_destination": (
        "the destination uses a folder link or another path that cannot be written safely.",
        "Choose a regular output folder without symbolic links or reparse points (Windows folder redirects).",
    ),
    "destination_not_empty": (
        "the destination is occupied or could not be confirmed empty.",
        "Choose a new or empty destination folder. Existing contents are never removed.",
    ),
    "write_failure": (
        "the vault could not be written or published.",
        "Check folder permissions and free disk space. Review the publication status, then choose a new or empty destination for another attempt.",
    ),
    "payload_integrity_failure": (
        "the prepared vault files did not pass the converter's integrity check.",
        "Keep the diagnostic report and report the problem. Check the publication status before another attempt.",
    ),
    "cleanup_failure": (
        "the temporary folder used to prepare the vault could not be removed.",
        "Check the reported leftover path and folder permissions. The application will not delete that folder or retry automatically. Review publication status before another attempt.",
    ),
    "publication_occurred": (
        "a verified vault was published before a later error occurred.",
        "Review that vault and the diagnostic report. Choose another destination for another conversion.",
    ),
    "invalid_source_configuration": (
        "the source selection or local API settings are invalid.",
        "Use a canonical Brain UUID with --source-kind local-api and valid API settings, or a BRZ archive without API options. Use --help for accepted options.",
    ),
}

WARNING_EXPLANATIONS = {
    "image_presentation_normalized": "An authored image width will be replaced by a responsive image that fits the available space. The exact percentage width will not be reproduced. Review the image's placement in the converted thought note.",
    "formatting_loss": "Some thought-note formatting needs review. Tables may become responsive, custom icons may use text labels, or an inserted element may be unsupported. Review the affected thought notes and the Migration report after conversion.",
    "absent_payload": "An attachment is unavailable. Review the source warnings before conversion; the converter cannot preserve bytes it could not read.",
    "source_gap": "Some Brain content is unavailable. Review the source warnings before conversion; the converter cannot preserve content it could not read.",
    "approved_source_gap": "Some thought-note, icon or attachment bytes are unavailable. Conversion will describe these missing contents in the Migration report. Review these warnings before continuing.",
    "approved_metadata_discrepancy": "An attachment's recorded details differ from its available bytes. Conversion preserves the verified available bytes. Review the Migration report for the difference.",
}

KNOWN_CODES = set(CODE_EXPLANATIONS) | set(WARNING_EXPLANATIONS)


def diagnostic_reason(code, message):
    """Translate only explicitly reviewed internal literals into reason IDs."""
    reason = _KNOWN_MESSAGES.get(message)
    return "diagnostic." + reason if (code, reason) in REASONS else None


def diagnosed_issue(issue):
    """Retain the structured source fact and give it the same safe guidance."""
    if issue.rule_id is None:
        issue = issue.model_copy(
            update={"rule_id": diagnostic_reason(issue.code, issue.message)}
        )
    guidance = explain_issue(issue, "inspect").removeprefix(
        "Inspection stopped because "
    )
    return issue.model_copy(update={"guidance": guidance[0].upper() + guidance[1:]})


def explain_issue(issue, operation):
    """Return an operation, supported cause and action, without exception text."""
    prefix = {
        "inspect": "Inspection stopped",
        "convert": "Conversion stopped",
        "list_brains": "The Brain list could not be read",
    }[operation]
    if issue.severity == "warning":
        prefix = {
            "inspect": "Inspection found a warning",
            "convert": "Conversion reported a warning",
            "list_brains": "Brain listing reported a warning",
        }[operation]
    reason = (
        (issue.rule_id or "").removeprefix("diagnostic.")
        if (issue.rule_id or "").startswith("diagnostic.")
        else None
    )
    admitted_reason = reason if (issue.code, reason) in REASONS else None
    explanation = REASONS.get((issue.code, admitted_reason)) or CODE_EXPLANATIONS.get(
        issue.code
    )
    cause, action = explanation or (
        "an error occurred, but its cause could not be identified.",
        "Save the diagnostic report and report the problem before trying again.",
    )
    context = ""
    if issue.subject is not None:
        label = {
            "item": "Thought note"
            if admitted_reason in {"note_html", "note_encoding", "note_target_missing"}
            else "Thought",
            "document": "Thought note",
            "asset": "Attachment",
            "relationship": "Relationship",
        }[issue.subject.kind]
        context = f' {label}: "{issue.subject.name}".'
    if issue.code in WARNING_EXPLANATIONS:
        return WARNING_EXPLANATIONS[issue.code] + context
    return f"{prefix} because {cause}{context} {action}"


def diagnostic_subject(kind, name):
    """Admit bounded display metadata; omit URI-like and secret labels."""
    if not isinstance(name, str):
        return None
    printable = "".join(
        char for char in name if not unicodedata.category(char).startswith("C")
    ).strip()[:120]
    if not printable or any(
        token in value.casefold()
        for value in (name, printable)
        for token in ("://", "token=", "key=", "password=", "authorization:")
    ):
        return None
    return DiagnosticSubject(kind=kind, name=printable)


def with_subject(error, kind, name):
    """Attach admitted metadata while preserving an earlier explicit subject."""
    subject = diagnostic_subject(kind, name)
    if subject is None:
        return error
    return type(error)(
        tuple(
            issue.model_copy(update={"subject": subject})
            if issue.subject is None
            else issue
            for issue in error.issues
        ),
        receipt=error.receipt,
    )


def contextual_issue(issue, snapshot):
    """Use the first admitted affected label from qualified snapshot metadata."""
    if issue.subject is not None or snapshot is None:
        return issue
    affected = set(issue.affected)
    items = {item.key: item for item in snapshot.items}
    candidates, original_assets = [], set()
    for document in snapshot.documents:
        if document.key in affected:
            if document.owner in items:
                candidates.append(("document", items[document.owner].title))
            if document.original_asset_id is not None:
                original_assets.add(document.original_asset_id)
    for asset in snapshot.assets:
        if asset.asset_id in affected | original_assets:
            candidates.extend(
                (("asset", asset.display_name), ("asset", asset.original_name))
            )
    for relationship in snapshot.relationships:
        endpoints = (relationship.item_a, relationship.item_b)
        if relationship.key in affected and all(key in items for key in endpoints):
            candidates.append(
                ("relationship", " \u2014 ".join(items[key].title for key in endpoints))
            )
    candidates.extend(
        ("item", item.title) for item in snapshot.items if item.key in affected
    )
    for kind, name in candidates:
        subject = diagnostic_subject(kind, name)
        if subject is not None:
            return issue.model_copy(update={"subject": subject})
    return issue
