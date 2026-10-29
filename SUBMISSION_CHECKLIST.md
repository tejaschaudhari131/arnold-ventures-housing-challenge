# Submission Checklist

Advisory only. The Official Rules govern completeness. Team: Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns, Carnegie Mellon University. Tool: Stateframe.

## Eligibility gates

- [x] Reproducible setup from documented commands (`bash scripts/setup.sh`, `bash scripts/run.sh`, `bash scripts/test.sh`, also the Makefile)
- [x] Automated tests covering core logic, with a documented run command (`bash scripts/test.sh`)
- [x] No committed secrets; `.env` is gitignored and `.env.example` has no credentials
- [ ] Dependabot alerts and CodeQL enabled in the GitHub security settings; workflows are committed (`.github/workflows/codeql.yml`, `.github/dependabot.yml`) and the dashboard steps are in docs/REPO_SETUP_GUIDE.md
- [x] Approved OSI-compliant license (Apache-2.0)

Secret scanning is a repository setting. The workflow files cannot flip that toggle by themselves. Turn it on from the GitHub settings page before the deadline and confirm zero unresolved alerts.

## Deliverables

- [x] Interactive tool (web app at `bash scripts/run.sh`, plus CSV/JSON/Markdown export)
- [ ] Slide deck (≤ 30 slides, PDF) — not in this commit; presentation guidance remains in docs/PRESENTATION_GUIDE.md
- [ ] Demo video (5 minutes, viewable without an account) — not in this commit
- [x] Model & Assumptions Overview (`docs/MODEL_AND_ASSUMPTIONS.md`)
- [x] Source code (this repository)
- [x] Software Bill of Materials (`docs/sbom.cdx.json`, summarized in `docs/DISCLOSURES.md`)
- [x] Policy scenario comparison (`docs/POLICY_SCENARIO_COMPARISON.md`)

## Scope and disclosures

- [x] Baseline and all five benchmark scenarios, plus the combined package, for all eleven states
- [x] Data provenance documented (`docs/DATA_PROVENANCE.md`)
- [x] AI tools, models, APIs, and dependencies disclosed (`docs/DISCLOSURES.md`)
