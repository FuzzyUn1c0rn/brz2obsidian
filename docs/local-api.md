# Local API import

The library, both CLI entry points and local Windows app can inspect and publish a supported Brain from
the running TheBrain desktop application. Enable the local API in TheBrain's
settings and copy its current address and API key. The default address is
`http://127.0.0.1:11522/api`; the converter does not scan ports or open/navigate a
Brain. Requests are read-only and use a validated local HTTP(S) origin.

The current stage includes public, non-forgotten ordinary thoughts, thought types
and tags with a valid ordinary Home. Disconnected thoughts are discovered too.
Qualified hierarchy and jump relationships, including reviewed one-way facts,
are preserved as navigation with scoped originals. Thought types and source tags
retain exact inventoried membership. Direct colour strings, corresponding type
defaults and source calendar dates are retained through neutral declarations and
assignments; labels stay owned. Known forgotten/system items and associations
retain only minimal scope evidence. Private, custom, conflicting or unresolved
included declarations refuse. Every included link requires a successful empty
attachment inventory. Qualified raw UTF-8 Markdown, note images, owned files,
external HTTP(S) resource destinations and explicit/inherited icons are preserved.
Required unavailable payloads and unqualified gaps, including TXT404, currently
refuse. No partial vault is published.

Raw note bytes come from the qualified `Notes.md` attachment, with exact original
bytes retained when safe. Supported references bind only after the complete
included inventory is known. Known forgotten/system note references are removed
as complete Markdown spans; their unsafe original copy is omitted. Unsupported
references or rendered-only authored content refuse. Rendered notes are never a
fallback and external destinations are never fetched. Pure Markdown adaptations
retain exact scoped edit evidence; reviewed formatting losses produce warnings.

Profile 2 adds the specifically qualified generic PNG/ZIP files, PNG note image
and JPEG `Icon.png` alternatives to profile 1. Raw roles determine file/image/icon
meaning. PNG/JPEG/WebP decoders and ZIP directories are checked where the profile
requires them; bytes are never transcoded or ZIP members extracted. A JPEG icon
keeps its declared `Icon.png` name and actual JPEG bytes. Missing required type
icons also refuse when an ordinary item inherits them; direct icons override the
corresponding type default without dropping the type-owned resource.

An empty non-Home item can remain an intentionally uncreated target under the
existing planner; the migration record accounts for it.

All five required starting/ending counters must agree. The observed ordinary-link
family cross-check is conditional: excluded associations retain minimal evidence
without inventing their counter contribution. Included endpoints and graph/link
joins still reconcile exactly; statistics never establish universal completeness.

## GUI

Convert and Inspect offer **BRZ archive** and **TheBrain local API** source
choices. In API mode, enter the current address from TheBrain settings, select
**Refresh Brains**, then choose a Brain by its name and full stable ID. Duplicate
names remain separate choices. Refresh does not select another Brain for you.
A failed refresh keeps the selected identity and requires a successful retry
before inspection; a successful list that omits it clears the selection.

**Advanced search limits** exposes the same four search settings and defaults
listed below. The optional result ceiling is disabled when blank. Invalid
addresses or bounds disable refresh and inspection, with guidance beside the
controls. For the local app, supply credentials through the launch environment.
Python callers can use an external credential provider; the GUI has no key field.

Inspection fully acquires the supported content and releases its
capture. Review its findings and choose a valid destination. Conversion acquires
again, with the same settings and acquisition cost. A changed source or conversion
compatibility refuses publication and requires another inspection/review.
Changing the selected source or acquisition settings also discards the review.
Acquisition is not atomic: capture verification checks the retained copy and
cannot prove that the live Brain remained unchanged. Listing and acquisition run
in workers so the task sheet remains responsive.

The closed GUI worker and review contracts use version 3. API selections carry
every effective credential-free acquisition setting; older or incomplete wire
shapes refuse explicitly. API credentials and arbitrary remote errors are never
forwarded in worker results or diagnostics. Existing destination checks, explicit
warning authorization, verified publication receipts and recovery apply to both
source choices. The current content restrictions above still apply.

## CLI

Provide the key externally in `THE_BRAIN_LOCAL_API_KEY`. Do not pass a key in the
source reference, address or command options. For example, after setting that
environment variable in your shell:

```powershell
brz2obsidian inspect 11111111-1111-4111-8111-111111111111 --source-kind local-api --api-url http://127.0.0.1:11522/api --json
brz2obsidian convert 11111111-1111-4111-8111-111111111111 new-vault --source-kind local-api --api-url http://127.0.0.1:11522/api
```

`python -m brz2obsidian` accepts the same arguments. Replace the example UUID
with the Brain's exact lowercase, hyphenated, nonzero UUID. The positional source
remains an archive path when `--source-kind` is omitted or is `brz`. API options
require `--source-kind local-api`. Existing text/JSON result envelopes and exit
codes apply; JSON emits one result object. Invalid configuration and remote or
filesystem failures use safe classified issues without echoing remote bodies,
credentials, request URLs or arbitrary exception text.

| Option | Default | Meaning |
| --- | --- | --- |
| `--api-search-initial-results` | 5000 | Raw wildcard hit limit before owner deduplication. |
| `--api-search-timeout` | 300 | Total wildcard seconds, including response waits, decompression, parsing and repeated searches. |
| `--api-search-max-response-bytes` | 128000000 | Complete post-decompression bytes per wildcard reply. |
| `--api-search-max-results` | disabled | Optional positive count ceiling. A saturated final request refuses. |

Search uses `queryText=*` and `onlySearchThoughtNames=false`. Saturated raw replies
double the requested limit; a non-power-of-two ceiling is requested once. Search
counts fit the API signed 32-bit integer range. Search stubs only seed candidates;
the adapter fetches authoritative metadata and definitions, expands graphs with
`includeSiblings=true`, validates repeated facts and reconciles the five qualified
start/end counters. Optional pins add seeds when Python configuration enables
them; their request must succeed. Null sibling inventories refuse. Null graph
attachments require a separate successful empty owner inventory to prove no note.

## Python and capture lifetime

```python
from brz2obsidian.application.wiring import local_api_workflow
from brz2obsidian.sources.thebrain.local_api import LocalApiConfig, LocalApiSourceRef

workflow = local_api_workflow(LocalApiConfig())  # uses the environment provider
reference = LocalApiSourceRef("11111111-1111-4111-8111-111111111111")
result = workflow.inspect(reference)
```

`LocalApiSourceModule(config, credentials=provider)` accepts a zero-argument
provider returning the key at acquisition time. `local_api_workflow` accepts the
same provider. References/configuration contain no credential field. The outer `local_api_workflow` explicitly pairs reviewed profile 2 with the
module. Direct `LocalApiSourceModule` construction defaults to profile 1, which
refuses the additional profile 2 shapes; explicit `profile_version="2"` requires
its matching `LOCAL_API_POLICY_V2` when composing a workflow. There is no automatic
fallback or additional GUI/CLI setting. Custom source/policy bindings remain
caller-owned composition; the factory supplies the reviewed pair. Existing config
and worker shapes remain unchanged. The module
implements `SourceModule.open`; its frozen session supplies `snapshot`,
`source_identity`, `open_payload` and `verify_consistency`. Direct session
construction accepts already qualified scoped facts plus the normalized snapshot,
closed acquisition audit and measured payload mapping; it validates identities,
evidence, storage associations and fixed capture compatibility before freezing.
It grants no additional live content support.

Additional Python bounds are request timeout 30 seconds, non-search response
16000000 bytes per metadata reply, 100000 requests, 100000 discovered thought/link identities,
1000000000 total capture bytes and 256000000 bytes per payload. The total capture
limit also bounds aggregate post-decompression response bytes before freezing.
All limits are positive finite values; timeouts use whole milliseconds and are at
most one day. Storage is private and generated; session close revokes streams and
cleans only its own capture. Acquisition also streams into a separately owned
staging directory using generated keys; complete bytes are measured and copied
into the frozen capture before staging is released. Raw notes stay in bounded
private memory until scope qualification; only eligible original bytes are then
streamed to disk, so excluded originals cannot remain after a cleanup failure. Each lifetime checks storage
identity before cleanup and preserves an unowned replacement on refusal. Temporary
staging and freezing can briefly hold two bounded copies. Integrity checks stream
captured files and never reread the live Brain.

The [capture contract](local-api-capture.md) defines CJSON1 bytes, both content
digests and a separate pinned integrity digest covering all metadata, audit,
payload bytes and ownership/storage bindings. Origin/port, acquisition times and
generated storage names do not change content identity. Authored timestamps,
values, ordered aliases, scope decisions and payload measurements do. The current
profile uses the assessed schema/build qualification baseline recorded in that
contract; this is not a fresh measurement of the running desktop build.

The source-specific outer metadata adds `run_metadata.source_acquisition` to the
published migration record. It contains exactly the closed `audit` and
`integrity_sha256` of the frozen capture, never its temporary filesystem path.
BRZ run metadata keeps its existing shape. Audit operations name resource
families: accessible-Brain listing is `brain` with `subject_id=null`; optional pin
listing is `thought` with `subject_id=null`. Each request still records the
verified requested Brain ID, sequence, outcome, times and measured reply length.
The exact failed tag400 zero-inventory exception is recorded as a classified
failed request and scoped source decision, not a successful empty response.

## Consistency

The local API import reads a Brain through several requests over time. It is not
an atomic snapshot. Editing or syncing during acquisition can produce a mixture
of source states. After acquisition, conversion uses a captured copy and verifies
that copy's integrity. This does not prove that the live Brain stayed unchanged,
that every captured object existed at the same moment, or that API discovery is
universally complete. Inspection releases its session; conversion acquires again
and therefore pays the acquisition cost again. Published acquisition evidence
records `atomic=false`, start/end times and these limits.
