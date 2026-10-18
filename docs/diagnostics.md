# Readable application diagnostics

The application, human-readable CLI and diagnostic reports use deliberate static
explanations for known error codes and reviewed `(code, diagnostic reason)` pairs.
An explanation states the operation, the supported cause and a practical action.
Unsupported content is a converter limitation; unknown causes stay uncertain.
An exception message, local API response body, note body or evidence string is
never used to improve the human explanation.

## Source-to-presentation audit for #232

| Boundary | Previous loss or risk | Current behavior |
| --- | --- | --- |
| Local API transport, listing and capture | Broad code mappings hid different failures; temporary-copy failures became a generic source limitation. | Authentication, connection, timeout, missing attachment and temporary-copy failures have distinct explanations and actions. Remote bodies remain excluded. |
| Local API declarations, ownership and resource qualification | Many deliberate refusals shared `invalid_source`. | Reviewed literal causes receive a `diagnostic.*` reason paired with their existing code: ownership, thought metadata, attachment/relationship conflict or unsupported data, and invalid attachment contents. |
| Local API note scoping and late reference binding | Wrappers replaced known Markdown causes; late binding lacked a thought label. | Typed refusal reasons survive, and safe thought metadata supplies note context. Leading-BOM interpretation and legacy capture validation remain owned by #231. |
| BRZ opening and payload reading | Raw filesystem exception strings could escape, and absent content had no useful explanation. | Missing archive, read permission, other read failure and invalid archive are distinguished. Required absent contents have a supported explanation. Unexpected exception text is replaced by static facts. |
| BRZ note preparation and binding | Known HTML/reference failures retained IDs but lost the readable thought name; reconstructed guidance blamed the note for converter limitations. | Reviewed reasons and safe thought names survive through public Workflow results, application findings and CLI output. Guidance uses the same supported explanation. |
| Workflow, inspection and conversion | Broad mappings discarded reason meaning; unexpected errors exposed exception text. | A shared projection gives GUI, CLI and reports the same explanation. Unexpected causes remain unknown, with a report action. Publication status remains separately reported. |
| Destination validation and publication | Brief field messages omitted the operation or context. | Destination messages explain the rejected folder/path and action; publication, integrity, cleanup and post-publication failures have static explanations. |
| Vault checking | Technical details and raw reference values distracted from the practical problem. | Known checker codes explain note properties, links, Bases, images and read failures, identify the affected file and give an action. The check remains read-only. |
| Qt presentation | Automatic rich text could interpret metadata tags; arbitrary wrapping split words; refused guidance suggested reviewing planned contents. | Findings use plain text, wrap at word boundaries where possible and retain applicable refusal guidance. Diagnostic details remain a secondary, expandable view. |

Some checks establish only a broad fact. Unclassified `invalid_source` means the
converter could not verify the Brain data; it does not establish whether the
Brain or converter is responsible. Unclassified `invalid_reference` does not
prove a broken link. `unsupported_feature` establishes a support limitation but
not a particular feature. New or unknown backend codes state uncertainty rather
than borrowing a familiar reason. Capture failures distinguish the temporary-copy
operation without guessing whether permissions, disk space or another host
condition caused it. Known converter limitations and confirmed converter-state
failures request a report instead of directing the user to edit their Brain.

## Structured interface compatibility

Existing error codes remain unchanged. `Issue.rule_id` may contain a reviewed
`diagnostic.*` reason; consumers should treat it as an identifier, not prose.
Reason meaning is admitted only with its matching code. Human explanation text
and guidance are user-facing wording and can change.

`Issue.subject` is an optional additive diagnostic extension with `kind` equal to
`item`, `document`, `asset` or `relationship` and a `name` of 1–120 printable
characters. The model keeps these source-neutral values; TheBrain presentation
uses thought, thought note, attachment and relationship. Source adapters admit
metadata names deliberately, remove control and bidirectional-format characters,
limit length and omit URI-like or credential-like labels. A label is metadata,
never note content or a transport error. Views render it literally.

Old inputs without `subject` remain valid. If no subject exists, serialization
omits the field exactly, preserving the previous shape, including existing null
fields. A populated subject is included in library/CLI JSON results. Older strict
readers that reject additional properties must accept this extension or use a
current result model before reading such results. Result schema version 4 and
source capture/schema/profile versions remain unchanged: this extension adds
optional diagnostic context, and does not change migration or capture meaning.
This compatibility change is explicit in the #232 review scope.

Detailed structured source evidence remains available through the existing
library contracts. Human CLI output and application reports display admitted
explanations, codes and applicable artifact paths instead of arbitrary evidence
or exception strings. The JSON CLI remains the structured result interface.

## Verification

Public Operations/Workflow and CLI tests use synthetic local API responses and a
small BRZ archive to exercise the supported cause families, late binding,
metadata context, unknown causes and content/credential canaries. The real Qt
widget control verifies literal metadata, operation wording, word wrapping and
refusal guidance. Existing destination and vault-check controls cover affected
consumers. Line/branch coverage, function contexts and elapsed time guide the
selection; native visual and keyboard/scrolling review independently establishes
presentation usability under P1–P6. These controls do not establish complete
source preservation or actual-vault acceptance.
