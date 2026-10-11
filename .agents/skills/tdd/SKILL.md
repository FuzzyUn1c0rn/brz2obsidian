---
name: tdd
description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
---

# Test-Driven Development

Build one behavioral slice at a time through a public interface: a failing test,
the implementation that makes it pass, then the next slice. Use independently
derived expectations so the test can catch an incorrect implementation.

When exploring the codebase, read `GLOSSARY.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification: "user can checkout with valid cart" tells you exactly what capability exists, and it survives refactors because it doesn't care about internal structure.

Read [tests.md](tests.md) when choosing test cases and [mocking.md](mocking.md)
when deciding how to isolate an external dependency.

## Seams: where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

Use the testing boundaries already approved in the conversation, accepted spec,
or ticket. Record the selected interfaces and their approval source in the test
plan; that existing approval is sufficient for tests within those boundaries.

Ask for a decision only when no boundary has been agreed or the change needs a
new interface or materially different testing boundary. State the missing
decision and propose the highest suitable public interface. Continue independent
work while it is unresolved; write the dependent tests once it is settled.

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
claiming completion. The agreed seam and behavioral assertions remain the testing boundary.
Select focused tests for the changed behavior and affected consumers; broaden or
repeat checks only for changed scope, failures, unresolved risks, or a mandatory
acceptance requirement. A small non-behavioral correction does not require new
tests merely because this skill is available.

## Rules of the loop

- **Red before green.** Write the failing test first, then only enough code to pass it. Don't anticipate future tests or add speculative features.
- **One slice at a time.** One seam, one test, one minimal implementation per cycle.
- **Keep refactoring separate from the behavioral slice.** Review it against the
  repository's architecture and existing behavior before merging.
