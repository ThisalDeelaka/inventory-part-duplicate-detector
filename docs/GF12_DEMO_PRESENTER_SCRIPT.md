# GF-12 product demo presenter script

Target duration: **5–10 minutes**. Demo data is synthetic and is not human
quality evidence.

## 1. Problem — 45 seconds

“Inventory masters accumulate spelling variants, abbreviations, site copies,
and ambiguous technical descriptions. This product finds possible duplicate
physical-item identities while keeping uncertainty and human control visible.”

State upfront: no automatic merge, delete, source rewrite, or IFS writeback.

## 2. Load inventory — 45 seconds

Open **New Scan**, choose `data/llm_assisted_mvp_demo.csv`, and say that all 17
rows are synthetic. Validate, show the bounded column-mapping step, and retain
Same-site mode, threshold 75, and Sensitive Data Mode.

## 3. Run the scan — 30 seconds

Choose **Run scan**. Explain that this supported local flow is synchronous and
provider-free. The browser opens the result only after the scan completes.

## 4. Show identity groups — 90 seconds

Point to the authoritative G2-v2 summary: 4 identity groups, 1 likely and 3
requiring review. Open the three-member 10 kW motor group. Emphasize that one
2..N identity set is the product unit—not three pair decisions. Show all members
and the bounded deterministic validation evidence.

## 5. Show caution — 60 seconds

Open **Conflicts & Deferred**. Show that 3 conflicts remain distinct from
accepted groups, deferred is visibly zero, and 8 records are not safely
assigned. Say: “Not safely assigned does not mean confirmed unique.” Cross-site
identity is not available in this fixture and is not manufactured for the demo.

## 6. Human review — 90 seconds

Return to the three-member motor group, enter `GF12C1_DEMO_PRESENTER`, choose
**Confirm all as one item**, and save. Show current state and append-only history.
Clarify that this synthetic presenter action demonstrates workflow; it is not an
expert quality label or production-accuracy evidence.

## 7. Exports — 60 seconds

Download **System Groups** and explain that it is the authority-selected,
member-shaped system hypothesis export. Download **Reviewed Identities** and
explain that only current confirmed human-reviewed sets appear. Mention the
separate conflict export. No export performs provider execution or writeback.

## 8. Close — 45 seconds

“The working product demonstrates deterministic group-first discovery, cautious
outcomes, human review, and operational exports with provider calls zero.”

Limitations to state exactly:

- showable local working product: verified by this milestone;
- production deployment readiness: no claim;
- representative human-reviewed quality: pending, dataset required;
- GF-11 100k cold-full 300-second target: not met, debt open under waiver;
- 1M readiness: no claim;
- durable resume, production cancellation, and production timeout: not
  implemented; and
- tenancy, IAM/SSO/RBAC, production storage/network/retention, cloud deployment,
  reference hardware, and external integrations: post-demo work.
