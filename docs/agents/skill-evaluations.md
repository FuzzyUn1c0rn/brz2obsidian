# Skill behavior evaluations

Use the small [prompt corpus](../../.agents/evals/cases.json) when changing skill
activation, authorization, completion or verification rules. It includes positive
activation and adjacent negative requests, explicit read-only use, prior approval
reuse and prototype completion. Each run uses fresh synthetic files and copies
the current repository skills and shared agent guidance into its own Git root,
so it exercises the actual instructions rather than checking their wording.

Run with the project interpreter:

```powershell
.venv\Scripts\python.exe tools/skill_evals.py list
.venv\Scripts\python.exe tools/skill_evals.py run --case spec-approved-boundary
.venv\Scripts\python.exe tools/skill_evals.py run --case delivery-start-main --case delivery-ticket-progress
.venv\Scripts\python.exe tools/skill_evals.py run
.venv\Scripts\python.exe tools/skill_evals.py score 'C:\checkout\tmp\skill-evals\run-id\spec-approved-boundary'
```

`run` starts separate ephemeral Codex CLI runs, inheriting the user's configured
model and effort. Use `--codex` if the executable is not on PATH. Cases run
sequentially with a 180-second per-case timeout (`--timeout` overrides it).
Read-only cases use the read-only sandbox; local Git setup and artifact cases use
workspace-write in their disposable fixture. Fixture instructions prohibit
delegation and external mutations. No model settings or repository guidance are
changed by evaluation execution.

Cases may supply `initial_branch`, `prior_work` (committed feature files) and
`fixture_files` (raw scenario inputs). An explicit starting branch uses a `main`
baseline; a feature branch is created from it and prior work committed there.
The default remains `fixture`. Shared sources include the issue-tracker and
triage guidance so lifecycle decisions use the authoritative rules. Inspect
`before-git.json` and `after-git.json` for actual branch, HEAD, refs and status;
content guards alone do not detect Git metadata changes.

## Delivery lifecycle coverage

The `delivery-*` cases exercise the one-root/one-draft workflow. The first two
authorize actual local branch setup only. Other cases ask agents for bounded
decisions or source review against supplied synthetic issue/PR state; they do not
execute remote actions or subagent dispatch.

| Case | Specification scenarios |
| --- | --- |
| `delivery-start-main`, `delivery-existing-root` | V1-V2: actual local root setup and existing-work preservation. |
| `delivery-ticket-progress` | V3-V5: explicit worker bases, serialized integration and internal/external dependency decisions. |
| `delivery-assembly-and-publication` | V7-V8, V12: held/assembled scope, orchestrator publication order and uncertain/legacy recovery decisions. |
| `delivery-review-omission` | V6, V9: missing accepted behavior beyond changed lines and aggregate review scope. |
| `delivery-repair-and-handoff` | V10-V13: same-PR repairs, revision changes, draft default and applicable authorization. |
| `implement-explicit-read-only`, `implement-plan-approved-boundary` | V14: actual read-only routing and preservation of settled approvals. |
| `delivery-ordinary-worker` | V15: ordinary/lightweight worker ownership and completion handoff. |
| `delivery-ordinary-candidate` | V3-V4, V15: independent ticket PASS before an ordinary candidate may integrate. |

Record each case's setup, trace/answer evidence, actual result, independent rubric
verdict and limits. Distinguish an agent's observed decision from a scripted
transition or authored stage observation. A synthetic driver choosing the right
sequence does not prove that an agent chose it. Use the existing
[workflow rehearsal](../../.agents/skills/implement-spec-enhanced/references/handoff-rehearsal.md)
for protocol/transition checks when needed, labeling those as scripted coverage.
Neither route establishes live GitHub or multi-agent coordination. Do not create
real delivery PRs or mutate live issues solely for evaluation.

Evidence lives under Git-ignored `tmp/skill-evals/<run>/<case>/`: prompt, command,
before hashes, final response, JSONL trace, stderr, fixture files and guard score.
The runner scores completion, changed paths, required artifacts, unnecessary
questions, observed skill references and unrelated check commands. A referenced
skill path in a command is a discovery signal, not proof that its instructions
were applied correctly. Inspect the trace to confirm actual reading and use.

Observable guard success alone is not a skill PASS. Independently review each
case's rubric against the response, changed artifacts and trace; record
`satisfied`, `failed` or `unverified` with evidence and limits in the run directory.
Check the demo's actual behavior when the rubric requires a runnable artifact.
The grader leaves semantic review pending so it cannot invent that verdict.

Compare the same cases across revisions, retaining skill versions, model/effort,
command counts, token usage from the traces and materially different environments.
Add cases for demonstrated failures. Fix the skill or harness at the actual
failure boundary; do not loosen an expectation merely to make the score pass.
These fixtures cover bounded local workflows, not live tracker publication,
subagent coordination, native UI acceptance or the whole GPT-6 model family.

The approach follows [OpenAI's skill evaluation guidance](https://developers.openai.com/blog/eval-skills).
