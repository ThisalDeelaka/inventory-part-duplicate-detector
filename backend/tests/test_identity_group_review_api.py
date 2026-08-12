from copy import deepcopy

import pytest

from app.db.models import (
    DuplicateScan,
    HumanIdentityConstraint,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.llm.groq_provider import GroqLLMProvider
from app.services import identity_group_projection, identity_group_snapshot_service


def accepted_group(db, *, scan_id=1, size=5, key="a"):
    scan = db.query(DuplicateScan).filter_by(id=scan_id).one_or_none()
    if scan is None:
        scan = DuplicateScan(
            id=scan_id, scan_name=f"scan-{scan_id}", threshold=80,
            status="COMPLETED", model_version="deterministic-v1",
            selected_fields="[]",
        )
        db.add(scan); db.flush()
    pairs = size * (size - 1) // 2
    run = IdentityGroupProjectionRun(
        scan_id=scan_id, algorithm_version="constrained-group-projection-v1",
        edge_classifier_version="identity-edge-classifier-v1",
        evidence_fingerprint=key * 64, max_group_validation_members=20,
        engine_version="deterministic-v1", status="COMPLETED",
        records_seen=size, seed_edges=pairs, provisional_components=1,
        accepted_groups=1, likely_groups=1, review_groups=0,
        conflicting_families=0, oversized_families=0, ambiguous_families=0,
        internal_pairs_total=pairs, internal_pairs_reused=pairs,
        internal_pairs_rescored=0, cannot_links_found=0,
        max_component_size=size, max_accepted_group_size=size,
    )
    db.add(run); db.flush()
    group = IdentityGroupSnapshot(
        projection_run_id=run.id, scan_id=scan_id, hypothesis_key=key * 64,
        projection_algorithm_version=run.algorithm_version,
        group_status="LIKELY_DUPLICATE_GROUP", group_size=size,
        supporting_edge_count=pairs, review_edge_count=0,
        non_groupable_internal_count=0, internal_pair_count=pairs,
        internal_pairs_reused=pairs, internal_pairs_rescored=0,
        evidence_completeness=1, distinct_uoms_json='["PCS"]',
        same_uom_pair_count=pairs, convertible_uom_pair_count=0,
        different_basis_pair_count=0, missing_or_wildcard_pair_count=0,
        malformed_or_unknown_pair_count=0, possible_mapping_error_count=0,
        reason_codes_json="[]",
    )
    db.add(group); db.flush()
    refs = []
    for index in range(size):
        ref = f"{key}{index:02d}".ljust(64, key)
        record = ScanRecordSnapshot(
            scan_id=scan_id, record_ref_key=ref, contract="S1",
            part_no=f"PART-{key}-{index}", description=f"Component {index}",
            normalized_part_no=f"part {key} {index}",
            normalized_description=f"component {index}", uom="PCS",
            product_category_id="", hsn_sac_code="",
        )
        db.add(record); db.flush()
        db.add(IdentityGroupMemberSnapshot(
            group_snapshot_id=group.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
        refs.append(ref)
    db.commit()
    return run, group, tuple(refs)


def payload(run, group, decision, **values):
    body = {
        "projection_run_id": run.id,
        "group_hypothesis_key": group.hypothesis_key,
        "decision_type": decision,
        "reviewer": "demo-reviewer",
    }
    body.update(values)
    return body


def post(client, run, group, decision, **values):
    return client.post(
        f"/api/scans/{run.scan_id}/identity-groups/{group.id}/reviews",
        json=payload(run, group, decision, **values),
    )


def test_read_no_review_state_and_g3_state_are_typed(client, db):
    run, group, _ = accepted_group(db, size=2)
    current = client.get(
        f"/api/scans/1/identity-groups/{group.id}/reviews/current"
    )
    history = client.get(f"/api/scans/1/identity-groups/{group.id}/reviews")
    assert current.status_code == history.status_code == 200
    assert current.json() == {"reviewed": False, "current_review": None}
    assert history.json()["items"] == []
    listing = client.get(f"/api/scans/1/identity-groups?projection_run_id={run.id}").json()
    assert listing["items"][0]["review_state"]["reviewed"] is False


def test_create_confirm_all_size_four_returns_six_must_links(client, db):
    run, group, _ = accepted_group(db, size=4)
    response = post(client, run, group, "CONFIRM_ALL_AS_ONE")
    assert response.status_code == 201
    body = response.json()
    assert body["derived_constraint_counts"] == {
        "must_link_count": 6, "cannot_link_count": 0
    }
    assert len(body["partitions"]) == 1 and len(body["partitions"][0]) == 4


def test_confirm_selected_four_of_five_leaves_fifth_unresolved(client, db):
    run, group, refs = accepted_group(db, size=5)
    response = post(
        client, run, group, "CONFIRM_SELECTED",
        selected_record_ref_keys=list(reversed(refs[:4])),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["derived_constraint_counts"] == {
        "must_link_count": 6, "cannot_link_count": 0
    }
    constraints = db.query(HumanIdentityConstraint).all()
    assert len(constraints) == 6
    assert all(refs[4] not in {
        row.left_record_ref_key, row.right_record_ref_key
    } for row in constraints)


@pytest.mark.parametrize("blocks,expected", [
    ((4, 1), (6, 4)),
    ((2, 2, 1), (2, 8)),
])
def test_split_partitions_have_exact_typed_counts(client, db, blocks, expected):
    run, group, refs = accepted_group(db, size=5)
    partitions = []
    start = 0
    for size in blocks:
        partitions.append(list(reversed(refs[start:start + size])))
        start += size
    response = post(
        client, run, group, "SPLIT_PARTITIONS", partitions=partitions
    )
    assert response.status_code == 201
    assert response.json()["derived_constraint_counts"] == {
        "must_link_count": expected[0], "cannot_link_count": expected[1]
    }


@pytest.mark.parametrize("decision,must,cannot", [
    ("KEEP_ALL_SEPARATE", 0, 6),
    ("UNSURE", 0, 0),
])
def test_separate_and_unsure_contracts(client, db, decision, must, cannot):
    run, group, _ = accepted_group(db, size=4)
    response = post(client, run, group, decision)
    assert response.status_code == 201
    assert response.json()["derived_constraint_counts"] == {
        "must_link_count": must, "cannot_link_count": cannot
    }
    assert db.query(IdentityGroupReviewEvent).count() == 1


@pytest.mark.parametrize("body", [
    {"selected_record_ref_keys": ["unknown", "unknown-2"]},
    {"selected_record_ref_keys": []},
    {"partitions": [["unknown"], ["unknown-2"]]},
])
def test_invalid_selected_or_partition_membership_is_safe_422(client, db, body):
    run, group, _ = accepted_group(db, size=5)
    decision = "SPLIT_PARTITIONS" if "partitions" in body else "CONFIRM_SELECTED"
    response = post(client, run, group, decision, **body)
    assert response.status_code == 422
    assert "Traceback" not in response.text and "\\" not in response.text
    assert db.query(IdentityGroupReviewEvent).count() == 0


def test_initial_concurrency_valid_correction_stale_correction_and_history(client, db):
    run, group, _ = accepted_group(db, size=4)
    first = post(client, run, group, "UNSURE").json()
    duplicate_initial = post(client, run, group, "CONFIRM_ALL_AS_ONE")
    assert duplicate_initial.status_code == 409
    second_response = post(
        client, run, group, "KEEP_ALL_SEPARATE",
        supersedes_review_event_id=first["review_event_id"], comment="corrected",
    )
    assert second_response.status_code == 201
    second = second_response.json()
    stale = post(
        client, run, group, "UNSURE",
        supersedes_review_event_id=first["review_event_id"],
    )
    assert stale.status_code == 409 and "reload" in stale.json()["detail"]
    history = client.get(f"/api/scans/1/identity-groups/{group.id}/reviews").json()
    assert [row["review_event_id"] for row in history["items"]] == [
        first["review_event_id"], second["review_event_id"]
    ]
    assert [row["is_current"] for row in history["items"]] == [False, True]


def test_cross_scan_projection_hypothesis_and_supersession_are_rejected(client, db):
    run, group, _ = accepted_group(db, scan_id=1, size=2, key="a")
    other_run, other_group, _ = accepted_group(db, scan_id=2, size=2, key="b")
    first = post(client, run, group, "UNSURE").json()
    wrong_group = client.post(
        f"/api/scans/2/identity-groups/{other_group.id}/reviews",
        json=payload(
            other_run, other_group, "UNSURE",
            supersedes_review_event_id=first["review_event_id"],
        ),
    )
    assert wrong_group.status_code == 409
    mismatch = payload(run, group, "UNSURE")
    mismatch["group_hypothesis_key"] = "z" * 64
    assert client.post(
        f"/api/scans/1/identity-groups/{group.id}/reviews", json=mismatch
    ).status_code in {409, 422}
    assert client.get("/api/scans/1/identity-groups/999/reviews").status_code == 404


def test_review_write_does_not_mutate_snapshot_project_or_call_provider(
    client, db, monkeypatch
):
    run, group, _ = accepted_group(db, size=4)
    before = {
        "group": deepcopy({column.name: getattr(group, column.name) for column in group.__table__.columns}),
        "members": [(row.id, row.record_ref_key, row.member_index) for row in
                    db.query(IdentityGroupMemberSnapshot).filter_by(group_snapshot_id=group.id).all()],
        "run_count": db.query(IdentityGroupProjectionRun).count(),
    }
    monkeypatch.setattr(
        identity_group_projection, "project_identity_groups",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G1 called")),
    )
    monkeypatch.setattr(
        identity_group_snapshot_service, "project_and_persist_identity_groups",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G2 called")),
    )
    monkeypatch.setattr(
        GroqLLMProvider, "complete_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )
    assert post(client, run, group, "CONFIRM_ALL_AS_ONE").status_code == 201
    db.refresh(group)
    after = {
        "group": {column.name: getattr(group, column.name) for column in group.__table__.columns},
        "members": [(row.id, row.record_ref_key, row.member_index) for row in
                    db.query(IdentityGroupMemberSnapshot).filter_by(group_snapshot_id=group.id).all()],
        "run_count": db.query(IdentityGroupProjectionRun).count(),
    }
    assert after == before
    detail = client.get(f"/api/scans/1/identity-groups/{group.id}").json()
    assert detail["group_status"] == "LIKELY_DUPLICATE_GROUP"
    assert detail["review_state"]["current_decision_type"] == "CONFIRM_ALL_AS_ONE"
