# Agree acceptance checks and the implementation specification

Status: resolved
Type: grilling
Labels: wayfinder:grilling
Parent: [Find the route from a BRZ archive to an Obsidian vault](../map.md)
Blocked by: 05
Assignee: /root

## Question

Which acceptance checks and implementation boundaries make the agreed conversion contract precise enough to implement without reopening design decisions?

Agree how to verify content and file preservation, source-to-vault identity mapping, each supported relationship's meaning, valid internal references, filename collisions, and explicit accounting for unsupported or missing source data. Define how to compare the real export with the output and which small synthetic cases are needed beyond that export.

Use the evidence to choose the parser/model/writer boundaries and development sequence at the level needed for implementation. Identify any remaining blockers and graduate genuine fog into new decision tickets before declaring the route clear.

Once the human agrees the contract and checks are complete, capture the implementation-ready specification in `../spec.md`, linking the tickets and evidence that support it. Resolve this ticket only when the specification has no unresolved decisions required before implementation.

## Comments

- 2026-10-03: Prerequisite [Choose the conversion and failure contract](05-conversion-contract.md) is resolved after the human confirmed Q44. This ticket is now unblocked and remains unclaimed. Its checks and implementation specification must follow the accepted contract; production implementation is a later effort.
- 2026-10-03: User requested "Grill next". Claimed before substantive work. Use grilling and domain-modeling, with codebase-design for the proposed implementation interfaces. The accepted contract is fixed; this ticket chooses acceptance evidence, module responsibilities, development sequence, and specification precision. Pause all work after asking a decision round. Production implementation is outside this effort.

### Design tree and first frontier

These proposals are not accepted until the human answers. A delegated read-only fact check is verifying the existing acceptance baselines before the round is presented. The user is not asked to establish facts available in the repo.

- Q45 — Preservation proof: require full conversion and independent source/output comparison for both exact real acceptance archives. Check every present payload and original-note backup byte-for-byte; compare all exported JSON records/fields semantically; verify all identities and target mappings, every accepted hierarchy/jump/tag representation, and every adapted local reference. Verify source Markdown outside explicitly allowed adaptation spans, accounting for every source item and known warning. Counts are useful regression evidence, not the sole proof. Do not accept merely because the converter's own validation says success.
- Q46 — Contract edge cases: use small shareable synthetic archives with expected observable results, covering empty Home, empty parent chains/cycles/multiple parents, isolated/Related/tag uncreated cases, duplicate/unsafe/reserved/long names and ID-prefix collisions, code examples versus actual links, ordinary-to-tag hierarchy, forgotten versus deleted items, unsupported features, missing required bytes, the exact known-TXT warning pattern, invalid Home/IDs/references, nonempty destinations, and failed-write cleanup/publication. Test public/module interfaces and generated artifacts rather than mirroring private helpers. Keep real source data/vault output local under ignored brz; normal automated checks use synthetic fixtures.
- Q47 — Reproducibility: require identical assigned relative targets, thought-note content, copied bytes, relationship/tag presentation, and source-to-target mappings for repeated conversions with the same source/configuration. Equivalent source/ZIP order variations must not alter these logical outputs or greedy choices. Explicit run metadata, destination paths, archive fingerprints, and faithfully retained source-record ordering may legitimately differ; define those exceptions in the specification. No globally optimal parent count is required.
- Q48 — Implementation interfaces: share one archive reader/analyzer between inspect and convert; retain original records alongside a checked source model. A deterministic planning module selects files, identities, links, tags, and issues before output is written. A writer renders/copies into staging, checks output against the plan, and publishes it. Keep CLI argument handling/result formatting thin. Use concrete modules and small interfaces, without a speculative plugin/adapter framework. Test the interfaces that callers use.
- Q49 — Native application acceptance: after automatic verification, review each newly generated real vault in standard Obsidian. Check Home at root/bookmark/startup, hierarchy and uncreated-target click-to-create/backlinks, tag discovery, and selected real inline images/PDF/resource links. Use fresh vaults only. Reuse the accepted prototype as baseline evidence, but verify the actual converter output as well. Selected rendering checks plus full byte/content checks establish first-version acceptance; reviewing every note/PDF page is not required.
- Q50 — Development sequence: implement one small synthetic end-to-end inspect/convert path first, then complete verified feature mappings and failure handling, then full independent regressions on both real archives, then native Obsidian review and install/use documentation. Each stage has observable checks; the first version is accepted only when all agreed gates pass. Do not treat the disposable prototype as production-ready code or expand to bigger/unverified Brains before the initial coverage works.

After answers, settle any dependent details needed for an implementation-ready specification: versioned migration-record/CLI-result schemas, concrete dependency/testing choices, exact supported-feature predicates and naming/reference rules, and the final acceptance matrix. These are technical specification details constrained by the accepted policies; bring genuine new user decisions back as a round rather than silently assuming them. Present the consolidated specification for final shared-understanding confirmation before resolving this ticket. Stop all work after presenting Q45–Q50.

- 2026-10-03: Q45–Q50 are ready from the accepted contract and recorded trial evidence. The delegated baseline audit was interrupted before asking, so no background work remains active. No new totals are claimed from that unfinished audit; completing the acceptance-baseline table is factual work for the specification after the user's answers. None of the six policy questions depends on a fresh numeric total. All work pauses after the durable final-message round.

- 2026-10-03: User answered "Agreed" to Q45–Q50: full independent preservation checks on both real archives, synthetic contract-edge fixtures, logical reproducibility, shared archive analysis and deterministic planning, fresh-vault native Obsidian acceptance, and staged implementation are accepted. The user added an explicit architecture requirement: clear deep modules with small reusable interfaces; clean code/clean architecture; a very thin CLI; reusable business logic with archive input and vault output at outer I/O seams. They proposed the planner as the business logic and asked to stress-test these ideas. Q48's broad stages remain accepted; concrete dependency direction, validation responsibilities, rendering, payload lifetime, and reusable entry points are still to be settled with the human.

- 2026-10-03: Apply codebase-design's Design It Twice workflow to stress-test alternate interfaces before asking the architecture frontier. Frame constraints/dependencies and an illustrative sketch for the human, compare three delegated designs, and make a recommendation. The agents must finish before any user decision questions are presented, so the user's pause-all-work instruction is honored.

- 2026-10-03: User clarified that EVERY module must be reusable and that the core must not depend on the outer archive reader or vault writer. Dependencies point inward. The thin CLI is an outer entry/composition module configuring the modules; another interface can replace it. These are explicit requirements, not alternatives to ask again. The user also identified module interfaces as the seams and required tests there. Specify inputs, outputs, invariants, errors, resource lifetime, and dependency direction for each seam; test observable behavior through those interfaces. Pure module tests and real synthetic-archive/temporary-filesystem I/O tests serve different evidence needs.

- 2026-10-03: User additionally requested an initial code/folder-layout proposal. Three design comparisons finished: explicit functional pipeline, use-case orchestration through injected ports, and a reusable outer workflow facade. The third proposal combines common-caller depth with a pure core and reusable individual modules. The following initial proposal is design material only; no source packages or production code have been created. All agents have finished before the next decision round.

- 2026-10-03: User explicitly requested Pydantic models. This is a requirement. A focused delegated primary-source check is verifying Python 3.14 compatibility and validation/preservation behavior before finalizing model settings. Proposed placement is inward-owned data contracts, separate from the concrete I/O modules, with original source JSON preserved independently from normalized typed interpretations. The human still needs to settle whether Pydantic is the inner contract representation versus an outer validation-only representation; recommend inner Pydantic contracts for this project to avoid duplicate model families.

### Initial architecture and code-layout proposal

The dependency rule is already required: the core and inward data contracts import no archive reader, renderer, filesystem publisher, workflow, wiring, or CLI implementation. Each outer module depends on the data contracts; the outer workflow coordinates modules. The CLI composes/configures the workflow and translates structured results to terminal/JSON/exit codes. Another interface can replace it without importing cli.

The three examined alternatives were:

| Alternative | Depth and reuse | Cost |
| --- | --- | --- |
| Explicit reader → core → renderer → writer pipeline | Each module is directly reusable with a small interface | Every caller must manage correct sequencing and source-session lifetime |
| Application use-case module with injected source/destination ports | A small inspect/convert interface can hide the complete workflow | More interface machinery; calling I/O orchestration the business core would obscure the user's pure-core intent |
| Reusable outer workflow plus pure core and independent I/O modules | Common callers get inspect/convert; advanced callers can compose individual modules | One additional module, justified by lifecycle and error/publication handling |

Recommend the third shape, retaining the first shape underneath it. An archive reader is a concrete adapter/module; its interface is the seam, which can be expressed as a small port where a substitute is justified. A port declaration does not authorize a dependency from pure business code onto a concrete outer module.

Proposed initial layout (filenames are indicative until the architecture answers):

```text
pyproject.toml
README.md
src/
  brz2obsidian/
    __init__.py
    __main__.py
    contracts.py
    core/
      __init__.py
      analysis.py
      planning.py
    archive/
      __init__.py
      reader.py
      decoding.py
      notes.py
    obsidian/
      __init__.py
      rendering.py
    publication/
      __init__.py
      filesystem.py
    application/
      __init__.py
      workflow.py
      wiring.py
    cli.py
tests/
  core/
  archive/
  obsidian/
  publication/
  application/
  cli/
  fixtures/
  local_acceptance/
docs/
  architecture.md
  testing.md
```

Existing GLOSSARY, agent docs, research, and local tracker remain where they are. Private inputs/generated vaults remain under ignored brz. Checked-in fixtures use synthetic data. Packages expose their cohesive module interfaces; internal files may split for maintainability without becoming extra public interfaces. Keep contracts focused on immutable source facts, plans, artifacts, issues/results, and a small payload-access interface. They have no I/O or imports from implementation modules. Avoid a class per helper or a generic adapter registry.

| Module interface (proposed) | Responsibility hidden behind the seam | Main test evidence |
| --- | --- | --- |
| `archive.open_source(path) -> SourceSession` | ZIP membership, decoding/BOM, CRC/hash inventory, source-format interpretation, original record capture and asset lifetime | Real synthetic ZIPs, integrity/syntax failures, source consistency |
| `core.analyze(snapshot) -> Analysis` | Graph/live-reference/Home validity, supported migration semantics, exact warning/refusal policy | Source values with independently specified accepted/refused outcomes |
| `core.plan(analysis) -> MigrationPlan` | Eligibility, greedy coverage, stable names/tags, representations/adaptations, source accounting | Plans for contract scenarios and reordered equivalent inputs |
| `obsidian.render(plan, run_metadata) -> RenderedVault` | Markdown/link/frontmatter/report/record/config serialization, preserving nonadapted source spans | Exact selected generated artifacts and original-span preservation |
| `publication.publish(artifacts, payloads, destination) -> Receipt` | Destination/path checks, streaming, staging/output verification, publication/cleanup | Temporary directories, failing payload streams/writes, publication/cleanup outcomes |
| `application.Workflow.inspect/convert` | Shared preparation, sequencing, source lifetime, operation-level results | Synthetic end-to-end archive/vault tests and fault cases |
| `cli.main(argv) -> int` | Parsing, default wiring/configuration, terminal/JSON, 0/2/1 translation | Thin command smoke tests and result/exit behavior |

`analysis.py` and `planning.py` form one deep core module with two public operations. Other package modules similarly expose few operations, not all helper functions. `contracts.py` supplies inward-owned value/interface definitions and may split internally if it grows. Return durable structured values and typed/structured failures; reusable modules do not print, parse command arguments, or call sys.exit. The writer must consume assigned targets/copy instructions rather than make conversion-policy decisions. It must not import the concrete reader.

A possible common-caller interface is:

```python
workflow = application.create_default_workflow()
result = workflow.convert(source, destination)
# A Python caller or GUI consumes result directly.
# CLI formats it and chooses the agreed exit code.
```

An advanced caller can independently open a source, analyze/plan its snapshot, render it for preview, and publish using its payload provider. The core sees immutable values and opaque asset IDs, not source paths, ZIP handles, byte streams, or filesystem objects. The source-format adapter owns BRZ key derivation, compact GUID decoding, and source-note syntax interpretation; core owns the decision about whether interpreted facts/relationships/content can migrate and how. Preserve original records/text alongside normalized facts for traceability. Typed reference tokens/spans allow planning to resolve targets and rendering to apply approved edits without a second competing reference parser.

The proposed source session holds the archive open through conversion and exposes payload access by ID plus consistency verification. Inventory hashes/lengths are established by the reader; copies are streamed and checked before publication. A changed source refuses the run and cleans owned staging. The outer workflow owns the session lifetime and closes it before returning. Inspect results/plans returned to ordinary callers contain durable data, not live iterators. Copying all binary payloads into memory or a mandatory extra temporary archive snapshot is unnecessary for the first local-file adapter.

### Architecture frontier awaiting answers

The user's inward-dependency, all-module reuse, thin replaceable CLI, and interface-seam testing requirements are settled. These questions choose concrete responsibilities, not whether to follow those requirements:

- Q51 — Reusable orchestration: recommend an outer workflow with inspect/convert entry points, used by CLI and other callers, while keeping every lower module callable independently. It owns sequencing and source lifetime; the business core stays pure. The thin CLI selects/configures this workflow and translates results.
- Q52 — Validation/decoding split: recommend outer archive modules own source-format syntax/decoding and integrity (including Home-setting/compact-ID and source-note syntax interpretation), while pure core analysis owns live graph/Home validity, supported conversion meanings, required-content policy, and the exact warning exceptions. Return decoded facts/provenance rather than deciding eligibility inside the reader. Destination feasibility and I/O integrity belong to publication. This gives each failure category one responsible module.
- Q53 — Rendering split: recommend a semantic migration plan from core and a separate reusable pure Obsidian renderer. Core assigns identities/targets and what gets represented; renderer owns exact target syntax and generated bytes; publication owns filesystem effects. A preview caller can render without creating files.
- Q54 — Payload lifetime: recommend a reader-owned source session, outer-workflow-managed lifetime, and opaque asset IDs in the plan. Stream assets through a small payload interface, verify consistency/hashes before publication, refuse source mutation, and return durable results. The core never handles ZIP/stream/filesystem objects. Avoid mandatory loading/duplicating all large payloads.
- Q55 — Pydantic placement/settings: Pydantic is required. Recommend its models for inward source/analysis/plan/artifact/result contracts, with explicit strict validation, frozen models plus immutable collections, and closed normalized schemas. Retain every original source field in separate original evidence rather than relying on normalized model serialization for source preservation. This consciously makes Pydantic a pure model dependency of the library; the core still imports no outer implementation. The alternative is Pydantic at external decoding seams only plus a second family of plain core models, with more mapping/maintenance. Verify exact library behavior from primary sources before presenting this recommendation.

Delegated primary-source verification completed before questions. [Official PyPI](https://pypi.org/project/pydantic/) lists Pydantic 2.13.5, released 2026-08-28, with Python >=3.9 and explicit Python 3.14 support metadata; [official release](https://github.com/pydantic/pydantic/releases/tag/v2.13.5) identifies that stable release. Exact installed-interpreter compatibility has not been locally tested yet and belongs to implementation checks. [Strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/) is opt-in, type-specific, and different for JSON versus decoded Python inputs: choose explicit decoding into Python values and explicit adapter conversions into typed values, then strict core-model validation. Raw source records remain separately retained, including naive date strings. [Extra-data handling](https://docs.pydantic.dev/latest/concepts/models/#extra-data) defaults to ignore, which is unsuitable as a source-retention strategy; closed normalized models may forbid extras while original source evidence retains every field. [Frozen models](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability) are not recursively immutable, so collections require tuples/immutable ownership rather than mutable nested dict/list fields exposed as supposedly frozen values. [Serialization documentation](https://docs.pydantic.dev/latest/concepts/serialization/) reinforces that model dumps are normalized representations, not independent preservation proof. Pydantic is an acknowledged pure-library dependency of inward contracts; it creates no import from core onto a concrete outer module.

Pydantic SourceSnapshot/Analysis/MigrationPlan/RenderedVault/Issue/Result models belong in the proposed contracts module. The opaque payload-access interface can be a small Python typing Protocol there; it is a behavioral contract, not a BaseModel. Asset IDs, relative destinations, original source evidence, and structured outcomes are plain durable values. Source sessions remain outer resources rather than core models containing open file objects. Keep raw evidence isolated from validators to prevent mutation or information loss.

Present Q51–Q55 and the initial folder proposal together after factual verification finishes, then pause all work. After answers, finalize exact seam contracts and package layout, dependency/testing choices and schemas, then produce the specification for final shared-understanding confirmation. No production implementation is authorized by this planning ticket.

- 2026-10-03: User answered "agreed" to Q51–Q55. Reusable outer orchestration, split format/integrity versus semantic validation, separate pure Obsidian rendering, streamed reader-session payload lifetime, and inward Pydantic contracts are accepted. The user clarified the purpose of reuse: a future source module for another note-taking format should be swappable to produce an Obsidian vault. This is an architecture extensibility requirement, not a request to implement a second real format now. Stress-test source-neutral contracts, source-format-specific semantics/anomalies, source injection into the workflow, opaque identities and original-source preservation before finalizing the specification.

### Source-substitution refinement and frontier

Three delegated read-only design checks completed. The architecture can permit another source module without edits to the core, Obsidian renderer, or publisher when that source's meanings fit the shared contract. Parsing another container alone does not provide this: the source module must normalize its identities, content, relationships, resources, entry designation, and source evidence. New meanings that do not fit the contract still require later research/model/policy work, rather than silent flattening.

Propose a source-neutral Pydantic SourceSnapshot comprising items, relationships, documents, assets, original evidence, source findings and accounting. Item keys are opaque strings, not UUID-only fields. Each source module supplies a stable lowercase hexadecimal naming seed; BRZ uses the exact dashless source UUID to preserve the accepted suffix/folder rules. Core validates suitability/collisions and uses documented deterministic ordering; its BRZ tie behavior still follows source IDs. A future source uses an explicitly documented deterministic encoding/digest while retaining original IDs. Neither core nor renderer decodes GUIDs, ZIP paths, brain:// URLs, numeric source enums, or the Home setting formula.

Canonical relationship kinds include accepted hierarchy, Related, and tag memberships. Embedded document references are distinct facts and do not invent Related relationships. A document supplies supported Markdown with typed reference spans tied to that exact text; the source module protects code examples and decodes source target identities. Core resolves canonical references and targets; renderer applies approved spans. BRZ text remains unchanged outside allowed adaptations. A future rich-note source must provide an approved normalization and preserve its original, rather than claiming arbitrary rich-content support now. Original evidence can identify raw JSON records, text, or binary originals without forcing another source format to impersonate BRZ record files. BRZ retains all original JSON fields and original note bytes as already agreed.

The canonical entry designation is validated by core and maps to the existing root Home presentation. BRZ supplies the verified Home UUID. A future source must supply an explicit compatible entry designation; guessing an entry for a tool without that concept would require a later policy decision. Binary assets use opaque IDs, ownership, role, actual length/digest and availability; their access remains in the outer source session.

The exact missing-TXT predicate exposes a responsibility refinement: numeric Type/NoteType/state fields belong to BRZ interpretation, while permission to tolerate a gap belongs to migration policy. Recommend evidence-backed SourceFinding values with opaque versioned rule IDs. The BRZ classifier recognizes only the precise approved TXT/icon patterns; it does not set final severity or decide eligibility. An explicitly reviewed source policy, selected in outer wiring and supplied as inward data, states which recognized findings may continue as warnings. Core makes the warning/refusal disposition and accounts for every finding. Unknown rules, unsupported meanings and unmatched required missing content refuse. No caller/CLI arbitrary allowlist is added. The core contains no BRZ rule constants or numeric predicates; the initial reviewed BRZ profile supplies them through its source-module binding. This refines Q52's exact-predicate ownership without changing any accepted BRZ outcome.

Each adapter must account for all exported items and unsupported findings. The generic core verifies consistency/completeness of the declared snapshot, but cannot prove that a foreign parser never omitted an input item. Adapter-seam tests and independent raw-source/output preservation comparisons provide that evidence. Retaining an unknown item as raw evidence does not by itself approve loss of its meaning.

The workflow receives a source module through a small open-source/session interface. BRZ is selected by default wiring, not imported by the generic workflow, core, renderer, or publisher. The source module provides a compatible reviewed profile along with its opener; the workflow manages the session and passes normalized data/policy inward. This is explicit composition, not a dynamic plugin registry. Package initializers must not eagerly import BRZ when importing generic modules.

Update the initial proposed layout from `archive/` to:

```text
src/brz2obsidian/
  sources/
    thebrain/
      __init__.py
      reader.py
      decoding.py
      notes.py
      profile.py
tests/
  sources/
    thebrain/
    fake_source.py
```

Other approved module roles remain. The fake source belongs only to test support. Future production source packages are added only when a real new format is investigated.

Proposed substitutability acceptance: one small logical fixture has a real synthetic BRZ input and a test-only in-memory source with non-UUID raw/canonical item keys, no BrainId/settings/numeric TheBrain enums, and explicitly compatible stable naming seeds and migration facts. Run both through the same public generic workflow with only the source binding changed. Compare created/uncreated selections, assigned targets, note content, relationship/tag presentation, native configuration, copied bytes, logical counts and outcomes under a known fixture correspondence. Original source identities/provenance/fingerprints remain different and faithful; do not demand identical raw mapping or migration-record bytes. Ensure the non-UUID keys actually reach core, rather than translating every alternative source ID back to a UUID and masking a hidden requirement. Also exercise alternate-source stream failure, lifetime closure, source change, unsupported findings and invalid normalized references. Enforce inward imports and test generic operation without importing BRZ/CLI modules.

- Q56 — Shared identities and knowledge model: recommend source-neutral items/relationships/documents/assets/entry/evidence, opaque identities plus stable naming seeds, and supported Markdown/reference facts. BRZ-specific fields and decoding stay in its adapter; its exact existing migration behavior is preserved. Source-module replacement is sufficient for meanings that fit this model, not a promise about arbitrary new features.
- Q57 — Source-specific anomaly recognition: recommend the source module recognizes exact format-specific patterns and supplies evidence-backed findings. Core decides warning/refusal using an explicitly reviewed source policy supplied through composition. This refines the earlier validation split; BRZ's precise warning conditions/outcomes do not change, and unknown findings cannot silently continue.
- Q58 — Demonstrate replacement: recommend a test-only second source through the same workflow, with non-UUID identities and no BRZ-only metadata, plus an import-direction check. Keep another real note-taking format outside first-version implementation; the test proves the seam rather than claiming compatibility.

Q56–Q58 are proposals awaiting answers. Present the round and pause all work. After answering, complete remaining dependency/schema/seam-contract details and the draft specification for final human confirmation; this ticket is not resolved yet.

- 2026-10-03: User answered "agreed" to Q56–Q58. Source-neutral Pydantic contracts with opaque identities/stable naming seeds, source-owned exact anomaly recognition plus core disposition under an approved profile, and a second test-only source proving substitutability are accepted. Complete the concrete draft specification and factual acceptance/tooling details next. Present it for final shared-understanding confirmation before resolving this ticket or the map; production implementation is still outside scope.

### Consolidated specification for final confirmation

- 2026-10-03: Created the [draft implementation specification](../spec.md), consolidating accepted user behavior, verified source-feature predicates, naming/reference rules, reusable module interfaces and folder layout, strict immutable Pydantic contracts, source/session lifetime, publication guarantees, and the full acceptance matrix. [Use a source-neutral core with inward Pydantic contracts](../../../docs/adr/0001-source-neutral-core.md) records the accepted architecture; the glossary now distinguishes source collections/items/entry items from TheBrain-specific vocabulary.
- Fresh read-only verification on native Python 3.14.8 confirmed the exact acceptance fingerprints and expected complete output: A has 49 thought notes and 60 preserved payloads; B has 42 thought notes and 50 preserved payloads. Root Home is included in each note total; original-note backups are subsets of payload totals. The known 2/9 warning items make both expected conversions exit 2. These are specified expectations, not completed production results.
- Concrete version-1 model/result/record fields, structured failure contracts and stable issue codes are proposals under the accepted policies. The proposed tooling is Pydantic 2.x, markdown-it-py 4.2.x, pytest 9.x, Ruff 0.16.x and setuptools 84.x. Primary metadata/docs were checked; dependencies were not installed or tested in the native project environment. Native compatibility and exact source-position tracking for Markdown adaptation are explicit early implementation gates. No source code, package configuration, production tests or converter has been created by this ticket.
- Q59 — Final shared understanding: confirm the consolidated draft, including its concrete interfaces/schemas/tooling proposal and verification gates, or identify changes. Recommend confirmation: the specification preserves all accepted vault behavior, the core has no outer dependencies, other source modules can reuse the workflow for compatible meanings, and first-version acceptance requires full independent preservation checks plus fresh-vault native review. This ticket remains claimed pending the human's final response. Pause all work, including agents, after presenting Q59; do not resolve the ticket/map or start production implementation while awaiting review.

- 2026-10-03: User answered "i accept" to Q59 and explicitly requested applying the to-spec skill to the accepted file. Final shared understanding is confirmed, including module seams, inward Pydantic contracts, source substitution, concrete schemas/tooling, and acceptance gates. Applied the requested template without another interview; the already-confirmed seams satisfy its seam check. Published the [accepted specification](../spec.md) with Status: ready-for-agent and retained the requested [initial folder-layout proposal](../architecture-layout.md) as a linked companion artifact. Production implementation remains a separate effort.

## Answer

The user confirmed the consolidated specification on 2026-10-03. The [accepted implementation specification](../spec.md) now uses the to-spec template: problem, solution, 72 user stories, implementation decisions, testing decisions, out-of-scope boundaries, and further notes. It is published to the project's local tracker as ready-for-agent; this decision ticket is resolved.

The agreed architecture uses reusable source-neutral strict immutable Pydantic contracts, pure analysis/planning, outer source interpretation and payload access, pure Obsidian rendering, filesystem publication, reusable workflow composition, and a thin replaceable CLI. Core has no dependency on an archive reader/writer/CLI. A test-only alternate source with non-UUID identities proves substitution when source meanings fit the shared contract. The [architecture decision](../../../docs/adr/0001-source-neutral-core.md) and [initial folder layout](../architecture-layout.md) support that design.

Acceptance requires behavioral tests through module interfaces and the highest practical workflow seam, independent full-source preservation on the exact A/B archives, logical reproducibility, dependency-direction checks, source-substitution evidence, and fresh-vault native Obsidian review of actual converter output. Expected complete results are 49/42 thought notes including root Home, 60/50 byte-preserved payloads including original-note backups, and 2/9 known warning items. Counts alone do not establish preservation. Native dependency compatibility and exact Markdown source-span tracking are early implementation gates.

All implementation prerequisites within the agreed scope are specified. No production converter, package configuration, or automated converter tests were created during this wayfinding effort; no production acceptance has been claimed. The next effort may implement the accepted specification when the user directs it.
