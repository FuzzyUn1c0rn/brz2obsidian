# Disposable UI presentation prototype

Question: which of three structurally different presentations best communicates the agreed conversion workflow and outcomes? No existing UI route exists in this CLI-only project, so this self-contained throwaway HTML file is the host. Production stack remains undecided.

Run from the checkout root:

```powershell
.\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory tmp/ui-wayfinding/prototype
```

Open http://127.0.0.1:8765/prototype.html?variant=A . The file can also be opened directly in a browser without a server. No external scripts, fonts, styles or services are used.

The captured throwaway branch stores the same artifact under `docs/history/ui-wayfinding/prototype/`. From that branch, serve that directory instead of the local `tmp/` directory. No checkout switch is needed to try the current local preview.

- A: guided steps; one task at a time with a progress rail.
- B: workbench; persistent inputs beside results.
- C: compact task sheet; stacked sections with a bottom action area.

Use the floating prototype bar to change variant and load example states. Left/right arrows switch layouts except while a form control or editable content has focus. The URL records variant, mode and example state, so references can be reloaded. Form selections live only in memory.

Each variant is authored independently by its own sub-agent in `variants/a.html`, `variants/b.html` and `variants/c.html`. `prototype.html` is only the shared comparison host. The earlier root-authored draft (`root-draft.html`) is superseded and is not part of the comparison or proposed reference.

All paths, counts, file/folder pickers and converter results are synthetic. Completion buttons simulate their action; Copy details and Save diagnostic report operate only on synthetic report text. There is no converter connection, actual filesystem picker or private source access. Simulated elapsed time is illustrative, not a performance measurement. Colors, product name and sample wording are proposals awaiting user feedback. The floating control bar is prototype-only and belongs to no production deliverable.

Do not promote this code directly into production. Capture variants and the user's eventual verdict on the throwaway prototype branch and in the GitHub presentation ticket. Keep that ticket open until presentation approval and handoff requirements are recorded.
