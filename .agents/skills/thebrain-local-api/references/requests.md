# Local API requests and interpretation

These examples use PowerShell and the observed endpoint for TheBrain 15.0.640.0. Read
the current address from Settings > User > Local API before using it; the port
changed in an earlier release and restart-to-restart stability is undocumented.
Discover real UUIDs before substituting `BRAIN_UUID`, `THOUGHT_UUID` and `ATTACHMENT_UUID`.

## Connect and inspect the schema

```powershell
if ([string]::IsNullOrWhiteSpace($env:THE_BRAIN_LOCAL_API_KEY)) {
    throw 'THE_BRAIN_LOCAL_API_KEY is unavailable in this execution environment.'
}
$brainApiOrigin = 'http://localhost:11522'
$brainApiBase = "$brainApiOrigin/api"
$brainApiHeaders = @{ Authorization = "Bearer $env:THE_BRAIN_LOCAL_API_KEY" }
Invoke-RestMethod -Uri "$brainApiBase/brains" -Headers $brainApiHeaders

$brainApiSpec = Invoke-RestMethod -Uri "$brainApiBase/v1/docs.json" -Headers $brainApiHeaders
$brainApiSpec.paths.'/api/attachments/{brainId}/{attachmentId}/file-content'.get |
    ConvertTo-Json -Depth 30
$brainApiSpec.components.schemas.NotesDto | ConvertTo-Json -Depth 20
```

Do not output `$brainApiHeaders` or enable verbose request logging. Avoid
forwarding authenticated requests to another origin. For an offline lookup,
use `Get-Content -Raw` and `ConvertFrom-Json` on the bundled `local-openapi.json`,
resolving it relative to the skill directory. To retain a fresh spec, use
`Invoke-WebRequest -OutFile` and record the source URL and retrieval date.

## Read notes and attachment metadata

```powershell
$brainId = 'BRAIN_UUID'
$thoughtId = 'THOUGHT_UUID'
$attachmentId = 'ATTACHMENT_UUID'

$brainNote = Invoke-RestMethod -Uri "$brainApiBase/notes/$brainId/$thoughtId" -Headers $brainApiHeaders
$brainNote.markdown

$brainAttachments = Invoke-RestMethod -Uri "$brainApiBase/thoughts/$brainId/$thoughtId/attachments" -Headers $brainApiHeaders
$brainAttachments | Select-Object id, sourceId, type, isNotes, location, dataLength

$brainMetadata = Invoke-RestMethod -Uri "$brainApiBase/attachments/$brainId/$attachmentId/metadata" -Headers $brainApiHeaders
$brainMetadata | Select-Object id, brainId, sourceId, type, location, dataLength, modificationDateTime
```

`NotesDto` contains identity, modification timestamp and nullable `markdown`,
`html` and `text` fields. Save the relevant field when an authored note is wanted;
saving the JSON wrapper as `.md` does not produce a Markdown note. Retrieve
referenced images separately when the task requires preserving their presentation.

`AttachmentDto.name` may be null even when archive names are populated;
`location` may identify the filename. Compare specific fields rather than
asserting the whole API object and BRZ record have identical representations.

## Download file bytes

```powershell
$brainEvidenceDir = Join-Path (Get-Location) 'tmp/brain-api-investigation'
New-Item -ItemType Directory -Force -Path $brainEvidenceDir | Out-Null
$brainPayloadPath = Join-Path $brainEvidenceDir "$attachmentId.bin"
if (Test-Path -LiteralPath $brainPayloadPath) {
    throw 'Choose a fresh evidence filename before downloading.'
}
Invoke-WebRequest -Uri "$brainApiBase/attachments/$brainId/$attachmentId/file-content" `
    -Headers $brainApiHeaders -OutFile $brainPayloadPath
Get-Item -LiteralPath $brainPayloadPath | Select-Object Length
Get-FileHash -LiteralPath $brainPayloadPath -Algorithm SHA256
```

Choose an extension after checking source metadata and returned bytes. Save binary
content directly; decoding and re-encoding can alter it. Preserve HTTP status on
failure and avoid counting a partial output or JSON error body as recovered content.

## Errors and evidence

- Connection failure: distinguish a stopped desktop, changed endpoint and sandbox
  network restrictions.
- 401: check key availability and user association without displaying the key.
- 403: record the denied route/scope; this is not evidence of absent file bytes.
- 404 from file-content: verify attachment identity/metadata and a present-content
  control before generalizing. The bundled 2026-10-14 schema lists only 200/401 for this endpoint,
  but runtime 404s were observed on 2026-10-13.

Metadata `dataLength` may differ from actual downloaded length. Preserve actual
bytes and report the discrepancy. Matching lengths/timestamps helps correlation
but does not authenticate historical bytes absent from the archive. One absent
TXT downloaded successfully while other TXT records returned 404; neither result
defines attachment type 15.

## Other endpoints when relevant

`GET /api/links/{brainId}/{linkId}/attachments` lists relationship attachments.
`GET /api/attachments/{brainId}/by-location` finds external-resource locations;
URL type 3 is the default, with types 2 and 8 for external files/directories.
Encode query values. The local description says URL matching is case-insensitive
and ignores HTTP/HTTPS scheme and trailing slash; cloud case behavior differs.
This is not a general inventory endpoint.

`/api/notes-images/{brainId}/{token}/{filename}` describes an expiring-token image
request without Bearer authorization, although global Bearer security remains in
the schema. Use actual references from a note response; do not invent tokens or
treat tokenized URLs as durable. Keep tokens out of public logs and retained prose.
Resolve relative references against the correct origin before adding credentials.

`GET /api/app/state` reads Brain/thought/tab state. POSTs under
`/api/app/brain/{brainId}` open/close Brains or activate thoughts and change desktop
state. Use them when the task calls for these actions. Root routes such as
`/stock-icons/...`, `/custom-icons/...`, `/file-download/{tempId}` and
`/notes-image-request/...` require known resource references; inspect their schema
entries rather than guessing temporary IDs or icon identities.

Creation, upload, patch and deletion methods are also documented in the snapshot.
Select them within the user's authorized scope and inspect the installed schema's
request body, particularly multipart uploads where local and cloud schemas differ.
