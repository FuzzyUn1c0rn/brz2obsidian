"""Prepare thought-note facts, then bind them against the complete inventory."""

import hashlib
import json

from brz2obsidian.contracts import Document, MigrationRefused, SourceFinding

from .inserts import INSERT_RULE, adapt_note, trace_adapted_references
from .literals import adapt_literals, source_position
from .notes import bind_note_references, compact_thought_identity, trace_note_references
from .scope import contains_omitted_identity


def prepare_note(
    text,
    *,
    owner,
    asset_id,
    pointer,
    member,
    excluded=(),
    scope_tokens=(),
    source_refuse,
):
    """Return a prepared Document and its formatting-loss findings.

    Qualify original references before exclusion, then adapt and trace scoped
    text afresh. Exact edits describe scoped text; references describe final
    text. Original-copy eligibility is decided before removing references.
    """
    findings = []
    try:
        adapted, text_adaptations = adapt_literals(text)
        references = trace_note_references(adapted, excluded)
    except MigrationRefused as error:
        issue = error.issues[0]
        source_refuse(
            issue.code,
            issue.message,
            (owner, asset_id),
            evidence=(pointer, "payload:" + member),
            guidance="Review the affected thought-note Markdown and its preserved source evidence; unsupported HTML or reference syntax must be resolved before retrying.",
        )
    removals = []
    for reference in references:
        if reference.kind == "item":
            target = compact_thought_identity(reference.target)
            if target in excluded:
                removals.append(reference)
    unsafe_original = bool(removals) or contains_omitted_identity(text, scope_tokens)
    for reference in reversed(removals):
        begin = source_position(reference.start, text_adaptations)
        end = source_position(reference.end, text_adaptations)
        text = text[:begin] + text[end:]
    if contains_omitted_identity(text, scope_tokens):
        source_refuse(
            "invalid_reference",
            "Note contains an excluded association outside removable references",
            (owner, asset_id),
            evidence=(pointer, "meta.json"),
            guidance="Review this attachment's declared role and owned archive payload.",
        )
    try:
        adapted, text_adaptations, insert_losses = adapt_note(text)
        references = trace_adapted_references(adapted, text_adaptations)
    except MigrationRefused as error:
        issue = error.issues[0]
        source_refuse(
            issue.code,
            issue.message,
            (owner, asset_id),
            evidence=(pointer,),
            guidance=issue.guidance,
        )
    for loss in insert_losses:
        findings.append(
            SourceFinding(
                kind="formatting_loss",
                rule_id=INSERT_RULE,
                affected=(owner, asset_id),
                observed_json=json.dumps(loss, ensure_ascii=False),
                evidence=(pointer,),
            )
        )
    text = adapted
    document = Document(
        key=asset_id,
        owner=owner,
        text=text,
        text_digest=hashlib.sha256(text.encode()).hexdigest(),
        original_asset_id=None if unsafe_original else asset_id,
        original_copy_omitted=unsafe_original,
        references=references,
        text_adaptations=text_adaptations,
        evidence=(pointer,),
    )
    return document, tuple(findings)


def bind_prepared_notes(documents, assets, thoughts, source_refuse):
    """Bind prepared documents after all owned assets have been inventoried.

    Preserve document evidence and fixed binding guidance for typed refusals.
    """
    bound_documents = []
    for document in documents:
        try:
            bound_documents.append(bind_note_references(document, assets, thoughts))
        except MigrationRefused as error:
            issue = error.issues[0]
            source_refuse(
                issue.code,
                issue.message,
                (document.owner, document.key),
                evidence=document.evidence,
                guidance="Review the affected thought-note Markdown and declared local references before retrying.",
            )
    return bound_documents
