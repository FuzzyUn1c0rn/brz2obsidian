# Find the route from a BRZ archive to an Obsidian vault

Status: resolved
Labels: wayfinder:map

## Destination

An agreed, implementation-ready specification for a Python CLI that migrates a TheBrain BRZ archive into a new Obsidian vault, preserving content, associated files, hierarchical context, and usable connections. Reaching this destination settles the decisions needed to implement and verify the converter.

## Notes

- This effort is planning. Research and a disposable vault prototype support decisions; production implementation is a later effort.
- The user confirmed on 2026-10-03: a specification is the destination; preserve content, files, and relationship meaning; perform a one-time migration into a new vault; standard Obsidian is the baseline; use the supplied export and verified same-format archives as initial coverage.
- Later refinements to empty-thought handling and relationship-preservation priorities are recorded in [Choose note identity, relationships, and vault layout](issues/03-vault-model.md). Use those accepted constraints when continuing design.
- Acceptance starts with two real exports in `brz/`: the updated `D&D_ The Rise of Anzoras 2026-10-03.brz` and the larger `Dungeons & Dragons 2026-10-03.brz`. These are real user data, not synthetic samples. Keep investigation local; publish structural findings rather than private titles or note text.
- The user resumed research on 2026-10-03 after updating the first export and adding the second. Verify each archive's declared exchange format and compare their feature coverage. The earlier inventory described the superseded first export only.
- The user identifies the source application as TheBrain 15. Treat that as the application-version context for the fixture and UI guidance; the two inspected archives independently declare exchange format 5. The exact application build has not been recorded.
- Use [the glossary](../../GLOSSARY.md) for domain vocabulary. Consult wayfinder, grilling, and domain-modeling for decision sessions; research for research tickets; prototype for the vault trial.
- Follow [the local tracker conventions](../../docs/agents/issue-tracker.md). Find the next ticket by querying child files for open, unblocked, unclaimed status; the map does not duplicate the open-ticket list.
- The user requested on 2026-10-03: after asking human questions, pause work until the user replies. Leave a durable copy of questions in the final message; do not continue background work while awaiting their answers.
- The user emphasized on 2026-10-03: use Obsidian's built-in Backlinks, Graph, Tags/search, and ordinary navigation; do not build replacements. Generated sections and conditional listings should carry source meaning that has no native or endpoint-note home. [The vault trial](research/vault-trial.md) records the native checks, positive human verdict, and source Home prerequisite.
- Human review on 2026-10-03 found the prototype quite good and identified a home-thought requirement: preserve a clearly recognizable designated entry note in the migrated graph. [Verify how BRZ identifies the home thought](issues/11-home-thought-evidence.md) supplies source identity evidence; the [completed vault trial](research/vault-trial.md) confirms the accepted root-level Home representation and native access. This role does not authorize inventing new hierarchy edges or guessing a graph root.
- The final accepted specification is in the [separate implementation area](../brz-to-obsidian-v1/spec.md). The local `spec.md` remains a compatibility pointer for earlier links.
- Installed Windows Python 3.14.8 was used for archive research and independent verification. The inspection script's 3.11+ declaration is a minimum requirement. WSL may be used when useful; do not assume WSL is a runtime requirement for the converter.
- During conversion-contract grilling on 2026-10-03, the user explicitly prioritized building the first version around simpler verified Brains. Investigate new features, the unknown TXT payload purpose, and substantially larger archives as later Brains require them; those extensions do not block the present specification.
- The user requires reusable deep modules and inward dependencies: source-neutral strict Pydantic contracts, pure core analysis/planning, outer source/rendering/publication modules, reusable orchestration and a thin replaceable CLI. Another compatible source module must be swappable without changes to generic conversion modules. [Agree acceptance checks and the implementation specification](issues/06-implementation-specification.md) records these confirmed decisions.
- On 2026-10-03 the user accepted the consolidated specification and requested the to-spec template. The [accepted specification](../brz-to-obsidian-v1/spec.md) is published as ready-for-agent with the [initial folder-layout proposal](../brz-to-obsidian-v1/architecture-layout.md) linked alongside it. The wayfinding destination is complete; the [implementation tickets](../brz-to-obsidian-v1/README.md) track implementation and its verification separately.

## Decisions so far

<!-- One named link and a short gist per resolved child ticket. Detail lives in the ticket. -->

- [Determine what the BRZ export can preserve](issues/01-brz-preservation-evidence.md): both format-5 archives expose recoverable graph/content/file records, with precise gaps in default relationship semantics and some attachment metadata.
- [Establish what standard Obsidian can represent](issues/02-obsidian-representation-evidence.md): native links, properties, files, and optional Canvas offer preservation mechanisms, with graph, naming, and rendering limits to address in the design and trial.
- [Verify hierarchy and default direction with a controlled export](issues/07-relationship-fixture.md): observed child records store parent A / child B; default direction is a sentinel, and an explicit arrow is distinct from both hierarchy and the one-way flag.
- [Verify reverse arrows and one-way relationship behavior](issues/08-reverse-and-one-way-evidence.md): controlled jumps confirm values 3/5/7 and show that One Way controls neighbor visibility, with previous-thought context affecting the immediate view.
- [Verify uncreated targets and empty-thought hierarchy coverage](issues/09-uncreated-target-evidence.md): native uncreated links are feasible, but 7/4 hierarchy relationships need context outside their absent endpoint files; tag content also needs preservation.
- [Quantify creating parents for uncovered hierarchy relationships](issues/10-parent-materialization-evidence.md): the proposed parent-note exception requires 5/2 extra ordinary notes in the supplied exports; reuse and deterministic selection matter for other graphs.
- [Choose note identity, relationships, and vault layout](issues/03-vault-model.md): use readable names, uncreated empty targets with a parent-note exception, simple relationship/resource sections, native tags and small fallback listings, and a separate JSON migration record.

- [Verify how BRZ identifies the home thought](issues/11-home-thought-evidence.md): derive the home setting with UUIDv5(BrainId, `"20"`) and resolve its Value by thought identity; the controlled home change distinguishes designation from activation and hierarchy.
- [Validate the proposed vault in Obsidian](issues/04-vault-trial.md): human accepted the representation with an always-created root Home note, native bookmark/startup selection, and verified native links, discovery, and selected resource rendering.
- [Choose the conversion and failure contract](issues/05-conversion-contract.md): human confirmed the CLI/new-vault contract, verified-feature boundary, deterministic naming/parent coverage, source retention, and explicit warning/failure reporting.
- [Agree acceptance checks and the implementation specification](issues/06-implementation-specification.md): human confirmed reusable source-neutral inward contracts and seams, concrete schemas/tooling, full preservation/native acceptance gates, and the published specification.

## Not yet specified

<!-- No open decision tickets or unticketed decisions remain within the agreed scope. The user accepted the final specification, completing this map. -->

## Out of scope

- Production converter implementation during this wayfinding effort: the agreed destination is its specification.
- Synchronizing TheBrain with Obsidian or merging into a vault the user has already edited: the target is a new vault for a one-time migration.
- Recreating TheBrain's full application or navigation experience: preserve relationship meaning in standard Obsidian.
- Universal compatibility across TheBrain versions: establish coverage from inspected archives and report unsupported formats explicitly.
- Investigation of features, absent-payload patterns, or substantially larger Brains beyond the verified initial coverage: extend support when later source evidence requires it. The known TXT purpose can be investigated later; its explicit warning policy is settled in [Choose the conversion and failure contract](issues/05-conversion-contract.md).
- Requiring community plugins for the baseline vault.
- Emulating TheBrain's arrow/one-way navigation solely for fidelity: the user accepted simplifying those details in [Choose note identity, relationships, and vault layout](issues/03-vault-model.md). Hierarchical context remains in scope.
