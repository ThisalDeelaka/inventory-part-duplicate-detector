from sqlalchemy.orm import Session

from app.repositories.candidate_repository import CandidateRepository
from app.repositories.scan_repository import ScanRepository
from app.repositories.warning_repository import WarningRepository
from app.services.scan_runner import ScanRunner


def run_scan(db: Session, df, scan_name: str, selected_fields: list[str], threshold: float, source_type="CSV", sensitive_mode: bool = True):
    return ScanRunner(db).run(df, scan_name, selected_fields, threshold, source_type, sensitive_mode)


def list_scans(db: Session):
    return ScanRepository(db).list()


def get_scan(db: Session, scan_id):
    return ScanRepository(db).get(scan_id)


def get_scan_candidates(db: Session, scan_id):
    return CandidateRepository(db).list_for_scan(scan_id)


def get_scan_warnings(db: Session, scan_id):
    return WarningRepository(db).list_for_scan(scan_id)
