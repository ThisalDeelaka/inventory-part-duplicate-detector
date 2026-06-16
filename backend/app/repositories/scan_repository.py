import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.constants import MODEL_VERSION
from app.db.models import DuplicateScan


class ScanRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, scan_name, selected_fields, threshold, source_type="CSV", scan_mode="SAME_SITE_DUPLICATE"):
        scan = DuplicateScan(
            scan_name=scan_name,
            source_type=source_type,
            selected_fields=json.dumps(selected_fields),
            threshold=threshold,
            status="RUNNING",
            model_version=MODEL_VERSION,
            scan_mode=scan_mode,
        )
        self.db.add(scan)
        self.db.commit()
        self.db.refresh(scan)
        return scan

    def update_status(self, scan, status, **counts):
        scan.status = status
        for key, value in counts.items():
            setattr(scan, key, value)
        if status in {"COMPLETED", "FAILED"}:
            scan.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(scan)
        return scan

    def get(self, scan_id):
        return self.db.query(DuplicateScan).filter(DuplicateScan.id == scan_id).first()

    def list(self):
        return self.db.query(DuplicateScan).order_by(DuplicateScan.started_at.desc()).all()
