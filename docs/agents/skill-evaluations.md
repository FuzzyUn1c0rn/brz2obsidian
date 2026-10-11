# Skill behavior evaluations

Use the small [prompt corpus](../../.agents/evals/cases.json) when changing skill
activation, authorization, completion or verification rules. It includes positive
activation and adjacent negative requests, explicit read-only use, prior approval
reuse and prototype completion. Each run uses fresh synthetic files and copies
the current repository skills and its own Git root, so it exercises the actual instructions rather
than checking their wording.

Run with the project interpreter:

```powershell
.venv\Scripts\python.exe tools/skill_evals.py list
.venv\Scripts\python.exe tools/skill_evals.py run --case spec-approved-boundary
.venv\Scripts\python.exe tools/skill_evals.py run
.venv\Scripts\python.exe tools/skill_evals.py score 'C:\checkout\tmp\skill-evals\run-id\spec-approved-boundary'
```

`run` starts separate ephemeral Codex CLI runs, inheriting the user's configured
model and effort. Use `--codex` if the executable is not on PATH. Cases run
sequentially with a 180-second per-case timeout (`--timeout` overrides it).
Read-only cases use the read-only sandbox; requested artifact cases use
workspace-write in their disposable fixture. Fixture instructions prohibit
delegation and external mutations. No model settings or repository guidance are
changed by evaluation execution.

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
