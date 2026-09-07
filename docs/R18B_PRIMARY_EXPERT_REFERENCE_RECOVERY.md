# R18B-R1 Primary Expert Reference Recovery

## Decision

`R18B_R1_PRIMARY_EXPERT_REFERENCE_RECOVERED`

The Senior Functional Consultant's literal judgments were recovered without
editing or re-saving the submitted workbook. Recovery joins logical columns by
exact header name and pair ID; it does not trust shifted physical positions or
formula results.

## Baseline and immutable template

- Starting HEAD: `46b7e16411a84891958aa1c6fa86f476c56e3bd8` on
  `llm-assisted-mvp`.
- Protected tag `deterministic-demo-v1` remained at
  `d510cf3c18b3a8448d0f79be3e59c398efb32eae`.
- The protected untracked `List_20260709_093045.xlsx` was not inspected,
  modified, staged, deleted, or hashed.
- Provider calls were 0; no secret or environment file was accessed.

The original blank Reviewer A artifact had been overwritten in the ignored
artifact directory. Its immutable bytes were independently reconstructed in a
temporary directory using the committed deterministic R18 generator, the
read-only completed Scan-31 database state (5,327 records, discovery run 8,
evidence run 7), and the authorized source CSV. The CSV was first verified as
3,265,800 bytes with SHA-256
`8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b`.

The reconstructed template is byte-identical to the original manifest:

- size: 40,682 bytes;
- SHA-256:
  `682b4e4d5d83017a28f7c021124b2dd394431cf91c072a9934fd73d7025bb052`;
- 316 rows, original 23-field schema, zero labels, zero formulas;
- deterministic sample, mapping, and companion artifact hashes all matched the
  original R18 manifest.

This is an exact byte-level restoration of the immutable comparison baseline,
not a new sample or a detector rerun.

## Submitted workbook and logical mapping

The unchanged submitted Reviewer A workbook is 16,136,153 bytes with SHA-256
`6e27ce3a46f17834e8387879793cd18461d87295a1d28caa7b0aba0e3bbac7eb`.
The single header row is row 2. Every expected logical header occurs exactly
once. Logical columns 1-19 remain the pair ID and 18 source fields; two inserted
formula columns occupy physical columns 20-21; the human fields are recovered
from physical columns 22-25:

| Logical field | Physical column |
|---|---:|
| `review_pair_id` | 1 |
| `identity_label` | 22 |
| `confidence` | 23 |
| `reason_code` | 24 |
| `reviewer_comment` | 25 |

All source field names map individually by exact header, not by their displayed
position.

## Integrity gates

| Gate | Result |
|---|---|
| Non-empty pair IDs | 316 |
| Unique pair IDs | 316 |
| Missing / foreign / duplicate IDs | 0 / 0 / 0 |
| Reviewer-visible source cells compared | 5,688 (`316 x 18`) |
| Source cells different | 0 |
| Formula in any expected source field | 0 |
| Formula in any human-input field | 0 |
| Valid labels / confidence / reason codes | 316 / 316 / 316 |
| Missing label or confidence | 0 |

The extra formulas compare displayed source columns 9 versus 18 and 10 versus
19. Each extra column contains 317 formula cells including its header. They are
outside the 23 authoritative logical fields, contribute no recovered value,
and are not used as evidence. The inflated 1,048,576-row used range contains no
additional authoritative pair after the 316 expected rows and is ignored under
the approved recovery rule.

## Frozen recovered reference

The ignored derived artifact
`r18b_recovered_primary_expert_reference.csv` contains only the pair ID,
literal Senior label/confidence/reason/comment, reference type, source hashes,
and recovery version. It has 316 rows, size 94,232 bytes, and SHA-256
`24a8abd5505a535fd1d4acbec493cda8ac5ae1a6e017ef3d1b84e6110590ae02`.

`reference_type = SINGLE_SENIOR_DOMAIN_EXPERT_RECOVERED`

The recovered label distribution is 77 `SAME_IDENTITY`, 185
`DIFFERENT_IDENTITY`, and 54 `INSUFFICIENT_INFORMATION`; confidence is 139
HIGH, 145 MEDIUM, and 32 LOW.

## Claim limit

This is a blinded single-senior-domain-expert diagnostic reference with a
secondary junior-review challenge signal. It is not dual-reviewed adjudicated
ground truth, a gold standard, or a validated production-accuracy benchmark.
The original human submission remains unchanged. Recovery certifies what was
displayed and literally entered; it does not assert that any individual human
judgment is objectively correct.
