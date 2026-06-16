import json

from sqlalchemy.orm import Session

from app.db.models import DuplicateCandidate


class CandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, scan_id, record_a, record_b, result):
        candidate = DuplicateCandidate(
            scan_id=scan_id,
            contract_a=record_a.get("CONTRACT"),
            part_no_a=str(record_a.get("PART_NO", "")),
            description_a=str(record_a.get("DESCRIPTION", "")),
            contract_b=record_b.get("CONTRACT"),
            part_no_b=str(record_b.get("PART_NO", "")),
            description_b=str(record_b.get("DESCRIPTION", "")),
            similarity_score=result["final_score"],
            confidence_level=result["confidence_level"],
            description_similarity=result["description_similarity"],
            tfidf_score=result["tfidf_score"],
            fuzzy_score=result["fuzzy_score"],
            part_no_similarity=result["part_no_similarity"],
            technical_token_score=result["technical_token_score"],
            matched_fields=json.dumps(result["matched_fields"]),
            mismatched_fields=json.dumps(result["mismatched_fields"]),
            explanation=result["explanation"],
            recommended_action=result["recommended_action"],
        )
        self.db.add(candidate)
        return candidate

    def list_for_scan(self, scan_id):
        return (
            self.db.query(DuplicateCandidate)
            .filter(DuplicateCandidate.scan_id == scan_id)
            .order_by(DuplicateCandidate.similarity_score.desc())
            .all()
        )
