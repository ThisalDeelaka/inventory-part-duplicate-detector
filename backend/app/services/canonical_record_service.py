"""Immutable, scan-local canonical inventory-record catalog."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from app.core.constants import MODEL_VERSION, SOURCE_ROW_INDEX_FIELD
from app.db.models import ScanRecordSnapshot
from app.engine.domain_dictionary import normalize_part_no_with_dictionary
from app.engine.normalizer import normalize_description


CANONICAL_SCAN_RECORD_CONTRACT_VERSION = "canonical-scan-record-v1"
_CANONICAL_FIELD_MAP = {
    "contract": "CONTRACT",
    "part_no": "PART_NO",
    "description": "DESCRIPTION",
    "uom": "UNIT_MEAS",
    "type_code": "TYPE_CODE",
    "prime_commodity": "PRIME_COMMODITY",
    "second_commodity": "SECOND_COMMODITY",
    "accounting_group": "ACCOUNTING_GROUP",
    "part_product_code": "PART_PRODUCT_CODE",
    "part_product_family": "PART_PRODUCT_FAMILY",
    "product_category_id": "PRODUCT_CATEGORY_ID",
    "hsn_sac_code": "HSN_SAC_CODE",
    "hazard_code": "HAZARD_CODE",
}


@dataclass(frozen=True)
class CanonicalScanRecord:
    record_id: int
    scan_id: int
    source_row_index: int
    record_ref_key: str
    source_record_fingerprint: str
    part_no: str
    description: str
    contract: str | None
    uom: str | None
    type_code: str | None
    prime_commodity: str | None
    second_commodity: str | None
    accounting_group: str | None
    part_product_code: str | None
    part_product_family: str | None
    product_category_id: str | None
    hsn_sac_code: str | None
    hazard_code: str | None
    normalized_part_no: str
    normalized_description: str
    normalization_version: str


@dataclass(frozen=True)
class CanonicalRecordCatalogResult:
    records: tuple[CanonicalScanRecord, ...]
    created_count: int
    idempotent: bool


def _value(item, name: str, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _text(value) -> str:
    if value is None or bool(pd.isna(value)):
        return ""
    return str(value)


def _optional_text(value) -> str | None:
    raw = _text(value)
    return raw if raw.strip() else None


def canonical_record_ref_key(scan_id: int, source_row_index: int) -> str:
    payload = (
        f"{CANONICAL_SCAN_RECORD_CONTRACT_VERSION}|scan:{scan_id}|"
        f"source-row:{source_row_index}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _canonical_values(item) -> dict:
    values = {
        attribute: _optional_text(_value(item, source_name))
        for attribute, source_name in _CANONICAL_FIELD_MAP.items()
    }
    values["part_no"] = values["part_no"] or ""
    values["description"] = values["description"] or ""
    return values


def _source_record_fingerprint(values: dict) -> str:
    payload = {
        "contract_version": CANONICAL_SCAN_RECORD_CONTRACT_VERSION,
        "canonical_values": values,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _planned_snapshot(scan_id: int, item) -> dict:
    source_row_index = _value(item, SOURCE_ROW_INDEX_FIELD)
    if source_row_index is None:
        raise ValueError("canonical record is missing its source row index")
    try:
        source_row_index = int(source_row_index)
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical record source row index must be an integer") from exc
    if source_row_index < 0:
        raise ValueError("canonical record source row index must be non-negative")
    values = _canonical_values(item)
    return {
        "scan_id": scan_id,
        "source_row_index": source_row_index,
        "record_ref_key": canonical_record_ref_key(scan_id, source_row_index),
        "source_record_fingerprint": _source_record_fingerprint(values),
        **values,
        "normalized_part_no": normalize_part_no_with_dictionary(values["part_no"]),
        "normalized_description": normalize_description(values["description"]),
        "normalization_version": MODEL_VERSION,
    }


def _assert_same_snapshot(row: ScanRecordSnapshot, planned: dict) -> None:
    for name, expected in planned.items():
        if getattr(row, name) != expected:
            raise ValueError(
                "existing immutable canonical scan record differs from source evidence"
            )


def _contract(row: ScanRecordSnapshot) -> CanonicalScanRecord:
    return CanonicalScanRecord(
        record_id=row.id,
        scan_id=row.scan_id,
        source_row_index=row.source_row_index,
        record_ref_key=row.record_ref_key,
        source_record_fingerprint=row.source_record_fingerprint,
        part_no=row.part_no,
        description=row.description,
        contract=row.contract,
        uom=row.uom,
        type_code=row.type_code,
        prime_commodity=row.prime_commodity,
        second_commodity=row.second_commodity,
        accounting_group=row.accounting_group,
        part_product_code=row.part_product_code,
        part_product_family=row.part_product_family,
        product_category_id=row.product_category_id,
        hsn_sac_code=row.hsn_sac_code,
        hazard_code=row.hazard_code,
        normalized_part_no=row.normalized_part_no,
        normalized_description=row.normalized_description,
        normalization_version=row.normalization_version,
    )


def create_or_get_scan_record_catalog(
    db, *, scan_id: int, records: Iterable
) -> CanonicalRecordCatalogResult:
    """Persist one immutable row per valid source row using one bounded batch."""
    if scan_id <= 0:
        raise ValueError("scan_id must be positive")
    planned_by_index = {}
    for item in records:
        planned = _planned_snapshot(scan_id, item)
        source_row_index = planned["source_row_index"]
        if source_row_index in planned_by_index:
            raise ValueError("canonical catalog contains a duplicate source row index")
        planned_by_index[source_row_index] = planned

    existing_rows = (
        db.query(ScanRecordSnapshot)
        .filter_by(scan_id=scan_id)
        .order_by(ScanRecordSnapshot.source_row_index, ScanRecordSnapshot.id)
        .all()
    )
    existing_by_index = {
        row.source_row_index: row
        for row in existing_rows
        if row.source_row_index is not None
    }
    if len(existing_by_index) != len(existing_rows):
        raise ValueError(
            "historical scan record snapshots cannot be reinterpreted as a GF-1 catalog"
        )
    unexpected = set(existing_by_index) - set(planned_by_index)
    if unexpected:
        raise ValueError("existing canonical catalog has unexpected source rows")

    created = []
    resolved = []
    try:
        for source_row_index in sorted(planned_by_index):
            planned = planned_by_index[source_row_index]
            row = existing_by_index.get(source_row_index)
            if row is None:
                row = ScanRecordSnapshot(**planned)
                db.add(row)
                created.append(row)
            else:
                _assert_same_snapshot(row, planned)
            resolved.append(row)
        db.flush()
    except Exception:
        db.rollback()
        raise

    return CanonicalRecordCatalogResult(
        records=tuple(_contract(row) for row in resolved),
        created_count=len(created),
        idempotent=not created,
    )


def load_scan_record_catalog(db, scan_id: int) -> tuple[CanonicalScanRecord, ...]:
    rows = (
        db.query(ScanRecordSnapshot)
        .filter_by(scan_id=scan_id)
        .order_by(ScanRecordSnapshot.source_row_index, ScanRecordSnapshot.id)
        .all()
    )
    return tuple(_contract(row) for row in rows)


def catalog_record_to_engine_input(record: CanonicalScanRecord) -> dict:
    """Adapt the catalog to the current pair/G1 input shape without re-normalizing."""
    return {
        SOURCE_ROW_INDEX_FIELD: record.source_row_index,
        "CONTRACT": record.contract,
        "PART_NO": record.part_no,
        "DESCRIPTION": record.description,
        "UNIT_MEAS": record.uom,
        "TYPE_CODE": record.type_code,
        "PRIME_COMMODITY": record.prime_commodity,
        "SECOND_COMMODITY": record.second_commodity,
        "ACCOUNTING_GROUP": record.accounting_group,
        "PART_PRODUCT_CODE": record.part_product_code,
        "PART_PRODUCT_FAMILY": record.part_product_family,
        "PRODUCT_CATEGORY_ID": record.product_category_id,
        "HSN_SAC_CODE": record.hsn_sac_code,
        "HAZARD_CODE": record.hazard_code,
    }
