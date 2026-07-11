## Summary

<!-- Briefly describe what changed and why. -->

## Change Type

- [ ] fix
- [ ] feat
- [ ] refactor
- [ ] docs
- [ ] chore
- [ ] test
- [ ] ci

## Scope

- [ ] Backend (`src/`, `data_provider/`, `api/`, `bot/`)
- [ ] Web (`apps/dsa-web/`)
- [ ] Desktop (`apps/dsa-desktop/`)
- [ ] Workflows/scripts/Docker
- [ ] Docs/governance
- [ ] Other:

## Contract And Compatibility

<!-- Describe API/schema/config/report/notification/user-visible compatibility impact. State "No compatibility impact" if none. -->

## Validation

<!-- List commands run and results. If relying on CI, link or name the check. -->

- [ ] `./scripts/ci_gate.sh`
- [ ] `python -m pytest -m "not network"`
- [ ] `python -m py_compile <changed_python_files>`
- [ ] `cd apps/dsa-web && npm ci && npm run lint && npm run build`
- [ ] Desktop build validation
- [ ] Docs only, tests not run

## Screenshots / Visual Evidence

<!-- Required for report format, report rendering, or Web UI changes. Attach affected pages/reports or explain why visual evidence is not possible. -->

## Risk And Rollback

- Risk:
- Rollback plan:

## Notes For Reviewers

<!-- Include known limitations, follow-ups, or places that deserve careful review. -->
