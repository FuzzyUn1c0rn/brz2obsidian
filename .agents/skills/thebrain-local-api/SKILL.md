---
name: thebrain-local-api
description: Use the running TheBrain desktop application's local HTTP API to inspect Brains, thoughts and notes, retrieve attachments, or perform requested API actions. Apply to local TheBrain API work and API-assisted BRZ recovery investigations; ordinary archive-only conversion does not require this skill.
---

# TheBrain Local API

Use the desktop server's own specification to choose requests. Match Brain and
object identities before interpreting responses or retrieving content.

## Connection

- Current observed API base: `http://localhost:11522/api/` (desktop build reported as TheBrain 15.0.640.0, observed 2026-10-14). Read the current address in **Settings > User > Local API** (some releases label this **Local API Key**) and configure clients from that value.
- Interactive documentation: `<current-origin>/api/`.
- Live OpenAPI specification: `<current-origin>/api/v1/docs.json`.
- Key environment variable: `THE_BRAIN_LOCAL_API_KEY`.
- Authentication: `Authorization: Bearer <value of that environment variable>`.
  The variable name itself is not the token. Never print the key or headers,
  save the key in artifacts, or place its value in generated instructions.

The desktop must be running with its local API enabled. TheBrain's
[15.0.637 release notes](https://forums.thebrain.com/post/thebrain-15-0-637-quick-thoughts-note-versions-better-dialogs-undo-across-syncs-and-merged-13893294)
document the desktop address change from port 8001 to 11522. This explains
the observed change after the reported update; it does not establish whether the
port can vary on later restarts. Use the address displayed in **Settings > User >
Local API** as authoritative. The examined documentation does not describe a
stable automatic port-discovery mechanism. The installed app was reported as
version **15.0.640.0**; this is a desktop build, while the API schema reports
API version 1.0. If the API key is
missing, ask for it to be made available to the execution environment without
asking the user to paste the secret into chat. A local key belongs to its
generating user; it is not a cloud credential.

Use programmatic HTTP clients for ordinary API work. A sandbox connection denial
does not prove the desktop is stopped; use the permitted network execution route
when needed.

## Select requests

The bundled [local specification](references/local-openapi.json) was retrieved
from this user's running desktop on **2026-10-14** (OpenAPI 3.0.1, API version 1.0;
desktop build reported as 15.0.640.0).
Parse its JSON and inspect only the relevant path, method and referenced schemas;
avoid dumping the whole specification into context. Prefer the live local schema
if endpoint behavior or the installed version differs; refresh it with an
authenticated GET when useful.

These GET paths are relative to the `/api` base:

| Path | Purpose |
| --- | --- |
| `/brains` | List accessible Brains with IDs, names and Home thought IDs |
| `/app/state` | Read current application state without navigating |
| `/thoughts/{brainId}/{thoughtId}` | Read thought identity and metadata |
| `/notes/{brainId}/{thoughtId}` | Read `NotesDto`, with Markdown in `markdown` |
| `/notes/{brainId}/{thoughtId}/html` | Read `NotesDto`, with HTML in `html` |
| `/notes/{brainId}/{thoughtId}/text` | Read `NotesDto`, with plain text in `text` |
| `/thoughts/{brainId}/{thoughtId}/attachments` | List thought attachment records |
| `/attachments/{brainId}/{attachmentId}/metadata` | Read attachment metadata |
| `/attachments/{brainId}/{attachmentId}/file-content` | Download attachment bytes |

The schema's path keys already include `/api`. Add the table's relative paths to
the base once; root resource paths such as `/stock-icons/...` are outside `/api`.

Read [request examples and interpretation](references/requests.md) for PowerShell
requests, schema lookup, file downloads, errors, note images and app control.
Use documented write methods within the user's authorized task; inspection and
recovery investigations use read requests.

## Content and recovery

A **thought note** and an **attachment** are distinct. The notes endpoint returns
a JSON wrapper; extract its relevant `markdown`, `html` or `text` field. An
attachment download returns file bytes. A TXT attachment may contain flattened
document text with page numbers and repeated headings; do not describe it as
recovered Markdown or change its format without a user request.

For BRZ comparison, match `meta.json`'s `BrainId` to the API Brain ID, then match
attachment `Id` and `SourceId` to API `id` and `sourceId`. For a note, match the
thought ID. Names label objects; IDs establish identity. Follow the project's
native-investigation and workspace conventions when available.

Inspect the first retrieved content before repeating equivalent requests. Record
per-object HTTP outcomes, actual byte length and SHA-256. Compare with archive
bytes when present. Metadata success and `dataLength` do not prove bytes exist or
the declared length is accurate: metadata 200/content 404 and incorrect live
icon lengths were both observed.

The schema enumerates attachment type `15` without naming its purpose. Observed
type-15 attachments included TXT files; do not infer an authoritative meaning
such as extracted text or universal downloadability. A local 404 establishes
current request failure, not permanent loss or cloud unavailability. Retrieved
bytes are current content; historical equivalence needs independent evidence.

Keep private probes in the requested destination or an appropriate ignored effort
directory. Preserve source archives and user content. Fetching bytes does not
authorize patching a BRZ, editing a Brain or changing a vault.
