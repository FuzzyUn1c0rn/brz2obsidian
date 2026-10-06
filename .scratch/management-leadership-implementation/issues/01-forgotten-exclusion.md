# 01: Exclude forgotten thoughts throughout inspection and conversion

Status: claimed
Assignee: /root/forgotten_implementer
Approved: 2026-10-06
Specification: [Accepted conversion specification](../spec.md)

**What to build:** Inspect and convert a supported archive with forgotten thoughts into a fresh vault that contains only included thoughts and safe evidence. The source archive stays unchanged; excluded thoughts leave no destination artifacts or identifying audit traces.

**Blocked by:** None (can start immediately).

## Acceptance criteria

- [ ] Default exclusion applies to every BRZ archive from a valid populated ForgottenDateTime, independently of attachment state. There is no include-forgotten option. Establish trustworthy identities/ownership before scoping; malformed scope markers and unsafe source identities/paths still refuse.
- [ ] Excluded subjects contribute no assigned/reserved target, note, owned local/external asset, original copy, icon/provider effect, classification/tag membership, relationship, stub, warning subject, individual exclusion identity/list/count, associated raw record or unsafe history. Included counts describe included scope. Omitted subjects cannot affect collision names, greedy selection or ordering.
- [ ] Remove an entire authored linked phrase/embed resolving to an excluded subject, including label/target, without a plain-text reminder or deletion marker. Preserve other text, code literals, Unicode and newline spelling. Unknown nonexcluded targets retain refusal. No title/pixel matching removes unrelated included content.
- [ ] Preserve byte-exact safe originals and provably included raw evidence with original values and omission/null distinctions. Omit unsafe exact originals rather than editing and calling them exact; omit unsafe fields/records/whole unscopable history collections. Raw spans, embedded state-map keys and guide-linked evidence cannot reintroduce exclusions.
- [ ] Excluded providers remove membership/appearance effects, letting included members proceed under ordinary included selection; do not create category placeholders. An excluded designated Home retains required-entry refusal, with no replacement Home. Parse/refusal/failure output must not echo excluded identities, titles or content.
- [ ] Public inspect/convert workflow and text/JSON wrappers expose the scoped behavior and honest source measurements. Source-neutral contracts and policy, source module/profile, renderer and serialized result/record schemas advance to 3, package to 0.3.0; format stays 5. Establish the accepted common optional source-gap/generated-presentation contract and serialized shape with empty facts now, so later slices populate rather than silently redefine the closed version-3 shape. Preserve signatures/outcomes/exits, reject incompatible versions, and keep the separate checker at schema 1 unless its public shape changes. New absence features remain refused until their behavior slices land.
- [ ] A complete handwritten synthetic conversion proves owned content removal, incoming references, exact-copy conflicts, raw evidence/history, collisions, relationships, assignments, excluded provider/Home, malformed scope markers and unknown targets. Same-title/same-pixel included controls survive. Inspect, output inventories/bytes, manifests, records, reports and failures are checked from raw fixture facts.
- [ ] Retain inward import barriers, injected interfaces and a non-UUID alternate source on current source-neutral contracts with empty new optional facts. Update affected existing acceptance-oracle/version expectations so existing public checks remain green, without deferring known failures to a later ticket.
- [ ] Document the default scope, safe-copy tradeoff and changed public versions alongside the behavior. Use the project environment; existing applicable regressions pass. Record bounded proof and limits without claiming full original-archive conversion.

## Verification boundary

Actual synthetic ZIPs through public inspect/convert, thin text/JSON commands and output/source inventories. Use existing public source/core/renderer boundaries only for higher-level-impractical contract failures. No private-helper or new runtime test seam.

## Specification coverage

User Stories 15–16, 32–39, 49–50, 56–57, 60–62, 69–70; Implementation Decisions 1–8, 20–21, 23, 25; Testing Decisions 1–3, 5, 7, 10, 16–17, 20. Read the accepted specification; these references identify emphasis, not permission to ignore cumulative requirements.

## Comments

- 2026-10-06 (/root): Claimed the initially unblocked slice for an isolated
  implementer based on `codex/management-leadership-v3`, planning commit
  `bb7a5ab6506dce699bb7d8373bf04a25375d5979`. TDD seams are already confirmed in
  the accepted specification; no new user testing approval is needed.

- 2026-10-06 (/root): Published after the user approved all nine tickets and their
  dependencies, then explicitly invoked implement-spec for complete implementation.
