# Bounded native investigation

Use this procedure for source-application diagnosis and content-retrieval
experiments. Rendering and acceptance reviews use the existing
[visual sampling policy](../testing.md#visual-sampling-policy).

## 1. Define the question and first batch

Read existing source inventories, research and relevant ticket decisions first.
Use archive/file inspection or available programmatic tools for facts they can
establish; reserve native interaction for the missing application observation.

Record a short plan in the active ticket or its research handoff:

- **Question and decision:** the specific uncertainty and which conversion or
  implementation decision its answer changes.
- **Known evidence:** original input/reference identity and facts already checked.
- **Cases:** exact subject/file identities, why they differ and an appropriate
  present-content control. Start with one to three representative cases; justify
  a larger initial batch by the distinct questions it covers.
- **Limit:** a concrete case/operation count or time limit for this batch.
- **Stop condition:** what observation answers the question, and what evidence
  would require a different case or another batch.

Separate diagnosis from a user-requested complete recovery. If complete recovery
is the task, use a first batch to validate the method, then finish the authorized
scope. For an archive-only conversion, retrieved content is a diagnostic control;
the conversion design must work from the supplied archive without routine native
retrieval or a fresh backup.

Use isolated source/review copies and preserve original inputs according to
[workspace housekeeping](../workspace.md). Keep private probes/screenshots under
`tmp/<effort>/`; retain aggregate findings in the feature's versioned records.

Complete planning when the cases, limit and observable stopping condition are
recorded. This is agent preparation, not an additional user-approval gate.

## 2. Inspect the first result before repeating retrieval

After the first retrieval, inspect its actual bytes/content and references before
repeating the same action across similar subjects. Compare with what the original
archive already supplies: note text, owned images, icons and other resources are
different roles. Observe a referenced image when its content matters to the
question. A tiny or blank-looking Markdown wrapper can display substantive content.

Finish the selected batch, or stop earlier when its question is answered. At the
batch limit, record an unresolved result rather than silently extending the run.
Distinguish observed native behavior, archive/byte facts and inference. Explain
what the result means for conversion and what remains unknown before starting
routine bulk retrieval. Carry an actionable result into policy, a synthetic
control or a prototype while preserving its evidence limits.

Complete this batch when the decision has bounded evidence, or the unresolved
question and next useful observation are explicit. Official format semantics or
root cause may remain unknown when the conversion decision does not depend on them.

## 3. Expand only for a concrete evidence gap

Start another bounded batch when a decision-relevant uncertainty remains, a
distinct source shape needs observation, or a failure/contradiction challenges
the current conclusion. Record the gap, selected additional cases and new limit.
Reuse observations for equivalent cases when their source/app context still applies.
For complete recovery, proceed through the remaining requested population once
the method is validated; verify its completeness separately.

Stop native diagnosis once its decision is supported. Report the sampled subjects,
observed behaviors, conversion implications, unresolved facts and limits in the
ticket/research record. A sample does not prove all absent bodies have the same
content. Keep mandatory full automated source/body/image/preservation audits and
any required actual-user acceptance at their agreed scope.

## Example: absent notes with available owned images

To decide whether an original BRZ can display important images without routine
TheBrain retrieval, begin with an absent ordinary note owning a WEBP, a distinct
PNG case if present, and a present image-note control. Inspect a retrieved wrapper
immediately and join its image reference to the original archive bytes.

If these controls show wrappers around already-archived images, explain that
native retrieval adds note Markdown while the original already supplies those
image bytes. This supports investigating an archive-only image fallback with an
explicit missing-text notice. It does not establish that unseen notes contain no
prose, captions or layout, or that missing icons share the same behavior.

Recovering every similar note is unnecessary for that bounded design decision;
expand for distinct/contradictory cases or a task requiring complete recovery.
The [historical recovery report](https://github.com/FuzzyUn1c0rn/brz2obsidian/blob/05b36923cd330261973bd35e19e6fa20ada88290/docs/history/management-leadership-wayfinding/research/native-source-recovery.md)
records the earlier complete recovery and its limits; it is evidence, not a
required preparation step for future conversions.
