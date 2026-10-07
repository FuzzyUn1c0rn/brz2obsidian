---
status: accepted
---

# Use a source-neutral core with inward Pydantic contracts

Although initial conversion supports TheBrain BRZ only, the pure migration core receives source-neutral Pydantic facts and reviewed policy from outer source modules, while source interpretation, payload access, orchestration, and filesystem publication remain outside it. This deliberately accepts Pydantic as a core model dependency and avoids separate parallel model families, while allowing another source module to reuse the planner, Obsidian renderer, and publisher when its meanings fit the shared contract. Tests exercise the module interfaces, with a test-only alternative source proving substitution and dependency checks preventing imports from the core onto outer implementations; the accepted decisions are recorded in [Agree acceptance checks and the implementation specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/56).

The [accepted first-version specification](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/10) defines the concrete interfaces and verification gates; its [implementation index](https://github.com/FuzzyUn1c0rn/brz2obsidian/issues/4) tracks delivery.
