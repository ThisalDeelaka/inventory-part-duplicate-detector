from sqlalchemy.orm import Session

from app.db.models import ScanWarning


class WarningRepository:
    def __init__(self, db: Session):
        self.db = db

    def save(self, scan_id, warning):
        item = ScanWarning(
            scan_id=scan_id,
            warning_type=warning["warning_type"],
            message=warning["message"],
            record_reference=warning.get("record_reference"),
        )
        self.db.add(item)
        return item

    def list_for_scan(self, scan_id):
        return self.db.query(ScanWarning).filter(ScanWarning.scan_id == scan_id).all()

    def count_for_scan(self, scan_id):
        return self.db.query(ScanWarning).filter(ScanWarning.scan_id == scan_id).count()
