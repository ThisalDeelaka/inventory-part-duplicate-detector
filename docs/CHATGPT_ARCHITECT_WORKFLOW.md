# Group-first implementation governance workflow

## Role and authority

This document defines the procedure for future GF implementation phases. It cannot override product requirements, architecture, domain contracts, or migration phase boundaries.

The authority order is:

```text
requirements > architecture > contracts > roadmap > assessment > workflow > historical docs
```

Concretely, this means:

1. `PROJECT_SSOT.md`.
2. `docs/GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md`.
3. `docs/GROUP_FIRST_DOMAIN_CONTRACTS.md`.
4. `docs/GROUP_FIRST_MIGRATION_ROADMAP.md`.
5. `docs/CURRENT_PROJECT_ASSESSMENT.md`.
6. `docs/CHATGPT_ARCHITECT_WORKFLOW.md`.
7. `MVP_LLM_DEMO_SSOT.md` and older historical documents.

Older pair-first MVP requirements remain useful for historical compatibility and regression context, but they do not override the approved group-first product architecture.

## Required workflow for every GF phase

1. Read `PROJECT_SSOT.md` completely.
2. Read `docs/GROUP_FIRST_IDENTITY_ARCHITECTURE_ADR.md` completely.
3. Read `docs/GROUP_FIRST_DOMAIN_CONTRACTS.md` completely.
4. Read `docs/GROUP_FIRST_MIGRATION_ROADMAP.md` completely.
5. Read `docs/CURRENT_PROJECT_ASSESSMENT.md` completely.
6. Inspect the current Git branch, HEAD, complete working-tree status, and staging area.
7. Verify that protected tag `deterministic-demo-v1` has not moved.
8. Implement only the named, bounded phase and its explicit allowlist.
9. Run focused tests for the changed contracts and behavior.
10. Run the full relevant regression suites.
11. Verify that there are zero unrelated changes and preserve all concurrent user work.
12. Inspect the staged diff and commit only after all required evidence passes and commit authorization exists.
13. Never push unless the user explicitly instructs it.
14. Update `docs/CURRENT_PROJECT_ASSESSMENT.md` after a verified phase so it accurately describes the new repository state without becoming a requirements authority.

## Mandatory stop conditions

If repository behavior, source, schema, or existing contracts conflict with `PROJECT_SSOT.md` or the approved architecture package:

```text
STOP
report the exact conflict
do not improvise a new product or architecture decision
```

If unexpected concurrent changes, staging, generated files, or unrelated modifications appear:

```text
STOP
report the contamination
do not stage, revert, delete, or overwrite unrelated work
```

If a requested phase depends on an incomplete prerequisite phase, stop and report the missing prerequisite. GF-1 is the first production implementation phase. Work must not jump directly to GF-3, GF-5, GF-8, or GF-9.

## Phase evidence record

Every completed phase report must identify:

- starting and final commit identities;
- exact files changed;
- migrations and compatibility behavior, if any;
- focused and full test commands and results;
- safety and invariant checks;
- provider request count;
- secret-access status;
- final Git status;
- whether assessment documentation was updated;
- the single approved next phase or an exact blocker.

Ordinary deterministic tests and shadow comparisons make zero external provider calls. Provider evaluation requires a separate, explicit task and never becomes an implicit GF phase step.
