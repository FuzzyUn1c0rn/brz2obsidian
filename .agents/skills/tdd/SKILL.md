---
name: tdd
description: Test-driven development for features, behavior-changing fixes, and integration tests.
---

# Test-Driven Development

Build one behavioral slice at a time through a public interface: a failing test,
the implementation that makes it pass, then the next slice. Use independently
derived expectations so the test can catch an incorrect implementation.

Consult `GLOSSARY.md` when domain terminology or behavior is relevant so test
names and interface vocabulary match the project's domain language. Read
applicable ADRs when investigating or changing architecture, module boundaries,
or public interfaces. Proceed silently when these documents are absent.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification: "user can checkout with valid cart" tells you exactly what capability exists, and it survives refactors because it doesn't care about internal structure.

Read [tests.md](tests.md) when choosing test cases and [mocking.md](mocking.md)
when deciding how to isolate an external dependency.

## Seams: where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

Use testing boundaries specified in the conversation, accepted specification,
or ticket, recording their decision source. If none is specified, select an
established public interface that can demonstrate the requested behavior, and
record the choice and rationale in the test plan. Existing decisions are
sufficient; do not reopen them.

Ask when a material interface or acceptance decision remains unresolved, or the
choice would contradict an explicit testing decision. State the missing decision
and propose a suitable public interface. Continue independent work while it is
unresolved; write the dependent tests once it is settled.

When the interface's shape is itself in question, read the `codebase-design`
skill for its design vocabulary and decision criteria.

## Anti-patterns

- **Implementation-coupled**: mocks internal collaborators, tests private methods, or verifies through a side channel (querying the database instead of using the interface). The tell: the test breaks when you refactor but behavior hasn't changed.
- **Tautological**: the assertion recomputes the expected value the way the code does (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code. Expected values must come from an independent source of truth: a known-good literal, a worked example, the spec.
- **Horizontal slicing**: writing all tests first, then all implementation. Bulk tests verify _imagined_ behavior: you test the _shape_ of things rather than user-facing behavior, the tests go insensitive to real changes, and you commit to test structure before understanding the implementation. Work in **vertical slices** instead: one test → one implementation → repeat, each test a **tracer bullet** that responds to what the last cycle taught you.

## Check execution

Run each RED/GREEN pytest selection through
[the repository runner](../../../docs/testing.md#automated-check-runner).
Keep the failing receipt and its output; a later passing run is separate evidence.
Validate the final receipt against independently recorded required scope before
claiming completion. The selected public interface and behavioral assertions
remain the testing boundary.
Select focused tests for the changed behavior and affected consumers; broaden or
repeat checks only for changed scope, failures, unresolved risks, or a mandatory
acceptance requirement. A small non-behavioral correction does not require new
tests merely because this skill is available.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Keep refactoring separate from the behavioral slice.** Review it against the
  repository's architecture and existing behavior before merging.
