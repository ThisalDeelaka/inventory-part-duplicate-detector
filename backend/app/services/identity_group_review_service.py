"""Append-only human review and deterministic scan-local constraint resolution."""

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.db.models import (
    HumanIdentityConstraint,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupReviewPartition,
    IdentityGroupReviewPartitionMember,
    IdentityGroupSnapshot,
)


class GroupReviewDecision(str, Enum):
    CONFIRM_ALL_AS_ONE = "CONFIRM_ALL_AS_ONE"
    CONFIRM_SELECTED = "CONFIRM_SELECTED"
    SPLIT_PARTITIONS = "SPLIT_PARTITIONS"
    KEEP_ALL_SEPARATE = "KEEP_ALL_SEPARATE"
    UNSURE = "UNSURE"


class HumanConstraintType(str, Enum):
    MUST_LINK = "MUST_LINK"
    CANNOT_LINK = "CANNOT_LINK"


@dataclass(frozen=True, order=True)
class DerivedHumanConstraint:
    left_record_ref_key: str
    right_record_ref_key: str
    constraint_type: HumanConstraintType


@dataclass(frozen=True)
class EffectiveHumanConstraint:
    scan_id: int
    left_record_ref_key: str
    right_record_ref_key: str
    constraint_type: HumanConstraintType
    source_review_event_ids: tuple[int, ...]


@dataclass(frozen=True)
class CreatedGroupReview:
    review_event_id: int
    decision_type: GroupReviewDecision
    partition_count: int
    constraint_count: int
    supersedes_review_event_id: int | None


class GroupReviewValidationError(ValueError):
    pass


class GroupReviewTargetNotFoundError(GroupReviewValidationError):
    pass


class StaleGroupReviewError(GroupReviewValidationError):
    pass


class ConflictingEffectiveConstraintError(RuntimeError):
    pass


def _canonical_members(values: Iterable[str]) -> tuple[str, ...]:
    members = tuple(str(value).strip() for value in values)
    if not members or any(not value for value in members):
        raise GroupReviewValidationError("review members must be nonblank")
    if len(set(members)) != len(members):
        raise GroupReviewValidationError("review members must not contain duplicates")
    return tuple(sorted(members))


def canonical_review_partitions(
    decision_type: GroupReviewDecision,
    immutable_members: Iterable[str],
    *,
    submitted_members: Iterable[str] = (),
    partitions: Iterable[Iterable[str]] = (),
) -> tuple[tuple[str, ...], ...]:
    """Validate a decision against an immutable member set and canonicalize its blocks."""
    decision_type = GroupReviewDecision(decision_type)
    immutable = _canonical_members(immutable_members)
    immutable_set = set(immutable)
    submitted = tuple(submitted_members)
    provided_partitions = tuple(tuple(block) for block in partitions)

    if decision_type in {
        GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        GroupReviewDecision.KEEP_ALL_SEPARATE,
        GroupReviewDecision.UNSURE,
    }:
        if provided_partitions:
            raise GroupReviewValidationError("this decision does not accept partitions")
        if _canonical_members(submitted) != immutable:
            raise GroupReviewValidationError("submitted members must exactly match the immutable group")
        if decision_type == GroupReviewDecision.CONFIRM_ALL_AS_ONE:
            return (immutable,)
        if decision_type == GroupReviewDecision.KEEP_ALL_SEPARATE:
            return tuple((member,) for member in immutable)
        return ()

    if decision_type == GroupReviewDecision.CONFIRM_SELECTED:
        if provided_partitions:
            raise GroupReviewValidationError("CONFIRM_SELECTED does not accept partitions")
        selected = _canonical_members(submitted)
        if len(selected) < 2:
            raise GroupReviewValidationError("CONFIRM_SELECTED requires at least two members")
        if not set(selected).issubset(immutable_set):
            raise GroupReviewValidationError("selected member is not in the immutable group")
        return (selected,)

    if submitted:
        raise GroupReviewValidationError("SPLIT_PARTITIONS uses partitions, not selected members")
    if len(provided_partitions) < 2:
        raise GroupReviewValidationError("SPLIT_PARTITIONS requires at least two partitions")
    canonical = tuple(_canonical_members(block) for block in provided_partitions)
    flattened = tuple(member for block in canonical for member in block)
    if len(flattened) != len(set(flattened)):
        raise GroupReviewValidationError("a member appears in multiple partitions")
    if set(flattened) != immutable_set:
        raise GroupReviewValidationError("partitions must contain every immutable member exactly once")
    return tuple(sorted(canonical))


def derive_human_identity_constraints(
    decision_type: GroupReviewDecision,
    immutable_members: Iterable[str],
    *,
    submitted_members: Iterable[str] = (),
    partitions: Iterable[Iterable[str]] = (),
) -> tuple[DerivedHumanConstraint, ...]:
    """Pure, bounded, input-order-independent pair-constraint derivation."""
    decision_type = GroupReviewDecision(decision_type)
    immutable = _canonical_members(immutable_members)
    if len(immutable) > 20:
        raise GroupReviewValidationError("group review is bounded to 20 immutable members")
    blocks = canonical_review_partitions(
        decision_type, immutable, submitted_members=submitted_members, partitions=partitions
    )
    derived = set()
    if decision_type in {
        GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        GroupReviewDecision.CONFIRM_SELECTED,
        GroupReviewDecision.SPLIT_PARTITIONS,
    }:
        for block in blocks:
            for left, right in combinations(block, 2):
                derived.add(DerivedHumanConstraint(left, right, HumanConstraintType.MUST_LINK))
    if decision_type == GroupReviewDecision.SPLIT_PARTITIONS:
        for left_index, left_block in enumerate(blocks):
            for right_block in blocks[left_index + 1:]:
                for left in left_block:
                    for right in right_block:
                        first, second = sorted((left, right))
                        derived.add(DerivedHumanConstraint(first, second, HumanConstraintType.CANNOT_LINK))
    elif decision_type == GroupReviewDecision.KEEP_ALL_SEPARATE:
        for left, right in combinations(immutable, 2):
            derived.add(DerivedHumanConstraint(left, right, HumanConstraintType.CANNOT_LINK))
    return tuple(sorted(derived))


class IdentityGroupReviewService:
    def __init__(self, db):
        self.db = db

    def _group_members(self, scan_id, projection_run_id, group_snapshot_id, hypothesis_key):
        group = self.db.query(IdentityGroupSnapshot).join(
            IdentityGroupProjectionRun,
            IdentityGroupProjectionRun.id == IdentityGroupSnapshot.projection_run_id,
        ).filter(
            IdentityGroupSnapshot.id == group_snapshot_id,
            IdentityGroupSnapshot.scan_id == scan_id,
            IdentityGroupSnapshot.projection_run_id == projection_run_id,
            IdentityGroupSnapshot.hypothesis_key == hypothesis_key,
            IdentityGroupProjectionRun.scan_id == scan_id,
            IdentityGroupProjectionRun.status == "COMPLETED",
            IdentityGroupSnapshot.group_status.in_([
                "LIKELY_DUPLICATE_GROUP", "POSSIBLE_DUPLICATE_GROUP_REVIEW"
            ]),
        ).one_or_none()
        if group is None:
            raise GroupReviewValidationError("accepted immutable group snapshot reference is invalid")
        members = self.db.query(IdentityGroupMemberSnapshot.record_ref_key).filter_by(
            group_snapshot_id=group.id
        ).order_by(IdentityGroupMemberSnapshot.member_index).all()
        keys = tuple(row[0] for row in members)
        if len(keys) != group.group_size or len(set(keys)) != len(keys):
            raise GroupReviewValidationError("immutable group membership is inconsistent")
        return group, keys

    def group_members(self, scan_id, projection_run_id, group_snapshot_id, hypothesis_key):
        """Return server-authoritative immutable membership for a typed review write."""
        return self._group_members(
            scan_id, projection_run_id, group_snapshot_id, hypothesis_key
        )[1]

    def _accepted_group(self, scan_id, group_snapshot_id):
        group = self.db.query(IdentityGroupSnapshot).join(
            IdentityGroupProjectionRun,
            IdentityGroupProjectionRun.id == IdentityGroupSnapshot.projection_run_id,
        ).filter(
            IdentityGroupSnapshot.id == group_snapshot_id,
            IdentityGroupSnapshot.scan_id == scan_id,
            IdentityGroupProjectionRun.scan_id == scan_id,
            IdentityGroupProjectionRun.status == "COMPLETED",
            IdentityGroupSnapshot.group_status.in_([
                "LIKELY_DUPLICATE_GROUP", "POSSIBLE_DUPLICATE_GROUP_REVIEW"
            ]),
        ).one_or_none()
        if group is None:
            raise GroupReviewTargetNotFoundError(
                "Accepted identity group snapshot not found for scan"
            )
        return group

    def current_review(self, group_snapshot_id):
        successor = aliased(IdentityGroupReviewEvent)
        return self.db.query(IdentityGroupReviewEvent).outerjoin(
            successor,
            successor.supersedes_review_event_id == IdentityGroupReviewEvent.id,
        ).filter(
            IdentityGroupReviewEvent.group_snapshot_id == group_snapshot_id,
            successor.id.is_(None),
        ).order_by(IdentityGroupReviewEvent.id.desc()).first()

    def history(self, group_snapshot_id):
        return self.db.query(IdentityGroupReviewEvent).filter_by(
            group_snapshot_id=group_snapshot_id
        ).order_by(IdentityGroupReviewEvent.id).all()

    def review_history(self, scan_id, group_snapshot_id):
        """Load one exact group's complete review graph in bounded bulk queries."""
        self._accepted_group(scan_id, group_snapshot_id)
        events = self.history(group_snapshot_id)
        if not events:
            return ()
        event_ids = [row.id for row in events]
        partition_rows = self.db.query(
            IdentityGroupReviewPartition, IdentityGroupReviewPartitionMember
        ).join(
            IdentityGroupReviewPartitionMember,
            IdentityGroupReviewPartitionMember.partition_id
            == IdentityGroupReviewPartition.id,
        ).filter(
            IdentityGroupReviewPartition.review_event_id.in_(event_ids)
        ).order_by(
            IdentityGroupReviewPartition.review_event_id,
            IdentityGroupReviewPartition.partition_index,
            IdentityGroupReviewPartitionMember.member_index,
        ).all()
        count_rows = self.db.query(
            HumanIdentityConstraint.source_review_event_id,
            HumanIdentityConstraint.constraint_type,
            func.count(HumanIdentityConstraint.id),
        ).filter(
            HumanIdentityConstraint.source_review_event_id.in_(event_ids)
        ).group_by(
            HumanIdentityConstraint.source_review_event_id,
            HumanIdentityConstraint.constraint_type,
        ).all()
        partitions = {}
        for partition, member in partition_rows:
            event_partitions = partitions.setdefault(partition.review_event_id, {})
            event_partitions.setdefault(partition.partition_index, []).append(
                member.record_ref_key
            )
        counts = {
            (event_id, constraint_type): count
            for event_id, constraint_type, count in count_rows
        }
        superseded_ids = {
            row.supersedes_review_event_id
            for row in events if row.supersedes_review_event_id is not None
        }
        return tuple({
            "review_event_id": row.id,
            "scan_id": row.scan_id,
            "projection_run_id": row.projection_run_id,
            "group_snapshot_id": row.group_snapshot_id,
            "group_hypothesis_key": row.group_hypothesis_key,
            "decision_type": row.decision_type,
            "reviewer": row.reviewer,
            "comment": row.comment,
            "created_at": row.created_at,
            "supersedes_review_event_id": row.supersedes_review_event_id,
            "is_current": row.id not in superseded_ids,
            "partitions": [
                members for _, members in sorted(partitions.get(row.id, {}).items())
            ],
            "derived_constraint_counts": {
                "must_link_count": counts.get((row.id, "MUST_LINK"), 0),
                "cannot_link_count": counts.get((row.id, "CANNOT_LINK"), 0),
            },
        } for row in events)

    def current_review_state(self, scan_id, group_snapshot_id):
        history = self.review_history(scan_id, group_snapshot_id)
        current = next((row for row in reversed(history) if row["is_current"]), None)
        return {"reviewed": current is not None, "current_review": current}

    def create_review(
        self,
        *,
        scan_id: int,
        projection_run_id: int,
        group_snapshot_id: int,
        group_hypothesis_key: str,
        decision_type: GroupReviewDecision,
        reviewer: str,
        submitted_members: Iterable[str] = (),
        partitions: Iterable[Iterable[str]] = (),
        comment: str | None = None,
        supersedes_review_event_id: int | None = None,
    ) -> CreatedGroupReview:
        reviewer = str(reviewer or "").strip()
        if not reviewer:
            raise GroupReviewValidationError("reviewer is required")
        group, immutable_members = self._group_members(
            scan_id, projection_run_id, group_snapshot_id, group_hypothesis_key
        )
        decision_type = GroupReviewDecision(decision_type)
        blocks = canonical_review_partitions(
            decision_type, immutable_members,
            submitted_members=submitted_members, partitions=partitions,
        )
        constraints = derive_human_identity_constraints(
            decision_type, immutable_members,
            submitted_members=submitted_members, partitions=partitions,
        )
        current = self.current_review(group.id)
        if current is None and supersedes_review_event_id is not None:
            raise StaleGroupReviewError("review changed; reload the current review before saving")
        if current is not None and supersedes_review_event_id != current.id:
            raise StaleGroupReviewError("review changed; reload the current review before saving")
        try:
            event = IdentityGroupReviewEvent(
                scan_id=scan_id, projection_run_id=projection_run_id,
                group_snapshot_id=group.id, group_hypothesis_key=group.hypothesis_key,
                decision_type=decision_type.value, reviewer=reviewer,
                comment=comment, supersedes_review_event_id=supersedes_review_event_id,
                initial_group_snapshot_id=(
                    group.id if supersedes_review_event_id is None else None
                ),
            )
            self.db.add(event)
            self.db.flush()
            for partition_index, block in enumerate(blocks):
                partition = IdentityGroupReviewPartition(
                    review_event_id=event.id, partition_index=partition_index
                )
                self.db.add(partition)
                self.db.flush()
                self.db.add_all([
                    IdentityGroupReviewPartitionMember(
                        review_event_id=event.id, partition_id=partition.id,
                        member_index=member_index, record_ref_key=record_ref_key,
                    )
                    for member_index, record_ref_key in enumerate(block)
                ])
            self.db.add_all([
                HumanIdentityConstraint(
                    scan_id=scan_id,
                    left_record_ref_key=item.left_record_ref_key,
                    right_record_ref_key=item.right_record_ref_key,
                    constraint_type=item.constraint_type.value,
                    source_review_event_id=event.id,
                )
                for item in constraints
            ])
            self.db.commit()
            return CreatedGroupReview(
                event.id, decision_type, len(blocks), len(constraints),
                supersedes_review_event_id,
            )
        except IntegrityError:
            self.db.rollback()
            raise StaleGroupReviewError(
                "review changed; reload the current review before saving"
            ) from None
        except Exception:
            self.db.rollback()
            raise

    def effective_constraints(self, scan_id: int) -> tuple[EffectiveHumanConstraint, ...]:
        successor = aliased(IdentityGroupReviewEvent)
        rows = self.db.query(HumanIdentityConstraint, IdentityGroupReviewEvent).join(
            IdentityGroupReviewEvent,
            IdentityGroupReviewEvent.id == HumanIdentityConstraint.source_review_event_id,
        ).outerjoin(
            successor,
            successor.supersedes_review_event_id == IdentityGroupReviewEvent.id,
        ).filter(
            HumanIdentityConstraint.scan_id == scan_id,
            successor.id.is_(None),
        ).order_by(
            HumanIdentityConstraint.left_record_ref_key,
            HumanIdentityConstraint.right_record_ref_key,
            IdentityGroupReviewEvent.id,
        ).all()
        by_pair = {}
        for constraint, event in rows:
            pair = (constraint.left_record_ref_key, constraint.right_record_ref_key)
            by_pair.setdefault(pair, []).append((constraint.constraint_type, event.id))
        effective = []
        for pair, values in sorted(by_pair.items()):
            types = {value[0] for value in values}
            if len(types) > 1:
                raise ConflictingEffectiveConstraintError(
                    f"active group reviews disagree for scan-local pair {pair[0]} / {pair[1]}"
                )
            effective.append(EffectiveHumanConstraint(
                scan_id, pair[0], pair[1], HumanConstraintType(values[0][0]),
                tuple(value[1] for value in values),
            ))
        return tuple(effective)

    def project_with_effective_constraints(self, *, scan_id: int, **projection_inputs):
        """Explicit future-projection adapter; never persists or auto-runs a projection."""
        from app.services.identity_group_projection import project_identity_groups

        return project_identity_groups(
            scan_id=scan_id,
            human_constraints=self.effective_constraints(scan_id),
            **projection_inputs,
        )
