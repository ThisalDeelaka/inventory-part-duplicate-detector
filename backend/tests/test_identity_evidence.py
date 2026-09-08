import dataclasses
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import event, inspect

from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.db.migrations import ensure_identity_discovery_tables
from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    HumanIdentityConstraint,
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityEvidenceRun as IdentityEvidenceRunRow,
    IdentityGroupProjectionRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodSnapshot,
    RuleExclusionAudit,
    ScanRecordSnapshot,
)
from app.engine.identity_edge import IdentityEdgeClass, classify_identity_edge
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.engine.scoring import score_candidate
from app.evidence.contracts import IdentityEvidenceEdge, IdentityEvidenceRun
from app.repositories.discovery_repository import DiscoveryRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.services.canonical_record_service import create_or_get_scan_record_catalog
from app.services.identity_discovery_service import (
    persist_discovery_proposals,
    start_discovery_run,
)
from app.services.identity_evidence_service import (
    acquire_identity_evidence,
    load_evidence_runs_for_discovery,
    start_identity_evidence_run,
)
from app.services.identity_neighborhood_service import (
    build_and_persist_identity_neighborhoods,
)
from app.services.scan_runner import ScanRunner


def configuration(**values):
    defaults = dict(
        hybrid_retrieval_enabled=False,
        identity_neighborhood_max_members=20,
        llm_provider="none",
        llm_demo_enabled=False,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def row(part_no, description, **values):
    result = {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "CONTRACT": "S1",
        "UNIT_MEAS": "EA",
        "ACCOUNTING_GROUP": "AG1",
        "HSN_SAC_CODE": "1000",
        "PRODUCT_CATEGORY_ID": "CAT1",
    }
    result.update(values)
    return result


def prepare_discovery(db, records, edges, *, selected_fields=None):
    selected_fields = selected_fields or ["CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP"]
    frame = pd.DataFrame(records)
    frame[SOURCE_ROW_INDEX_FIELD] = range(len(frame))
    scan = DuplicateScan(
        scan_name="GF-4 fixture",
        selected_fields=json.dumps(selected_fields),
        threshold=60,
        model_version="test",
        scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(scan)
    db.commit()
    catalog = create_or_get_scan_record_catalog(
        db, scan_id=scan.id, records=frame.to_dict(orient="records")
    )
    db.commit()
    run = start_discovery_run(
        db,
        scan_id=scan.id,
        catalog_records=catalog.records,
        configuration=configuration(),
        scan_mode=scan.scan_mode,
        selected_fields=selected_fields,
    )
    db.commit()
    engine_records = frame.to_dict(orient="records")
    proposals = [
        {
            "record_a": engine_records[left],
            "record_b": engine_records[right],
            "matched_fields": [],
            "mismatched_fields": [],
            "warnings": [],
        }
        for left, right in edges
    ]
    persist_discovery_proposals(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        catalog_records=catalog.records,
        standard_pairs=proposals,
        hybrid_result=None,
        engine_records=engine_records,
    )
    build_and_persist_identity_neighborhoods(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        max_members=20,
    )
    db.commit()
    return scan, catalog, run, tuple(selected_fields)


def acquire(db, records, edges, *, selected_fields=None):
    scan, catalog, discovery, selected = prepare_discovery(
        db, records, edges, selected_fields=selected_fields
    )
    run = start_identity_evidence_run(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.discovery_run_id,
        context=DeterministicIdentityContext(scan.scan_mode, selected),
    )
    assert run.status.value == "RUNNING"
    db.commit()
    result = acquire_identity_evidence(db, evidence_run_id=run.evidence_run_id)
    db.commit()
    return scan, catalog, discovery, result


def test_evidence_contracts_are_frozen_and_contain_no_group_human_or_llm_authority():
    forbidden = {
        "group_status", "group_confidence", "human_review_decision", "llm_result",
        "final_identity_set", "duplicate_probability",
    }
    for contract in (IdentityEvidenceRun, IdentityEvidenceEdge):
        assert dataclasses.is_dataclass(contract)
        assert contract.__dataclass_params__.frozen is True
        assert not forbidden & {field.name for field in dataclasses.fields(contract)}


def test_all_four_signed_classes_use_production_deterministic_logic(db):
    records = [
        row("SKF-6205-A", "SKF BEARING 6205 25MM"),
        row("SKF6205A", "SKF BEARING 6205 25 MM"),
        row("M1", "MOTOR BEARING 6205"),
        row("M2", "MOTOR BEARING SKF 6205"),
        row("D1", "BEARING 10MM"),
        row("D2", "BEARING 20MM"),
        row("N1", "BEARING"),
        row("N2", "FILTER"),
    ]
    _scan, _catalog, _discovery, result = acquire(
        db, records, [(0, 1), (2, 3), (4, 5), (6, 7)]
    )
    assert [edge.edge_class for edge in result.edges] == [
        IdentityEdgeClass.STRONG_SUPPORT,
        IdentityEdgeClass.REVIEW_SUPPORT,
        IdentityEdgeClass.CANNOT_LINK,
        IdentityEdgeClass.NON_GROUPABLE,
    ]
    assert result.run.proposal_count_expected == result.run.edge_count_persisted == 4
    assert (
        result.run.strong_support_count
        + result.run.review_support_count
        + result.run.cannot_link_count
        + result.run.non_groupable_count
    ) == 4


def test_gf4_inherits_generic_safety_and_existing_part_number_rescue(db):
    records = [
        row("A", "BEARING"),
        row("B", "BEARING"),
        row("BRG-6205-A", "BEARING"),
        row("BRG6205A", "BEARING"),
    ]
    _scan, _catalog, _discovery, result = acquire(db, records, [(0, 1), (2, 3)])
    by_pair = {(edge.record_id_1, edge.record_id_2): edge for edge in result.edges}
    ordered = sorted(by_pair)
    assert by_pair[ordered[0]].edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert by_pair[ordered[1]].edge_class == IdentityEdgeClass.STRONG_SUPPORT
    assert json.loads(by_pair[ordered[0]].generic_evidence_json)[
        "generic_description_warning"
    ] is True


@pytest.mark.parametrize("field", ["CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP"])
def test_context_difference_alone_is_not_cannot_link_in_pure_gf4_seam(db, field):
    left = row("A", "BEARING")
    right = row("B", "BEARING")
    right[field] = "DIFFERENT"
    _scan, catalog, _discovery = prepare_discovery(db, [left, right], [(0, 1)])[:3]
    evaluated = evaluate_canonical_identity_relationship(
        catalog.records[1],
        catalog.records[0],
        DeterministicIdentityContext("SAME_SITE_DUPLICATE", (field,)),
    )
    assert evaluated.edge_class != IdentityEdgeClass.CANNOT_LINK


def test_protected_technical_conflict_is_cannot_link_with_stable_reason(db):
    _scan, _catalog, _discovery, result = acquire(
        db, [row("A", "MOTOR 10A"), row("B", "MOTOR 20A")], [(0, 1)]
    )
    edge = result.edges[0]
    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert edge.classification_reason_codes == (
        "CRITICAL_MISMATCH_ELECTRICAL_RATING",
    )
    assert json.loads(edge.protected_conflicts_json)[0]["group"] == "ELECTRICAL_RATING"


def test_pure_evaluator_matches_authoritative_edge_semantics_and_is_orientation_stable(db):
    _scan, catalog, _discovery = prepare_discovery(
        db,
        [row("M1", "MOTOR BEARING 6205"), row("M2", "MOTOR BEARING SKF 6205")],
        [(0, 1)],
    )[:3]
    context = DeterministicIdentityContext(
        "SAME_SITE_DUPLICATE", ("CONTRACT", "UNIT_MEAS")
    )
    forward = evaluate_canonical_identity_relationship(
        catalog.records[0], catalog.records[1], context
    )
    reverse = evaluate_canonical_identity_relationship(
        catalog.records[1], catalog.records[0], context
    )
    current = classify_identity_edge(score_candidate(
        {
            "PART_NO": "M1", "DESCRIPTION": "MOTOR BEARING 6205",
            "CONTRACT": "S1", "UNIT_MEAS": "EA",
            "ACCOUNTING_GROUP": "AG1", "HSN_SAC_CODE": "1000",
            "PRODUCT_CATEGORY_ID": "CAT1",
        },
        {
            "PART_NO": "M2", "DESCRIPTION": "MOTOR BEARING SKF 6205",
            "CONTRACT": "S1", "UNIT_MEAS": "EA",
            "ACCOUNTING_GROUP": "AG1", "HSN_SAC_CODE": "1000",
            "PRODUCT_CATEGORY_ID": "CAT1",
        },
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    ))
    assert forward.edge_class == current.edge_class
    assert forward.classification_reason_codes == tuple(sorted(current.reason_codes))
    assert forward == reverse


def test_proposal_coverage_overlap_and_no_transitive_edge(db):
    scan, catalog, discovery, result = acquire(
        db,
        [row("A", "PUMP MODEL 100"), row("B", "PUMP MODEL 100"), row("C", "PUMP MODEL 100")],
        [(0, 1), (1, 2)],
    )
    ids = [record.record_id for record in catalog.records]
    assert {(edge.record_id_1, edge.record_id_2) for edge in result.edges} == {
        (ids[0], ids[1]), (ids[1], ids[2]),
    }
    assert (ids[0], ids[2]) not in {
        (edge.record_id_1, edge.record_id_2) for edge in result.edges
    }
    assert result.run.edge_count_persisted == 2
    assert db.query(IdentityNeighborhoodSnapshot).filter_by(scan_id=scan.id).count() == 3
    assert db.query(IdentityNeighborProposal).filter_by(
        discovery_run_id=discovery.discovery_run_id
    ).count() == 2
    targeted = evaluate_canonical_identity_relationship(
        catalog.records[0],
        catalog.records[2],
        DeterministicIdentityContext(
            scan.scan_mode, ("CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP")
        ),
    )
    assert (targeted.record_id_1, targeted.record_id_2) == (ids[0], ids[2])
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(scan_id=scan.id).count() == 2


def test_source_proposal_and_same_scan_catalog_provenance_are_exact(db):
    _scan, catalog, discovery, result = acquire(
        db, [row("A", "VALVE 100"), row("B", "VALVE 100")], [(0, 1)]
    )
    proposal = DiscoveryRepository(db).proposals_for_run(discovery.discovery_run_id)[0]
    edge = result.edges[0]
    assert edge.source_proposal_id == proposal.id
    assert (edge.record_id_1, edge.record_id_2) == (
        catalog.records[0].record_id, catalog.records[1].record_id,
    )
    assert edge.scan_id == catalog.records[0].scan_id == catalog.records[1].scan_id


def test_acquisition_is_idempotent_and_terminal_rows_are_immutable(db):
    scan, _catalog, discovery, first = acquire(
        db, [row("A", "VALVE 100"), row("B", "VALVE 100")], [(0, 1)]
    )
    repeated_run = start_identity_evidence_run(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.discovery_run_id,
        context=DeterministicIdentityContext(
            scan.scan_mode, ("CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP")
        ),
    )
    second = acquire_identity_evidence(db, evidence_run_id=repeated_run.evidence_run_id)
    assert repeated_run.evidence_run_id == first.run.evidence_run_id
    assert second.idempotent is True
    assert [edge.evidence_fingerprint for edge in second.edges] == [
        edge.evidence_fingerprint for edge in first.edges
    ]
    assert db.query(IdentityEvidenceEdgeSnapshot).count() == 1

    with pytest.raises(ValueError, match="incompatible with discovery"):
        start_identity_evidence_run(
            db,
            scan_id=scan.id,
            discovery_run_id=discovery.discovery_run_id,
            context=DeterministicIdentityContext(scan.scan_mode, ("CONTRACT",)),
        )

    row_model = db.get(IdentityEvidenceRunRow, first.run.evidence_run_id)
    row_model.safe_failure_category = "MUTATION"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()


def test_shuffled_catalog_and_proposal_reads_preserve_classes_summaries_and_fingerprints(
    db, monkeypatch
):
    scan, catalog, discovery, selected = prepare_discovery(
        db,
        [row("A", "BEARING"), row("B", "BEARING"), row("C", "BEARING 10MM")],
        [(0, 1), (1, 2)],
    )
    context = DeterministicIdentityContext(scan.scan_mode, selected)
    proposals = DiscoveryRepository(db).proposals_for_run(discovery.discovery_run_id)
    expected = {
        (proposal.record_id_1, proposal.record_id_2): evaluate_canonical_identity_relationship(
            next(item for item in catalog.records if item.record_id == proposal.record_id_1),
            next(item for item in catalog.records if item.record_id == proposal.record_id_2),
            context,
        )
        for proposal in proposals
    }
    run = start_identity_evidence_run(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.discovery_run_id,
        context=context,
    )
    db.commit()

    original_proposals = DiscoveryRepository.proposals_for_run
    monkeypatch.setattr(
        "app.services.identity_evidence_service.load_scan_record_catalog",
        lambda _db, _scan_id: tuple(reversed(catalog.records)),
    )

    def reversed_proposals(repository, discovery_run_id):
        return list(reversed(original_proposals(repository, discovery_run_id)))

    monkeypatch.setattr(DiscoveryRepository, "proposals_for_run", reversed_proposals)
    result = acquire_identity_evidence(db, evidence_run_id=run.evidence_run_id)
    actual = {(edge.record_id_1, edge.record_id_2): edge for edge in result.edges}
    assert set(actual) == set(expected)
    for pair, edge in actual.items():
        assert edge.edge_class == expected[pair].edge_class
        assert edge.evidence_fingerprint == expected[pair].evidence_fingerprint
        assert edge.component_scores_json == expected[pair].component_scores_json
        assert edge.technical_evidence_json == expected[pair].technical_evidence_json


def test_acquisition_does_not_read_legacy_pair_group_review_or_llm_authority(db, monkeypatch):
    scan, _catalog, discovery, selected = prepare_discovery(
        db, [row("A", "VALVE 100"), row("B", "VALVE 100")], [(0, 1)]
    )
    run = start_identity_evidence_run(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.discovery_run_id,
        context=DeterministicIdentityContext(scan.scan_mode, selected),
    )
    db.commit()
    statements = []

    def record_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    event.listen(db.bind, "before_cursor_execute", record_select)
    try:
        acquire_identity_evidence(db, evidence_run_id=run.evidence_run_id)
    finally:
        event.remove(db.bind, "before_cursor_execute", record_select)
    forbidden = (
        "duplicate_candidate", "rule_exclusion_audit", "duplicate_feedback",
        "llm_advisory_snapshot", "identity_group_projection_run",
        "identity_group_snapshot", "human_identity_constraint",
    )
    assert not any(table in statement for table in forbidden for statement in statements)
    assert len(statements) <= 15


def test_failure_rolls_back_partial_edges_and_preserves_completed_discovery(db, monkeypatch):
    def fail_after_one(repository, rows):
        if rows:
            repository.db.add(rows[0])
            repository.db.flush()
        raise RuntimeError("forced GF-4 persistence failure")

    monkeypatch.setattr(EvidenceRepository, "add_edges", fail_after_one)
    data = pd.DataFrame([
        row("A", "VALVE MODEL 100"),
        row("B", "VALVE MODEL 100"),
    ])
    with pytest.raises(RuntimeError, match="forced GF-4 persistence failure"):
        ScanRunner(db, configuration()).run(
            data, "failed GF-4", ["CONTRACT", "UNIT_MEAS"], 60
        )

    scan = db.query(DuplicateScan).one()
    discovery = db.query(IdentityDiscoveryRun).one()
    evidence = db.query(IdentityEvidenceRunRow).one()
    assert scan.status == "FAILED"
    assert discovery.status == "COMPLETED"
    assert evidence.status == "FAILED"
    assert db.query(ScanRecordSnapshot).count() == 2
    assert db.query(IdentityNeighborProposal).count() == 1
    assert db.query(IdentityNeighborhoodSnapshot).count() == 2
    assert db.query(IdentityEvidenceEdgeSnapshot).count() == 0
    assert db.query(DuplicateCandidate).count() == 0
    assert db.query(RuleExclusionAudit).count() == 0
    assert db.query(IdentityGroupProjectionRun).count() == 0
    repeated = start_identity_evidence_run(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.id,
        context=DeterministicIdentityContext(
            scan.scan_mode, ("CONTRACT", "UNIT_MEAS")
        ),
    )
    assert repeated.evidence_run_id == evidence.id
    assert repeated.status.value == "FAILED"


def test_historical_scan_without_gf4_data_is_readable_without_backfill(db):
    scan = DuplicateScan(
        scan_name="historical", selected_fields="[]", threshold=60,
        model_version="historical", scan_mode="SAME_SITE_DUPLICATE", status="COMPLETED",
    )
    db.add(scan)
    db.commit()
    assert load_evidence_runs_for_discovery(db, 999999) == ()
    assert db.query(IdentityEvidenceRunRow).count() == 0
    assert db.query(IdentityEvidenceEdgeSnapshot).count() == 0


def test_additive_migration_creates_gf4_tables(db):
    engine = db.get_bind()
    IdentityEvidenceEdgeSnapshot.__table__.drop(engine)
    IdentityEvidenceRunRow.__table__.drop(engine)
    ensure_identity_discovery_tables(engine)
    assert {"identity_evidence_run", "identity_evidence_edge_snapshot"} <= set(
        inspect(engine).get_table_names()
    )


def test_normal_scan_completes_gf4_before_legacy_writes_and_g2_with_zero_providers(
    db, monkeypatch
):
    from app.services import scan_runner as scan_runner_module

    def provider_called(*_args, **_kwargs):
        raise AssertionError("deterministic GF-4 invoked an external provider")

    calls = []
    original_acquire = scan_runner_module.acquire_identity_evidence
    original_projection = scan_runner_module.project_and_persist_identity_groups

    def evidence(*args, **kwargs):
        assert db.query(DuplicateCandidate).count() == 0
        assert db.query(RuleExclusionAudit).count() == 0
        assert db.query(IdentityGroupProjectionRun).count() == 0
        result = original_acquire(*args, **kwargs)
        calls.append("gf4")
        return result

    def projection(*args, **kwargs):
        assert calls == ["gf4"]
        calls.append("g2")
        return original_projection(*args, **kwargs)

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.group_provider_factory.create_group_advisory_provider", provider_called
    )
    monkeypatch.setattr(scan_runner_module, "acquire_identity_evidence", evidence)
    monkeypatch.setattr(scan_runner_module, "project_and_persist_identity_groups", projection)
    data = pd.DataFrame([
        row("A", "MCB30A"),
        row("B", "MCB 30 A"),
    ])
    scan, _ = ScanRunner(db, configuration()).run(
        data, "normal GF-4", ["CONTRACT", "UNIT_MEAS"], 60
    )
    evidence_run = db.query(IdentityEvidenceRunRow).filter_by(scan_id=scan.id).one()
    assert scan.status == "COMPLETED"
    assert evidence_run.status == "COMPLETED"
    assert evidence_run.edge_count_persisted == evidence_run.proposal_count_expected == 1
    assert db.query(DuplicateCandidate).filter_by(scan_id=scan.id).count() == 1
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1
    assert db.query(HumanIdentityConstraint).count() == 0
    assert calls == ["gf4", "g2"]
