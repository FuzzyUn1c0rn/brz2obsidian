# Testing the minimal migration slice

Use the native project virtual environment (tested Windows / Python 3.14.8):

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Ordinary tests use shareable synthetic format-5 records and actual temporary
ZIPs/filesystems. The checked-in `tests/fixtures/minimal.brz` contains only
synthetic identities and a plain Home note. The workflow is the primary seam;
public source/core/rendering/publication/CLI interfaces also have focused
checks. Filesystem cleanup denial is injected at the OS boundary, while
staging and its reported leftover are real. Tests cover native console/module
entry points and version-1 JSON round-trips.

The Markdown source-span gate instruments base markdown-it-py parser rules,
then maps each block's inline offsets back to exact authored code-point
positions. Repeated references, quote/list prefixes, escapes, inline/fenced
code and CRLF are covered. Live reference adaptation remains ticket 04.

Ticket 01 does not claim complete real-export acceptance. Private archives,
generated native review vaults and UI evidence remain under ignored `brz/`.
Later tickets own full-source preservation checks and full native review.
Native startup/bookmark serialization reproduces observed Obsidian 1.13.7
preferences; version-specific evidence is not a compatibility guarantee.
