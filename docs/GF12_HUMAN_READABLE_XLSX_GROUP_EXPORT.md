# GF-12C1-R5 human-readable XLSX System Group export

## Purpose and authority

GF-12C1-R5 adds a presentation-oriented Excel workbook for the exact
authority-selected System Group result at
`GET /api/scans/{scan_id}/identity-read/system-groups/export.xlsx`. It uses the
same persisted read authority, canonical snapshot, member projection, and
fail-closed behavior as System Group CSV.

> The XLSX report is a human-readable representation of System Group Export. It is not Reviewed Identity Export and does not itself confirm duplicate identity.

System Group CSV/XLSX remains system-generated analytical output that may
contain unreviewed groups. Reviewed Identity Export remains the separate
human-confirmed operational output. No export calls an LLM provider, changes
membership, selects a canonical master, merges inventory, writes back to an
ERP, or mutates review state.

## CSV and XLSX

The existing CSV route and fields are unchanged for machine-readable use. XLSX
is a bounded human-facing view of the same shared member-shaped projection. Its
`Group Data` sheet carries the same canonical group IDs and stable member
references. The backend adds `openpyxl==3.1.5`, a focused XLSX reader/writer.
Workbooks are generated in memory and are not persisted by the server.

## Workbook sheets

`Summary` states the System Group Report type, analytical authority, absence of
implied human confirmation, and the persisted scan name/status, canonical input
count, group/status/outcome counts, projection contract, and source run. It does
not claim accuracy.

`Duplicate Groups` starts with `Duplicate Group`, `Canonical Group ID`, `Status`,
`Reason`, `Member Count`, and `Review State`. Member columns are `Part No`,
`Description`, `Site`, `Inventory UOM`, `Part Type`, `Commodity Group 01`,
`Commodity Group 02`, `Safety Code`, `Accounting Group`, `Product Code`,
`Product Family`, `Product Category`, `HSN/SAC Code`, and
`Source Row / Stable Record Reference`. For each N-member group, only the six
group-level cells merge vertically over exactly N rows. Member cells never
merge and there are no separator rows.

`Group Data` repeats group values for one flat row per authoritative member. It
has no merged cells, freezes the header, enables filtering, and uses an Excel
table for sorting. Membership is semantically equivalent to System Group CSV.

## Labels, reasons, and review state

Friendly `DG-000001` labels follow the canonical snapshot group order. They are
deterministic presentation labels only; the opaque versioned group key remains
the canonical identity.

Reasons are deterministic offline templates keyed by authoritative status.
Likely-group wording says strong evidence supports a *potential* group and does
not imply human confirmation. Review-group wording says supporting evidence is
present and human review is required. Cautious conflict/deferred templates are
defined, but those outcomes are not inserted into group sheets because System
Group Export does not export them as groups.

Review State is loaded only from the exact current append-only review chain for
the selected projection. Missing state displays `Not reviewed`; system status
never infers review. Review state remains informational and does not transform
this report into Reviewed Identity Export.

## Spreadsheet safety and failure gates

Every value passes through one spreadsheet-safe writer. Strings—including
business values beginning with `=`, `+`, `-`, or `@`—are explicitly stored as
literal string cells, never formulas. The workbook has no macros, formulas,
credentials, truth labels, hidden business data, or writeback actions.

The route returns 404 for a missing scan, 409 for not-ready/incomplete authority,
and 422 for inconsistent/corrupt authority via existing identity-read gates. It
does not fall back to another projection or combine scans.

## Verification evidence

Focused tests cover opening, sheet contracts, summary counts, CSV/XLSX parity,
exact 2-member and 3-member merged ranges, unmerged member columns, labels,
reasons, canonical IDs, status/member counts, review state, authority closure,
literal formula-like values, and absence of formulas, truth, credentials, and
writeback. Three generated synthetic workbooks have identical sheet order, cell
values, row order, merged ranges, labels, statuses, reasons, and relationships.

A disposable in-memory export of persisted completed scan 25 (5,327 canonical
records) produced three sheets, 288 groups, 711 member rows, 1,728 merged ranges,
labels `DG-000001` through `DG-000288`, 250,664 bytes, and 3.685080 seconds
generation time. No real scan was rerun and no real workbook was saved.

## Limitations

The group sheets contain accepted analytical System Groups only. Conflicts,
deferred work, and unassigned records appear as Summary counts and remain in
their dedicated product views/exports. This is not an accuracy study,
human-quality validation, deployment certification, canonical-master decision,
or ERP action plan. GF-12A2 remains `HUMAN_REVIEW_DATASET_REQUIRED`. GF-11's
waiver remains ACTIVE, `GF11-PERF-100K-COLD-FULL` remains OPEN, the 300-second
target remains unmet, and deployment/integration remains deferred post-demo.

## R6 Excel compatibility and current-product authority

R6 package inspection proved that the original Group Data worksheet and its
Excel Table both declared an AutoFilter over the same range. Microsoft Excel
repaired that overlap by discarding the table/filter. Group Data now has no
worksheet-level AutoFilter; its `SystemGroupData` table owns the single filter.
Package-level tests cover the exact XML relationship, range, columns, filter,
merged-range validity, and round-trip table retention.

The ordinary browser New Scan also now sends the typed public
`current_product` selection, so a fresh interactive scan persists group-first
primary authority and exports G2-v2 rather than inheriting the legacy config
default. Explicit legacy compatibility and historical G2-v1 reads remain.
Fresh scan 27 proves exact API/CSV/XLSX parity for 207 G2-v2 groups and 440
member rows. Its read-only quality canary is Q2, so the workbook is evidence for
authority/export correctness but is not yet the frozen real demo candidate.
See `docs/GF12_INTERACTIVE_G2V2_XLSX_AND_REAL_OUTPUT_AUDIT.md`.
