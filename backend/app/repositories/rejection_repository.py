import json

from sqlalchemy.orm import Session

from app.db.models import RuleExclusionAudit


class RejectionRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, scan_id, record_a, record_b, result):
        item = RuleExclusionAudit(
            scan_id=scan_id,
            contract_a=record_a.get("CONTRACT"),
            part_no_a=str(record_a.get("PART_NO", "")),
            description_a=str(record_a.get("DESCRIPTION", "")),
            contract_b=record_b.get("CONTRACT"),
            part_no_b=str(record_b.get("PART_NO", "")),
            description_b=str(record_b.get("DESCRIPTION", "")),
            similarity_score=result["final_score"],
            confidence_level=result["confidence_level"],
            business_status=result["business_status"],
            rule_decision=result["rule_decision"],
            rejection_reason=result["rejection_reason"],
            critical_mismatches=json.dumps(result["critical_mismatches"]),
            explanation=result["explanation"],
        )
        self.db.add(item)
        return item

    def list_for_scan(self, scan_id):
        return (
            self.db.query(RuleExclusionAudit)
            .filter(RuleExclusionAudit.scan_id == scan_id)
            .order_by(RuleExclusionAudit.similarity_score.desc())
            .all()
        )
