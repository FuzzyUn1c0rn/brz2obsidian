---
name: to-spec
description: "Synthesize the current conversation into a proportional specification; publish only when requested or already authorized."
disable-model-invocation: true
---

This skill produces a spec from the current conversation and codebase understanding. Synthesize settled decisions; ask only for missing material decisions as described below.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't
already. Consult the glossary when domain terminology or behavior is relevant,
and use its vocabulary throughout the spec. Read applicable ADRs when
investigating or changing architecture, module boundaries, or public interfaces.

2. Use testing boundaries specified in the conversation, accepted specification,
or ticket, recording their decision source. If none is specified, select an
established public interface that can demonstrate the requested behavior, and
record the choice and rationale in the spec. Existing decisions are sufficient;
do not reopen them.

Ask when a material interface or acceptance decision remains unresolved, or the
choice would contradict an explicit testing decision. Recommend a suitable
public boundary and explain which observable behavior it can establish. Label
the recommendation as proposed, record the decision as pending, and ask a focused
question about that missing decision. Complete independent synthesis while it
is pending.

3. Write the spec using the template below, proportional to the accepted scope.
Publish it when requested or already authorized. A draft-only or read-only
request returns the specification in the conversation. Mark published work
`ready-for-agent` only when necessary scope and testing decisions are settled;
retain unresolved decisions explicitly rather than inventing requirements.

<spec-template>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A concise numbered list covering the accepted user capabilities and material
edge cases. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

Include only stories needed to describe the agreed feature; avoid repetition
and speculative capabilities beyond its scope.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
