from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import DuplicateCandidate, DuplicateFeedback


def save_feedback(db: Session, candidate_id: int, decision: str, comment: str | None, created_by: str):
    candidate = db.query(DuplicateCandidate).filter(DuplicateCandidate.id == candidate_id).first()
    if not candidate: return None
    item = DuplicateFeedback(candidate_id=candidate_id, user_decision=decision, user_comment=comment, created_by=created_by)
    candidate.review_status = decision
    candidate.reviewed_by = created_by
    candidate.reviewed_at = datetime.now(timezone.utc)
    db.add(item); db.commit(); db.refresh(item)
    return item
