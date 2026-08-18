import dataclasses
from collections import defaultdict

import pandas as pd
import pytest
from sqlalchemy import event, inspect, update

from app.core.config import Settings
from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.db.migrations import ensure_identity_discovery_tables
from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    IdentityDiscoveryRun,
    IdentityGroupProjectionRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember as IdentityNeighborhoodMemberRow,
    IdentityNeighborhoodSnapshot,
    ScanRecordSnapshot,
)
from app.discovery.contracts import (
    IdentityNeighborhood,
    IdentityNeighborhoodMember,
    NeighborhoodMemberRole,
)
from app.repositories.discovery_repository import DiscoveryRepository
from app.services.canonical_record_service import create_or_get_scan_record_catalog
from app.services.identity_discovery_service import (
    persist_discovery_proposals,
    start_discovery_run,
)
from app.services.identity_neighborhood_service import (
    MEMBER_CAP_WARNING,
    _plan_neighborhoods,
    build_and_persist_identity_neighborhoods,
    load_identity_neighborhoods,
)
from app.services.scan_runner import ScanRunner


def configuration(**values):
    defaults = dict(
        llm_provider="none",
        llm_demo_enabled=False,
        hybrid_retrieval_enabled=False,
        identity_neighborhood_max_members=20,
    )
    defaults.update(values)
    return Settings(**defaults)


def frame(size):
    result = pd.DataFrame([
        {
            "PART_NO": f"P-{index}",
            "DESCRIPTION": f"Inventory item {index}",
            "CONTRACT": "S1",
            "UNIT_MEAS": "EA",
        }
        for index in range(size)
    ])
    result[SOURCE_ROW_INDEX_FIELD] = range(size)
    return result


def scan_and_catalog(db, size):
    rows = frame(size)
    scan = DuplicateScan(
        scan_name="GF-3 fixture",
        selected_fields='["CONTRACT"]',
        threshold=99,
        model_version="test",
        scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(scan)
    db.commit()
    catalog = create_or_get_scan_record_catalog(
        db, scan_id=scan.id, records=rows.to_dict(orient="records")
    )
    db.commit()
    return scan, rows, catalog


def pair(records, left, right):
    return {
        "record_a": records[left],
        "record_b": records[right],
        "matched_fields": [],
        "mismatched_fields": [],
        "warnings": [],
    }


def prepare(db, size, edges, *, cap=20, commit=True):
    scan, rows, catalog = scan_and_catalog(db, size)
    cfg = configuration(identity_neighborhood_max_members=cap)
    run = start_discovery_run(
        db,
        scan_id=scan.id,
        catalog_records=catalog.records,
        configuration=cfg,
        scan_mode="SAME_SITE_DUPLICATE",
        selected_fields=["CONTRACT"],
    )
    db.commit()
    records = rows.to_dict(orient="records")
    persisted = persist_discovery_proposals(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        catalog_records=catalog.records,
        standard_pairs=[pair(records, left, right) for left, right in edges],
        hybrid_result=None,
        engine_records=records,
    )
    assert persisted.status.value == "RUNNING"
    result = build_and_persist_identity_neighborhoods(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        max_members=cap,
    )
    if commit:
        db.commit()
    return scan, catalog, run, result


def memberships(result):
    output = defaultdict(list)
    anchors = {
        item.neighborhood_id: item.anchor_record_id for item in result.neighborhoods
    }
    for member in result.members:
        output[anchors[member.neighborhood_id]].append(member.record_id)
    return {anchor: tuple(values) for anchor, values in output.items()}


def test_contracts_are_immutable_and_contain_no_decision_semantics():
    forbidden = {
        "business_status", "duplicate_status", "group_status", "identity_confidence",
        "human_review_decision", "llm_result", "edge_class", "cannot_link",
    }
    for contract in (IdentityNeighborhood, IdentityNeighborhoodMember):
        assert dataclasses.is_dataclass(contract)
        assert contract.__dataclass_params__.frozen is True
        assert not forbidden & {field.name for field in dataclasses.fields(contract)}


def test_direct_adjacency_forms_overlapping_non_transitive_neighborhoods(db):
    _scan, catalog, _run, result = prepare(db, 3, [(0, 1), (1, 2)])
    ids = [record.record_id for record in catalog.records]
    actual = memberships(result)
    assert actual[ids[0]] == (ids[0], ids[1])
    assert actual[ids[1]] == (ids[1], ids[0], ids[2])
    assert actual[ids[2]] == (ids[2], ids[1])
    assert ids[2] not in actual[ids[0]]
    assert ids[0] not in actual[ids[2]]
    assert sum(ids[1] in members for members in actual.values()) == 3


def test_overlap_is_allowed_for_one_hub_and_three_leaves(db):
    _scan, catalog, _run, result = prepare(db, 4, [(0, 1), (1, 2), (1, 3)])
    ids = [record.record_id for record in catalog.records]
    actual = memberships(result)
    assert len(actual) == 4
    assert all(ids[1] in actual[anchor] for anchor in ids)
    assert result.records_in_at_least_one_neighborhood == 4


def test_record_without_proposal_remains_cataloged_without_singleton_neighborhood(db):
    _scan, catalog, _run, result = prepare(db, 3, [(0, 1)])
    ids = [record.record_id for record in catalog.records]
    anchors = {item.anchor_record_id for item in result.neighborhoods}
    assert anchors == {ids[0], ids[1]}
    assert ids[2] not in anchors
    assert result.records_without_proposals == 1
    assert db.query(ScanRecordSnapshot).count() == 3


def test_cap_is_explicit_deterministic_and_preserves_omitted_proposals(db):
    _scan, catalog, run_contract, result = prepare(
        db, 5, [(0, 1), (0, 2), (0, 3), (0, 4)], cap=3
    )
    anchor = catalog.records[0].record_id
    neighborhood = next(item for item in result.neighborhoods if item.anchor_record_id == anchor)
    assert neighborhood.candidate_neighbor_count == 4
    assert neighborhood.included_neighbor_count == 2
    assert neighborhood.member_count == 3
    assert neighborhood.is_truncated is True
    assert MEMBER_CAP_WARNING in neighborhood.warning_codes
    assert db.query(IdentityNeighborProposal).filter_by(
        discovery_run_id=run_contract.discovery_run_id
    ).count() == 4

    run = db.get(IdentityDiscoveryRun, run_contract.discovery_run_id)
    records = tuple(catalog.records)
    proposals = DiscoveryRepository(db).proposals_for_run(run.id)
    first, first_config = _plan_neighborhoods(run, records, proposals, 3)
    second, second_config = _plan_neighborhoods(run, records, tuple(reversed(proposals)), 3)
    assert first_config == second_config
    assert [item.fingerprint for item in first] == [item.fingerprint for item in second]
    assert [
        tuple(proposal.id for _record_id, proposal in item.selected) for item in first
    ] == [
        tuple(proposal.id for _record_id, proposal in item.selected) for item in second
    ]


def test_every_direct_member_links_to_its_anchor_proposal(db):
    _scan, _catalog, run, result = prepare(db, 4, [(0, 1), (1, 2), (1, 3)])
    proposals = {
        item.id: item for item in DiscoveryRepository(db).proposals_for_run(run.discovery_run_id)
    }
    anchors = {item.neighborhood_id: item.anchor_record_id for item in result.neighborhoods}
    for member in result.members:
        if member.role == NeighborhoodMemberRole.ANCHOR:
            assert member.source_proposal_id is None
            continue
        proposal = proposals[member.source_proposal_id]
        assert proposal.discovery_run_id == run.discovery_run_id
        assert {proposal.record_id_1, proposal.record_id_2} == {
            anchors[member.neighborhood_id], member.record_id,
        }


def test_forged_non_direct_member_fails_validation(db):
    _scan, _catalog, run, result = prepare(db, 4, [(0, 1), (2, 3)])
    neighborhood = result.neighborhoods[0]
    direct = next(
        item for item in result.members
        if item.neighborhood_id == neighborhood.neighborhood_id
        and item.role == NeighborhoodMemberRole.DIRECT_NEIGHBOR
    )
    unrelated = next(
        proposal for proposal in DiscoveryRepository(db).proposals_for_run(run.discovery_run_id)
        if neighborhood.anchor_record_id not in {proposal.record_id_1, proposal.record_id_2}
    )
    db.execute(
        update(IdentityNeighborhoodMemberRow)
        .where(IdentityNeighborhoodMemberRow.id == direct.member_id)
        .values(source_proposal_id=unrelated.id)
    )
    db.commit()
    with pytest.raises(ValueError, match="lacks its anchor proposal"):
        load_identity_neighborhoods(db, run.discovery_run_id)


def test_builder_is_idempotent_and_snapshots_are_immutable(db):
    scan, _catalog, run, first = prepare(db, 3, [(0, 1), (1, 2)])
    second = build_and_persist_identity_neighborhoods(
        db, discovery_run_id=run.discovery_run_id, scan_id=scan.id, max_members=20
    )
    assert second.idempotent is True
    assert first.neighborhood_count == second.neighborhood_count
    assert first.member_count == second.member_count
    assert [item.neighborhood_fingerprint for item in first.neighborhoods] == [
        item.neighborhood_fingerprint for item in second.neighborhoods
    ]
    with pytest.raises(ValueError, match="cap does not match"):
        build_and_persist_identity_neighborhoods(
            db, discovery_run_id=run.discovery_run_id, scan_id=scan.id, max_members=3
        )
    row = db.query(IdentityNeighborhoodSnapshot).first()
    row.degraded = not row.degraded
    with pytest.raises(ValueError, match="immutable"):
        db.commit()


def test_builder_never_queries_or_calls_pair_decision_layers(db, monkeypatch):
    scan, rows, catalog = scan_and_catalog(db, 3)
    cfg = configuration()
    run = start_discovery_run(
        db, scan_id=scan.id, catalog_records=catalog.records, configuration=cfg,
        scan_mode="SAME_SITE_DUPLICATE", selected_fields=["CONTRACT"],
    )
    db.commit()
    records = rows.to_dict(orient="records")
    persist_discovery_proposals(
        db, discovery_run_id=run.discovery_run_id, scan_id=scan.id,
        catalog_records=catalog.records,
        standard_pairs=[pair(records, 0, 1), pair(records, 1, 2)],
        hybrid_result=None, engine_records=records,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("GF-3 consulted a pair decision layer")

    monkeypatch.setattr("app.engine.scoring.score_candidate", forbidden)
    monkeypatch.setattr("app.engine.identity_edge.classify_identity_edge", forbidden)
    statements = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    event.listen(db.bind, "before_cursor_execute", record_select)
    try:
        build_and_persist_identity_neighborhoods(
            db, discovery_run_id=run.discovery_run_id, scan_id=scan.id, max_members=20
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", record_select)
    forbidden_tables = (
        "duplicate_candidate", "duplicate_feedback", "llm_advisory_snapshot",
        "rule_exclusion_audit", "identity_group_projection_run",
    )
    assert not any(table in statement for table in forbidden_tables for statement in statements)
    assert len(statements) <= 12


def test_neighborhood_failure_rolls_back_discovery_and_blocks_g2(db, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("forced GF-3 member failure")

    monkeypatch.setattr(DiscoveryRepository, "add_neighborhood_members", fail)
    data = frame(2).drop(columns=[SOURCE_ROW_INDEX_FIELD])
    with pytest.raises(RuntimeError, match="forced GF-3 member failure"):
        ScanRunner(db, configuration()).run(data, "failed GF-3", ["CONTRACT"], 60)

    scan = db.query(DuplicateScan).one()
    run = db.query(IdentityDiscoveryRun).one()
    assert scan.status == "FAILED"
    assert run.status == "FAILED"
    assert db.query(ScanRecordSnapshot).count() == 2
    assert db.query(IdentityNeighborProposal).count() == 0
    assert db.query(IdentityNeighborhoodSnapshot).count() == 0
    assert db.query(IdentityNeighborhoodMemberRow).count() == 0
    assert db.query(DuplicateCandidate).count() == 0
    assert db.query(IdentityGroupProjectionRun).count() == 0


def test_historical_gf2_completed_run_without_neighborhoods_is_readable_not_backfilled(db):
    scan, _rows, _catalog = scan_and_catalog(db, 1)
    historical = IdentityDiscoveryRun(
        scan_id=scan.id,
        discovery_fingerprint="f" * 64,
        algorithm_version="identity-discovery-v1",
        configuration_version="identity-discovery-config-v1",
        normalization_version="historical",
        configuration_json="{}",
        status="COMPLETED",
        records_total=1,
        records_without_proposal=1,
        provider_request_count=0,
    )
    db.add(historical)
    db.commit()
    loaded = load_identity_neighborhoods(db, historical.id)
    assert loaded.neighborhood_count == 0
    assert db.query(IdentityNeighborhoodSnapshot).count() == 0
    with pytest.raises(ValueError, match="not backfilled"):
        build_and_persist_identity_neighborhoods(
            db, discovery_run_id=historical.id, scan_id=scan.id, max_members=20
        )


def test_additive_migration_creates_neighborhood_schema_and_run_metrics(db):
    engine = db.get_bind()
    IdentityNeighborhoodMemberRow.__table__.drop(engine)
    IdentityNeighborhoodSnapshot.__table__.drop(engine)
    ensure_identity_discovery_tables(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"identity_neighborhood_snapshot", "identity_neighborhood_member"} <= tables
    columns = {
        column["name"] for column in inspect(engine).get_columns("identity_discovery_run")
    }
    assert {
        "neighborhood_count", "records_in_at_least_one_neighborhood",
        "records_with_proposals_but_no_neighborhood", "truncated_neighborhood_count",
        "max_candidate_neighbor_count", "max_included_member_count",
    } <= columns


def test_normal_scan_completes_neighborhoods_before_unchanged_g2_and_calls_no_provider(
    db, monkeypatch
):
    from app.services import scan_runner as scan_runner_module

    def provider_called(*_args, **_kwargs):
        raise AssertionError("GF-3 invoked an external provider")

    calls = []
    original_builder = scan_runner_module.build_and_persist_identity_neighborhoods
    original_projection = scan_runner_module.project_and_persist_identity_groups

    def builder(*args, **kwargs):
        calls.append("neighborhoods")
        result = original_builder(*args, **kwargs)
        assert db.get(IdentityDiscoveryRun, kwargs["discovery_run_id"]).status == "COMPLETED"
        return result

    def projection(*args, **kwargs):
        assert calls == ["neighborhoods"]
        calls.append("g2")
        return original_projection(*args, **kwargs)

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr("app.llm.group_provider_factory.create_group_advisory_provider", provider_called)
    monkeypatch.setattr(scan_runner_module, "build_and_persist_identity_neighborhoods", builder)
    monkeypatch.setattr(scan_runner_module, "project_and_persist_identity_groups", projection)
    data = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "MCB30A", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
        {"PART_NO": "B", "DESCRIPTION": "MCB 30 A", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
    ])
    scan, _ = ScanRunner(db, configuration()).run(
        data, "normal GF-3", ["CONTRACT", "UNIT_MEAS"], 60
    )
    run = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    assert scan.status == "COMPLETED"
    assert run.status == "COMPLETED"
    assert run.neighborhood_count == 2
    assert db.query(IdentityNeighborhoodSnapshot).filter_by(scan_id=scan.id).count() == 2
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1
    assert run.provider_request_count == 0
    assert calls == ["neighborhoods", "g2"]
