# Native first-version acceptance

Status: passed

Verified on 2026-10-04 in standard **Obsidian 1.13.7**, on native Windows.
The reviewer used fresh ignored `ui-A` / `ui-B` copies of the actual accepted
converter vaults. Every file's SHA-256 and inventory matched the pristine vault
before opening: 114 files in A, 96 in B. The pristine accepted outputs were
checked unchanged again after review. No normal user vault or community plugin
was used. Private screenshots and candidate mappings remain under ignored
`brz/`; this report contains only aggregate observations.

Independent full-source preservation passed all six exact/repeat/reordered A/B
conversions; see [the preservation report](real-export-acceptance.md). The
observations below exercise the actual complete converter output; earlier
prototype/Wayfinder results do not supply this gate.

## Confirmed native observations

| Check | A | B |
| --- | --- | --- |
| Startup and Home | Assigned root Home opened in Reading view; source heading/label/body observed | Assigned root Home opened in Reading view; source Home has no body; root URL visible |
| Native Home bookmark | Returned from an ordinary note to the assigned root file | Returned from an ordinary note to the assigned root file |
| Parents / Children / Related | Representative qualified paths followed successfully | Representative qualified paths followed successfully; selected parent was intentionally uncreated and its click created the assigned Notes path |
| Uncreated click-to-create | Candidate absent before click; exact assigned `.md` file existed afterward | Candidate absent before click; exact assigned `.md` file existed afterward |
| Native Backlinks | Authored and generated hierarchy mentions observed | Authored and generated hierarchy mentions observed |
| Native Graph | Connected existing and dim uncreated nodes visible | Connected existing and dim uncreated nodes visible |
| Native tags/search | Mapped token discovered; selected search returned 15 files including the focused membership listing | No tags found, matching zero source assignments |
| Inline images | Actual inline PNG rendered | Actual inline WebP rendered in Reading view |
| Additional generic Resources file | Type 1 generic PNG opened in native image viewer | Generic file class overlaps the retained PDFs; Resources link opened native PDF viewer |
| PDF | No source PDF candidate | Actual PDF opened in native 100-page viewer |
| External reference presence | Ordinary-note URL visible | Root and ordinary-note URLs plus directory `file:///` reference visible |

Both click-created paths were exactly the reserved `Notes/` targets, with no
extra `.md` extension. Later creation intentionally changes only review copies;
it does not imply that converter output originally contained those notes or
that the converter populates reciprocal sections afterward.

B's parent navigation created one reserved parent before the explicit separate
Home-linked candidate was tested. A's 15 search results count files including
the focused membership listing, not 15 created-source tag assignments. Graph
review observed representative connected/dim nodes; exhaustive graph/assignment
comparison belongs to the independent checker.

Neither Home owns a local inline image or local file resource. Those root
classes are not applicable to these inputs; actual ordinary owner notes supply
the resource observations, with synthetic renderer tests covering root-relative
local paths. A has no PDF/directory class and B has no native source tag
membership. External destinations were observed as retained references and
were never opened or fetched.

No converter-output defect was found, so no repair/retest cycle was needed.
This representative review complements complete independent preservation; it
does not claim every thought note or every PDF page was visually reviewed.
Private evidence includes startup, ordinary/resources, relationships, backlinks,
created targets, Graph, tags, inline PNG/WebP, generic image, PDF and external
reference screenshots. Tested preferences/presentation are version-specific
evidence rather than a guarantee for other Obsidian releases.

## Documentation and library/CLI verification

On 2026-10-04, all three documented Python examples ran against the checked-in
synthetic archive through the default Workflow, explicit composition and direct
analyze/plan/render/publish interfaces. Each published a verified one-note vault.
Both console and module entry points passed text/JSON inspect and conversion,
planned/pending inspection and null actual counts, structured result round-trip,
nonempty-destination refusal, help and invalid arguments. Temporary owned
outputs were removed. Captured UTF-8 output used `PYTHONIOENCODING=utf-8`, now
documented for Windows scripts.

README, architecture, testing and source-coverage guidance reflect complete
reviewed v1 behavior, exact warning rules/refusals, intentional uncreated targets,
fresh destination restrictions, actual nested record schema, inward dependencies,
source/profile composition, public/private/native checks and version boundaries.
All 15 local documentation link destinations exist. No production code or
prose-mirroring tests were added by ticket 10.

The applicable public gates passed: 277 pytest tests, Ruff lint/format,
`pip check` and `git diff --check`, using the root project's `.venv` interpreter
with `PYTHONPATH` selecting the ticket worktree source. Runtime/environment
versions are recorded in [testing](../../../docs/testing.md#recorded-versions).
All approved slice criteria, alternate-source reuse, full real-source preservation,
public behavioral checks and these native/documentation gates passed. Ticket 10
is resolved. Overall specification/index closure remains with the integration
coordinator after the required final code review.
