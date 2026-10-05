# TheBrain to Obsidian Migration

The vocabulary of moving a Brain into an Obsidian vault while preserving its content and relationships.

## Language

**Source collection**:
A collection of knowledge being migrated into a vault. A Brain is TheBrain's source collection.
_Avoid_: Brain when referring to another application's collection

**Source item**:
A named item of knowledge in a source collection that may have content, attachments, and relationships. A thought is TheBrain's source item.
_Avoid_: Thought when referring to another application's item

**Entry item**:
The item explicitly designated as a source collection's starting point. TheBrain's Home thought is its entry item.
_Avoid_: Graph root when implying a unique parentless item

**Brain**:
A collection of linked knowledge in TheBrain, including its content and associated files.
_Avoid_: Vault when referring to the source collection

**BRZ archive**:
A Brain exported by TheBrain as a `.brz` archive.
_Avoid_: Sample when referring to the supplied real export

**Thought**:
A named item in a Brain that can have relationships, note content, and attachments. TheBrain distinguishes ordinary thoughts from special roles such as tags, types, and system items.
_Avoid_: Node when referring to a source item; note when referring to the item rather than its text content

**Thought note**:
The text content associated with a thought in TheBrain, distinct from the thought and its relationships.
_Avoid_: Thought when referring only to its text content

**Home thought**:
The thought designated in a Brain as its entry point when loading the Brain or invoking Home. This role is independent of its title, content, and position in the hierarchy.
_Avoid_: Graph root when implying that it must be the only parentless thought

**Source tag**:
A special thought used to classify other items in a Brain. It can also have its own thought-note content.
_Avoid_: Vault tag when referring to the source thought

**Thought type**:
A special thought used as a reusable classification for other thoughts, with shared properties such as appearance.
_Avoid_: Source tag; attachment type; programming-language class when implying full object-oriented semantics

**Type assignment**:
The association that gives a thought its thought type, distinct from a tag assignment or a parent/child relationship.
_Avoid_: Inheritance when referring only to classification membership

**Inherited appearance**:
Appearance a thought receives from its assigned thought type, distinct from appearance specified directly on that thought.
_Avoid_: Inherited note content; copied attachment when referring only to displayed appearance

**Effective appearance**:
The icon and colours displayed for an item after applying its explicit appearance values and any inherited defaults. Each explicit value takes precedence over the corresponding inherited value.
_Avoid_: Stored appearance when referring to the displayed result; inherited label when label propagation has not been established

**Vault tag**:
A keyword attached to a note in Obsidian to classify it and support discovery.
_Avoid_: Source tag thought; note when referring to the keyword

**Vault category**:
A note representing a kind of entity in the vault, used to classify other notes and provide a shared point of navigation.
_Avoid_: Vault tag; thought type when referring to the destination concept

**Category membership**:
The association of a vault note with a vault category, distinct from an ordinary relationship or tag assignment.
_Avoid_: Parent/child relationship; source type assignment when referring to destination membership

**Category dashboard**:
A category note that provides context and views of the notes belonging to that category.
_Avoid_: Manually maintained index when membership is discovered dynamically

**Category template**:
A reusable starting structure for a new note belonging to a vault category, providing that category's agreed initial information. It does not impose continuing rules on existing notes.
_Avoid_: Thought type; enforced schema when referring to initial note structure

**Categories overview**:
A vault entry point listing the available category dashboards.
_Avoid_: Category dashboard when referring to the overview of all categories

**Appearance category**:
An optional vault category chosen from a note's memberships to supply a default dashboard icon, independently of membership order and separately from declared colour metadata. An explicit note icon takes precedence; an empty choice opts out and an invalid choice does not select a substitute.
_Avoid_: First category when implying that list order chooses the appearance; source thought type when referring to the editable destination choice

**Attachment**:
A file or external-resource reference associated with an item in a Brain.
_Avoid_: Archived file when the resource is an external reference

**Absent payload**:
A file described by a BRZ attachment record for which no corresponding bytes are present in that archive. Absence alone does not establish whether the file is primary content or derived data.
_Avoid_: Uncreated target; missing PDF when only a separate TXT payload is absent

**Forgotten thought**:
A live thought marked forgotten in TheBrain, distinct from a deleted object that is absent from the live export records.
_Avoid_: Deleted thought

**Vault**:
A collection of notes and associated files opened by Obsidian as one knowledge workspace.
_Avoid_: Brain when referring to the destination collection

**Uncreated target**:
A destination named by an internal vault link for which no note file exists yet.
_Avoid_: Missing source thought; broken link when the absence is intentional

**Relationship**:
A connection between items in a Brain, including the meaning of that connection.
_Avoid_: Ordinary link when the connection's type or direction matters

**Parent/child relationship**:
A hierarchy connection in which one thought is the parent of another. A thought can have multiple parents.
_Avoid_: Folder nesting, single-parent tree

**Jump relationship**:
A connection between thoughts that designates neither thought as the other's parent or child.
_Avoid_: Sibling relationship, which implies a shared parent

**Arrow direction**:
The visual direction indicated on a relationship, independent of whether the relationship is parent/child or jump.
_Avoid_: Hierarchy when referring to an arrow

**One-way relationship**:
A directed relationship whose destination normally does not display the source as a neighbor in TheBrain's Plex. This is a separate setting from a visible arrow and does not remove either thought from the Brain.
_Avoid_: Arrow when referring to the one-way setting; access restriction

**Migration**:
A one-time transfer from a source collection into a new vault.
_Avoid_: Synchronization, update of an existing vault

**Migration record**:
A record connecting source items and relationships to their destination representations, including source details retained for traceability.
_Avoid_: Synchronization state; editable vault note

**Migration report**:
A readable account of a migration's outcome, preserved material, adaptations, and unresolved source gaps.
_Avoid_: Migration record when referring to the account intended for human review
