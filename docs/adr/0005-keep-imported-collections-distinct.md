---
status: accepted
---

# Keep imported collections distinct in existing vaults

When first importing an unrelated Brain into an existing vault, default to a
user-selectable folder such as `Imports/Brain name/`, initially keeping its notes,
attachments and support files together. Users can reorganize later, with source
identity allowing subsequent updates to follow moved notes. Preserve existing
link meanings, including intentionally uncreated targets, by choosing distinct
incoming filenames where necessary; folder separation alone is not sufficient.
Connecting existing links to imported content requires an explicit choice.

When another Brain is first imported, keep its vault tags distinct by default
with a readable Brain prefix. Offer reuse of an existing vault tag as an explicit
mapping, and preserve established mappings through later updates.

Support the user's choice to keep an incoming category separate or integrate it
with an existing vault category. This category-mapping capability is included
when arbitrary-vault imports are introduced. Choose separately for each incoming
category, offering creation of a separate category or selection of an existing
vault category. Matching names may suggest candidates but require confirmation.
Remember the mappings for later updates.

Sharing a category initially combines membership. Preserve the source category's
prose and attachments in a separate imported reference note linked to the shared
category. Combining category-note bodies requires additional ownership and
conflict rules and is outside this initial integration.

Initially support category notes with the converter's existing linked-membership
convention through the `categories` property. Allow selection of an existing
category note, explain incompatibility with its current dashboard and offer a
separately reviewed compatible view. Automatic adaptation to arbitrary tag,
folder, property or custom-query classification systems is deferred.

The import's categories overview lists categories used by that import, including
links to shared categories. A shared category dashboard shows all notes assigned
to it, including pre-existing vault notes. Preserve the existing vault overview;
generating an additional combined overview is deferred.

Allow saved mappings to change through a reviewed operation that shows affected
imported memberships and links, protects manually edited memberships and preserves
unrelated vault content. Associate mappings with source identity so a source
category rename does not discard the user's choice.

The first release supporting arbitrary vaults adds distinct ordinary notes and
updates them safely; combining ordinary imported thoughts with existing notes is
deferred.
Users can link related notes in Obsidian. This limits initial integration
convenience to avoid silently equating similarly named knowledge and to defer
the ownership and update rules required by combined ordinary notes. Explicit
category integration is an exception to this deferred scope.
