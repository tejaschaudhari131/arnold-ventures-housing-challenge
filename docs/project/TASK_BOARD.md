# Task board

Status values: ready, in progress, in review, blocked, done.
Nothing here is marked done on an agent's say-so. Work that landed in this branch is **in review** until a person checks it.

## Dependency graph

```text
Phase 1 baseline ──► defect fixes in this PR ──► in review
        │
        ├─► Phase 2 product and design (one entry, badges, one scroll)     ready
        ├─► Phase 3 data registry and loader failure matrix                 ready
        │         │
        │         └─► Phase 4 analytical contract                           blocked on Phase 3 notes
        │                   │  (#4 package resolver, #6 reconciliation, #9 economics)
        │                   └─► Phase 5 uncertainty (conditional intervals)  ready after Phase 4
        ├─► Phase 6 architecture (ScenarioSpec)                             ready
        ├─► Phase 7 journeys                                                 ready
        ├─► Phase 8 accessibility and performance budgets                    ready
        │         (small a11y fixes from the 768/390 audit are in this PR)
        ├─► Phase 9 release verification                                     ready
        ├─► Phase 10 security hardening                                      in review (this PR)
        ├─► Phase 11 ops and promotion                                       ready
        └─► Phase 12 submission artifacts (deck, video, page counts)         ready
```

| ID | Item | Status | Notes |
| --- | --- | --- | --- |
| P1 | Baseline record, defect register, model inventory | in review | `docs/project/` |
| D1 | Custom export matches the on-screen scenario | in review | POST `/api/export` |
| D2 | Lab range is a labeled reference, never a dash | in review | `Reference range (defaults)` |
| D3 | Lab URL keeps overrides and an empty selection | in review | `on=none` |
| D4 | True package resolver | ready | Phase 4. Joint ADU+MM is 8,543.9 vs sum 12,021 |
| D5 | Methods and provenance docs on Vercel | in review | `/docs/*.md` |
| D6 | Engine reconciliation | ready | Phase 4. Do not treat the engines as interchangeable |
| D7 | Sensitivity uses the current package | in review | scenario `combined` plus overrides and reforms |
| D8 | Acquisition loader and failure contract | in review | Fixed on main by PR #21; this PR adds HTTPS redirect checks |
| D9 | Capacity labels | in review | Basis label only. Economics stay for Phase 4. PR #22 renamed the package cap |
| D10 | Resolved SBOM and license check | in review | App scope vs dev scope |
| S1–S9 | Security review | in review | 400s, CSV guard, CSP, CodeQL JS, pinned actions |
| X1 | Brief and county CSV label the reference range | in review | Ranking text matches the live order |
| UX | Header wrap, skip link, tour contrast, caption, retry, fee note, tabs | in review | Not the Phase 2 restructure |
