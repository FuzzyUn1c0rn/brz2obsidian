# Approved version 2 implementation breakdown

Review state: approved by the user on 2026-10-04; individual tickets published

This is the user-approved review record produced with to-tickets from the [ready-for-agent specification](spec.md). The slices below are now published as separate ready-for-agent tickets in the [implementation index](README.md), with acceptance checkboxes, genuine blockers, story coverage and confirmed public testing seams. This review record is not an implementation completion claim. The parent specification and Wayfinder issues were preserved during publication.

## Shape and testing boundaries

Eleven slices progressively add observable conversion/maintenance behavior. The current source adapter, pure core, renderer, publisher and workflow already expose the required boundaries. No standalone prefactoring or wide expand–contract migration is needed: evolve the versioned contracts through the first working typed conversion, and keep small naming/property/rendering refactors inside the slice whose output proves them. Update affected existing public tests for explicitly changed v2 schemas and output, preserving their underlying behavior checks.

Use public inspect/convert workflow calls with actual synthetic ZIPs and temporary vaults as the main automatic seam. Thin CLI checks verify serialization and exits. The checker has its own public library/command seam. Focused existing source/core/renderer/publication boundaries remain available for contract, reference-span and failure cases. Public tests use synthetic inputs; independent real-archive acceptance and native Computer evidence stay private. The project virtual environment remains mandatory.

Each feature slice must leave its applicable public regression checks green and demonstrate its result independently. Early slices are usable subsets of v2, not claims that the full Software Engineering archive already converts. Update the relevant migration record/report, artifact accounting and usage guidance as behavior lands. The last three slices establish integrated, independently audited and natively accepted delivery.

## Proposed slices

1. **Convert thought types and all their members into linked category notes**

   **Blocked by:** None.

   **What it delivers:** Inspect and convert a small reviewed Brain containing a type and typed members, including an otherwise empty member, into a verified fresh vault with distinct category/member notes and linked memberships. Ordinary native links and Backlinks make the objects navigable before later dashboard presentation lands.

   **Acceptance outline:**

   - Public inspect and its CLI command remain read-only, reporting consistent planned results without a publication receipt. Public convert and its CLI command publish the tiny typed fixture into a verified fresh vault, reporting consistent actual results and a durable receipt. Use version-2 contract/profile/renderer/result/migration schemas while retaining existing commands, workflow signatures and outcome/exit behavior.
   - Validate type/instance field-link correspondence in both directions; conflicting, duplicate, missing, dangling or wrong-role assignments refuse without publication. Unreviewed subtype/custom-link meanings remain refused.
   - Materialize every definition and typed ordinary member; preserve Home, ordinary graph/tags, the untyped-empty selection policy, source identity and deterministic collision-safe naming. Definition-owned authored content/resources survive as their own data, with no content inheritance into members.
   - Retain system-to-type connections only as evidence; category names follow source identity/title rather than inferred pluralization or remapping.
   - Demonstrate actual payload copying, original evidence, typed targets/counts/creation reasons and fresh-destination protection. Reserve the new support naming namespace needed by later slices without weakening Windows/path/collision protections.
   - Update the test-only alternate source to the current strict contract; retain inward dependencies and opaque generic identities. Install any needed packages only inside the project environment.

   **Stories:** 2–4, 5–9, 11–22, 61–65, 76–79.
   **Testing:** Workflow/CLI synthetic typed conversion and assignment-corruption controls; existing public naming/graph/tag/source/contract/architecture checks.

2. **Preserve canonical properties, source dates and editable icon snapshots**

   **Blocked by:** 01.

   **What it delivers:** Converted objects expose the documented linked metadata and source-derived calendar dates, with preserved local icon images and migration-time body-icon references that users can edit.

   **Acceptance outline:**

   - Serialize the complete agreed canonical property core safely for every created imported source-item note, including ordinary thoughts, type definitions and materialized source-tag thoughts. Retain source tags and imported identity pairs without inferring semantic fields or aliases from prose or treating a source tag as a category. A synthetic authored source-tag case proves that its source IDs, source-derived calendar dates and existing native tag behavior survive together.
   - Imported dates use valid source thought calendar components; missing values stay empty, populated invalid values do not receive invented dates, and full timestamp strings/migration time remain distinct evidence.
   - Preserve declared icons/colours and own labels, including the member-owned icon precedence and opaque token evidence; no synthesized inherited member label or unsupported colour interpretation.
   - Copy icons once through preserved ownership, reference the migration-time effective image inside created notes, keep decorative assets out of Resources, and leave untyped icon-only items under the existing materialization policy.
   - Explicit member icon, optional provider and declared colour fields remain distinguishable from inherited defaults; record provenance/adaptations and byte obligations without changing authored Markdown outside permitted spans.
   - Existing authored headings, original backups, code, blockquotes, Unicode and newline spelling remain preserved alongside the generated additions.

   **Stories:** 6–10, 13–14, 28–33, 41–44, 61, 74, 78–80.
   **Testing:** Actual converted frontmatter/body/resources and evidence through Workflow, including an authored source-tag case with populated source dates and identity; focused existing reference-span/public renderer contracts where necessary.

3. **Browse categories through rename-safe native dashboards**

   **Blocked by:** 02.

   **What it delivers:** Home opens a Categories overview, and category notes embed native Members/Gallery Bases with complete discovery and live icon inheritance.

   **Acceptance outline:**

   - Enable/configure the bundled Bases plugin in this slice's generated vault so its dashboards work before template support lands. Include the required native configuration in verified publication and artifact accounting, without requiring a community plugin or copying unrelated reference settings.
   - Discover actual memberships through linked category properties and the embedding category identity; a hierarchy/prose/provider link alone is not membership.
   - Contextual member queries remain applicable after link-preserving category renames; document that users open member views through the category dashboard rather than a standalone Base without an embedding category.
   - Exclude Templates/Attachments support deliberately; keep legitimate Template-named members. The overview uses the category tag and folder role guard and excludes ordinary source tags or same-basename ordinary notes.
   - Tables start Icon, Note, Inheritance, categories, created, updated, with deterministic note sorting; the overview starts Icon then Category. Gallery uses native images. The decorative Appearance display is absent.
   - Category icon changes update inherited views; member overrides win. Provider reordering/addition does not reselect defaults. Blank opt-out and invalid/dangling/nonmember providers behave as specified, without rewriting body-icon snapshots.
   - Every generated Base/embed/overview and its reserved names is included in publication/accounting; original Home content and entry/bookmark behavior remain available.
   - Perform an early bounded native check on a converter-produced synthetic vault to confirm contextual query, image and rename behavior. Keep that evidence separate from final full-output acceptance.

   **Stories:** 5, 15–20, 23–34, 39, 49–50, 74, 80.
   **Testing:** Workflow-generated Base/frontmatter/guard fixtures plus the prior prototype's native scenarios repeated on this slice's actual output.

4. **Create and extend objects with native templates and a maintenance guide**

   **Blocked by:** 03.

   **What it delivers:** A user opens the generated vault, selects a full template for a new note, sees it discovered in the dashboard and can add a future category using documented starters.

   **Acceptance outline:**

   - Retain and verify the bundled Bases configuration established by ticket 03; enable/configure bundled Templates, native property types, required Home/link preferences and template-folder/date insertion settings. Account for configuration without copying unrelated reference toggles or requiring community plugins.
   - Deliver a generic template and complete templates for the actual categories with linked membership/provider, blank overrides, insertion-date variables and no imported source IDs or invented domain-specific schema.
   - Deliver category-note, member-template and contextual Base starter examples that discover a manually classified future note using the same native mechanisms.
   - Document template selection, lookup before creation, meaningful entity links, canonical vocabulary, source versus new identity, existing-note membership editing and explicitly maintained update dates.
   - Existing memberships are edited directly; do not ship additive category-only templates or promise native protection against arbitrary full-template scalar overwrites.
   - Native insertion on a new note initializes membership/dates, whereas a membership edit on an existing note preserves its established dates, content, provider and identity. User/agent extension does not depend on folders as the type system or registry fields.
   - Document deliberate reference adaptations, dashboard entry points and editable snapshots; prove all support/configuration artifacts are manifested and collision-safe.

   **Stories:** 14, 19–20, 28, 32, 34–50, 74, 79–80.
   **Testing:** Workflow actual template/configuration/starter bytes and a bounded Computer check of native insertion, existing-note property edits and future-category discovery.

5. **Convert the evidenced differently marked thought note safely**

   **Blocked by:** 01.

   **What it delivers:** The sole unambiguous nonempty canonical NoteType-0 thought-note case becomes readable active Markdown with a working local image and exact original backup.

   **Acceptance outline:**

   - Promote only the specified thought-owned Type-1/NoteType-0 canonical Notes.md candidate on an ordinary owner, with normal state, ownership, length, CRC, decoded-content and supported-reference checks.
   - Preserve original bytes and numeric-marker evidence; adapt supported local image/thought references without changing other authored spans, code or line endings.
   - Retain empty-placeholder behavior and refuse competing active candidates, ambiguous roles, invalid required references and corrupt/missing payloads rather than selecting content by guesswork.
   - Do not promote arbitrary Markdown file attachments or infer that the different marker represents UI selection.
   - Show active-content eligibility/materialization, backup/copy obligations and reference adaptations consistently in inspection, conversion, reports and records.

   **Stories:** 6–10, 52–53, 61–63, 74, 80.
   **Testing:** Workflow/CLI fixtures for accepted and competing/integrity/refusal cases, with existing public note/span boundaries for exact edits.

6. **Report the zero-length absent TXT pattern while preserving PDFs**

   **Blocked by:** 01.

   **What it delivers:** A reviewed zero-length absent TXT declaration beside its identity-associated intact PDF converts successfully with an explicit source-gap warning and no fabricated file.

   **Acceptance outline:**

   - Recognize only the specified new versioned rule: correct owner/role/TXT location, zero length, state 2, absent bytes and the unique same-owner filename-stem/PDF-identity association with intact normally verified PDF bytes.
   - Require every predicate conjunct; wrong state/length/stem/owner/role, ambiguous association or absent/corrupt PDF remains a refusal with no publication.
   - Retain the earlier positive-length missing-TXT and icon-length rules unchanged; unknown profile/rule/disposition evidence cannot downgrade failures.
   - Return warnings/exit 2 with each declaration and association recorded individually. Add the source-filename notice only on an existing owner note, without making a note solely for the gap, fake TXT bytes or a usable broken local link.
   - Preserve PDFs byte-for-byte and explain vault Search's PDF-body limitation once in report/guide, separately from source-gap warnings. Do not claim optional-cache purpose, extraction failure or fresh-restore search equivalence.

   **Stories:** 8, 54–57, 61–65, 73–74, 80.
   **Testing:** Workflow accepted/refused synthetic PDF/TXT fixtures with independent mutations for each conjunct and combinations; existing warning/CLI/accounting/byte tests.

7. **Present reviewed video resources without changing their source URLs**

   **Blocked by:** 01.

   **What it delivers:** Converted reviewed YouTube resources retain exact clickable URLs and provide a usable native embed with the evidenced timing intent.

   **Acceptance outline:**

   - Preserve original URL spelling/query parameters and VideoHtml evidence while deriving native presentation from validated reviewed provider facts, not executing archived iframe HTML.
   - Offer the embed alongside the retained original link and account separately for any derived embed URL and timing adaptation, including the demonstrated 18-second start.
   - Do not fetch/download remote resources during inspection/conversion, invent a local video payload or silently support unreviewed video semantics/providers.
   - Explain remote/offline/service dependence once in report/guide, without treating an unavailable remote preview as missing archived bytes or hiding the original link.
   - Verify native rendering/playback/timing on a review copy of converter-produced output when service availability permits; record material limits honestly and leave playback paused.

   **Stories:** 8–10, 58–63, 74, 80.
   **Testing:** Workflow/CLI exact URL/evidence/native-embed fixtures and no-fetch behavior; bounded Computer comparison using the established resource scenarios.

8. **Check editable vault conventions through a read-only library and command**

   **Blocked by:** 04.

   **What it delivers:** A human or agent checks a generated or manually edited vault and receives deterministic structural diagnostics without needing the source archive or modifying any note.

   **Acceptance outline:**

   - Implement the specified source-independent public check_vault behavior and thin check-vault text/JSON command with the distinct strict versioned result envelope and clean/issues/failed outcomes and 0/2/1 exit semantics.
   - Check known property cardinality/types, safe data-only frontmatter including malformed/duplicate keys, category role, provider membership/resolution, required Base/image targets and imported identity pairs/duplicates.
   - Resolve qualified references deterministically; accept shortened links only when unambiguous and report ambiguous required category/provider/media references without choosing or rewriting a target.
   - Permit unrelated custom properties, native date variables in template scope and intentional uncreated ordinary targets. Preserve blank provider opt-out versus invalid-provider diagnostics.
   - Enforce contained reads, report unsafe required references without following them outside the vault, continue other readable notes after per-note problems, and expose unavailable measurements honestly on failures.
   - Evaluate actual mutable vault state rather than trusting migration records; prove unchanged file bytes/inventory and document structural scope, deterministic diagnostics and separation from preservation verification.

   **Stories:** 30–31, 44, 48, 51, 66–72, 74–75, 78–80.
   **Testing:** Public check_vault with real filesystem fixtures, command wrapper checks, malformed/ambiguous/custom/uncreated/template/containment/read-failure controls and before/after byte inventory comparisons.

9. **Prove the combined v2 workflow, publication safety and source neutrality**

   **Blocked by:** 05, 06, 07, 08.

   **What it delivers:** One complete synthetic conversion combines the new concepts with existing graph/tags/resources, passes the convention checker, and remains safe and reusable through public interfaces.

   **Acceptance outline:**

   - Publish and independently inspect a mixed-feature synthetic vault exercising classification/materialization, empty targets, graph/tags, icon/provider cases, canonical dates, dashboards/templates, exceptional active note, PDF/TXT gap and video URL metadata.
   - Verify the full versioned library/CLI/report/record/configuration/count/manifest contracts, classification/support accounting, expected warnings and no hidden feature-specific partial successes.
   - Extend source-change, path/collision, staging/stream/I/O, destination-race and teardown-failure controls to the new generated artifacts while preserving caller data, owned cleanup and honest retained receipts.
   - Retain alternate-source substitution and inward-import proofs using opaque non-UUID identities and compatible current contracts; exercise new shared meanings independently of TheBrain decoding where applicable.
   - Run cumulative public regression, lint/format and environment consistency checks; document intended v2 schema/output changes rather than weakening earlier acceptance behavior.

   **Stories:** 2–14, 17–22, 27–33, 38–42, 49–55, 58–65, 66–80.
   **Testing:** Combined Workflow/CLI/checker actual-output fixture; existing public failure-protection, source-substitution and architecture boundaries. No private archive is required for these tests.

10. **Independently verify complete preservation across all three real archives**

   **Blocked by:** 09.

   **What it delivers:** The complete Software Engineering archive and both earlier archives convert into fresh vaults, with source-derived preservation and reproducibility evidence independent of production expectations.

   **Acceptance outline:**

   - For each exact fingerprinted archive, run fresh exact, repeated and ZIP/root-record reordered conversions, producing nine complete accepted outputs without modifying source archives.
   - Extend the independent acceptance auditor using raw archives/outputs as expected facts; do not import production normalization/planning or treat production counts/manifests as the oracle.
   - Prove conservation of every record/field/history/identity, present payload hash/length, original backup/authored span/reference, classification assignment, graph/tag membership, created/uncreated target and materialization reason, exact warning conjunct, support/configuration artifact and actual inventory.
   - Independently prove the new archive's seven definitions, all 195 typed members and membership sizes, explicit member icon override, exceptional active note/image, four zero-length source gaps, four intact PDFs and four reviewed videos while auditing all 372 items, 693 relationships, 254 attachment records and 232 present payloads.
   - Verify earlier source tag, hierarchy, note/reference/resource, empty-target, warning and publication behavior under the accepted v2 output/schema additions.
   - Add meaningful corruption proofs showing that independent checks detect missing/altered source material, incorrect assignments/selection, fabricated warnings and missing/tampered support artifacts. Record repeat/reorder equivalence exceptions for original evidence ordering, source fingerprints and explicit run metadata.
   - Keep raw inputs, outputs, receipts and extracts ignored/private; publish aggregate coverage, discrepancies, commands and limitations. Repair failures through the responsible feature boundary and repeat affected/full acceptance as justified.

   **Stories:** 1–33, 41–42, 52–65, 72–74, 78–82.
   **Testing:** Independent full-archive exact/repeat/reordered audit and its synthetic corruption controls; use the completed integrated converter, not the prototype or convention checker as preservation proof.

11. **Accept actual v2 vaults in Obsidian and finish delivery guidance**

   **Blocked by:** 10.

   **What it delivers:** The user reviews the actual independently verified vaults in standard Obsidian and receives the final installation, library/CLI, maintenance and limitations guidance for a finished v2.

   **Acceptance outline:**

   - Preserve audited outputs and perform Computer checks on fresh review copies of all three actual full converter outputs, recording the real application version and private native evidence.
   - Verify Home/bookmark/overview, representative complete category membership, Members/Gallery, Icon-before-Note with no Appearance display, inherited/overridden/blank/invalid-provider behavior and separately editable body icons.
   - Exercise native full-template insertion/date initialization on new notes, direct existing-note membership edits, link-preserving category rename with contextual discovery, stable identity and shortened links, plus future-category/manual membership discovery.
   - Review the unusual Markdown/local image, intact PDFs, URL/embed/timing and accepted Search/remote limits, along with earlier source tags, hierarchy, resources, Backlinks, Graph and intentional uncreated targets.
   - Run the public checker on representative valid/invalid edits and explain that it reports without repair or source-preservation claims. Leave original vaults/Brains unchanged and remote playback paused.
   - Finish the accurate installation/environment, library/CLI/schema, property/template/rename/checker, reference-adaptation, source-feature and native-review guidance; do not present prototypes or accepted limitations as equivalent source functionality.
   - Complete an independent specification/standards review and final applicable public/tooling/acceptance checks, with no unresolved in-scope defects. Obtain and record the user's actual converted-vault verdict before declaring v2 finished; repairs repeat affected automatic, independent and native evidence.

   **Stories:** 1–82, with final acceptance ownership for 34–51, 56–60, 66–72, 79–82.
   **Testing:** Computer review of actual audited outputs, read-only checker behavior on review copies, final public/tooling gates and independent implementation review. Native inspection remains representative; independent audit establishes complete preservation.

## Dependencies and the execution frontier

The minimum blocker sets are:

| Slice | Direct blockers |
| --- | --- |
| 01 | None |
| 02 | 01 |
| 03 | 02 |
| 04 | 03 |
| 05 | 01 |
| 06 | 01 |
| 07 | 01 |
| 08 | 04 |
| 09 | 05, 06, 07, 08 |
| 10 | 09 |
| 11 | 10 |

Only 01 can start initially. After it, metadata/icons and the three separate source-content/resource capabilities are logically independent. Dashboard/template delivery extends metadata; the checker waits for the actual conventions and native starter artifacts. The combined integration proof joins those features, the independent real-archive audit follows the integrated result, and native final acceptance follows audited outputs. Transitive blockers are omitted. Logical independence does not authorize conflicting concurrent edits to shared adapter/contracts modules; execution follows the approved frontier and uses appropriate isolation if parallel work is later authorized.

No implementation ticket depends on Wayfinder ticket numbers. Once published, dependencies and claims are local to this implementation set. The final ticket contains the exact delivery/user-acceptance gate, so publication of tickets cannot complete the overarching finished-v2 destination.

## Story ownership

The detailed scope above provides overlap where a concept needs source, presentation and final acceptance evidence. The primary ownership map below ensures no story is left only to the final review ticket:

| Spec stories | Primary implementation owner(s) |
| --- | --- |
| 1 | 10, 11 |
| 2–4 | 01, 09 |
| 5 | 01, 03 |
| 6–10 | 02, 05, 09 |
| 11–14 | 01, 09 |
| 15–22 | 01, 03 |
| 23–27 | 03 |
| 28–33 | 02, 03 |
| 34 | 03, 04 |
| 35–40 | 04 |
| 41–43 | 02, 04 |
| 44–48 | 04, 08 |
| 49–50 | 03, 04 |
| 51 | 08 |
| 52–53 | 05 |
| 54–57 | 06 |
| 58–60 | 07 |
| 61–65 | 01, 05, 06, 07, 09 |
| 66–72 | 08, 10 |
| 73 | 09, 10 |
| 74–75 | 01–09 |
| 76–78 | 01, 08, 09 |
| 79–80 | 01–11 |
| 81 | 11 |
| 82 | This breakdown/publication, 10, 11 |

## Approval and publication

The user approved these ticket sizes, deliverables and blocking edges on 2026-10-04 with “Agreed”. The [to-tickets skill](C:/Users/stefa/.agents/skills/to-tickets/SKILL.md) approval gate is satisfied. All 11 slices are published individually in the [implementation index](README.md); only 01 is initially unblocked. Each ticket retains the approved scope, acceptance criteria, story coverage and testing boundaries. No implementation is claimed complete, and no parent issue or specification was changed.

Independent documentation validation subsequently clarified inspection versus publication and assigned first Bases enablement to dashboard ticket 03, with ticket 04 retaining/verifying that configuration. Story 34 therefore has owners 03 and 04. The approved ticket sizes and blocker graph remain unchanged. The specification's folder-layout wording was clarified to match the already accepted root Categories/Templates arrangement and Bases beneath Templates.

The same validation made materialized source-tag notes explicit in ticket 02's imported metadata/date coverage and synthetic case. Parent Wayfinder navigation was subsequently reconciled in a separate validation bookkeeping operation; parent records remained unchanged during to-tickets publication itself.
