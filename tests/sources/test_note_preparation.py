"""Thought-note preparation interactions through the two-phase source interface."""

from brz2obsidian.contracts import Asset, Issue, MigrationRefused
from brz2obsidian.sources.thebrain.note_preparation import prepare_note

OWNER = "11111111-1111-4111-8111-111111111111"
ASSET = "33333333-3333-4333-8333-333333333333"
IMAGE = "44444444-4444-4444-8444-444444444444"
EXCLUDED = "00000000-0000-0000-0000-000000000000"
EXCLUDED_URI = "brain://AAAAAAAAAAAAAAAAAAAAAA/title"
INCLUDED = "00000000-0000-0000-0000-000000000001"
INCLUDED_URI = "brain://AAAAAAAAAAAAAAAAAAAAAQ/title"
POINTER = "attachments.json:0"
MEMBER = OWNER + "/Notes.md"
HELPER_GUIDANCE = "Use supported same-Brain inline Markdown references to live thoughts and archived images, then re-export."


def source_refuse(code, message, affected=(), *, evidence=(), guidance=None):
    raise MigrationRefused(
        (
            Issue(
                code=code,
                phase="source",
                message=message,
                affected=affected,
                evidence=evidence,
                guidance=guidance,
            ),
        )
    )


def prepare(text):
    return prepare_note(
        text,
        owner=OWNER,
        asset_id=ASSET,
        pointer=POINTER,
        member=MEMBER,
        excluded=(EXCLUDED,),
        scope_tokens=(EXCLUDED,),
        source_refuse=source_refuse,
    )


def image_asset(*, owner=OWNER, availability="present"):
    return Asset(
        asset_id=IMAGE,
        owner=owner,
        naming_seed="4444",
        original_name="p.png",
        role="image",
        availability=availability,
    )
