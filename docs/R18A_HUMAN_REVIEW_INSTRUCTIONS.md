# R18A Blinded Human Identity-Review Instructions

## Your task

For every row, answer this question using only the source fields shown:

> Are these records the same underlying physical/business inventory item,
> based on the source information available?

Work independently. Do not consult another reviewer's answers, detector output,
group status, expected controls, or an AI/LLM. Do not change pair IDs or source
fields. Enter only the label, confidence, reason code, and optional note.

## Labels

- `SAME_IDENTITY`: the available evidence supports the same underlying item.
- `DIFFERENT_IDENTITY`: the available evidence supports different underlying
  items.
- `INSUFFICIENT_INFORMATION`: the visible source evidence cannot responsibly
  establish same or different. Use this instead of guessing.

Physical identity is not the same as ERP mapping consistency. Site, contract,
accounting group, product family, UOM, or other mapping differences do not by
themselves prove different identity. Likewise, missing data is not matching
evidence, and copied or identical wording does not by itself prove identity.

Identity-defining distinctions may include model, version, size, capacity,
voltage, amperage, pressure, material, side, functional/location role, pack
quantity, technical specification, or a unique identifier when those facts are
relevant to the item.

## Confidence

- `HIGH`: the visible source evidence clearly supports the selected label.
- `MEDIUM`: the balance of visible evidence supports it, with a meaningful
  limitation or ambiguity.
- `LOW`: the selection is weakly supported. Prefer
  `INSUFFICIENT_INFORMATION` when the evidence cannot responsibly decide.

Choose one bounded reason code that best explains the decision. The reviewer
note is optional and should be concise, factual, and based only on visible
source evidence. Do not place credentials, personal information, detector
information, or external research in a note.

## Independence and return

Reviewer A and Reviewer B must complete their separate workbooks without seeing
one another's entries. Do not rename columns, add rows, delete rows, alter
source cells, or copy labels between files. Return the completed workbook to the
authorized project coordinator through the approved private channel; reviewer
workbooks remain outside Git.
