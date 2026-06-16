from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.schemas import FeedbackCreate, FeedbackResponse
from app.services.feedback_service import save_feedback

router = APIRouter(prefix="/api/candidates", tags=["feedback"])


@router.post("/{candidate_id}/feedback", response_model=FeedbackResponse)
def feedback(candidate_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)):
    item = save_feedback(db, candidate_id, payload.user_decision, payload.user_comment, payload.created_by)
    if not item: raise HTTPException(404, "Candidate not found")
    return item
