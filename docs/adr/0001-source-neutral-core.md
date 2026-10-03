---
status: accepted
---

# Use a source-neutral core with inward Pydantic contracts

Although initial conversion supports TheBrain BRZ only, the pure migration core receives source-neutral Pydantic facts and reviewed policy from outer source modules, while source interpretation, payload access, orchestration, and filesystem publication remain outside it. This deliberately accepts Pydantic as a core model dependency and avoids separate parallel model families, while allowing another source module to reuse the planner, Obsidian renderer, and publisher when its meanings fit the shared contract. Tests exercise the module interfaces, with a test-only alternative source proving substitution and dependency checks preventing imports from the core onto outer implementations; the accepted decisions are recorded in [Agree acceptance checks and the implementation specification](../../.scratch/brz-to-obsidian/issues/06-implementation-specification.md).

The [accepted first-version specification](../../.scratch/brz-to-obsidian-v1/spec.md) defines the concrete interfaces and verification gates; its [implementation index](../../.scratch/brz-to-obsidian-v1/README.md) tracks delivery.
