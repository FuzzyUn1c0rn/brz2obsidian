---
name: research
description: Produce a cited research report when the user requests a saved investigation or delegates substantial research. Ordinary factual questions use direct answers.
---

Investigate against primary sources: official docs, source code, specifications
and first-party APIs. Follow claims back to the source that owns them.

Preserve the requested output and side effects. For a read-only request, return
cited findings in the conversation. Save a report only when requested or already
authorized; use the requested destination and repository conventions. Temporary
research notes belong under `.scratch/<effort>/` or `tmp/<effort>/`.

Handle a bounded investigation directly. Delegate substantial independent reading
when it makes useful progress while other work continues and delegation is
available and authorized. Assign one research owner; a delegated researcher
performs the investigation rather than spawning another researcher by default.

Report the question, supported findings with citations, uncertainties and any
material limits. Identify the saved report when one was requested. Prefer the
OpenAI Docs skill for OpenAI product or API documentation questions.
