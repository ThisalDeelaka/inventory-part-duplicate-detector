from sqlalchemy.orm import Session

from app.repositories.candidate_repository import CandidateRepository
from app.repositories.scan_repository import ScanRepository
from app.repositories.rejection_repository import RejectionRepository
from app.repositories.warning_repository import WarningRepository
from app.services.scan_runner import ScanRunner


def run_scan(
    db: Session,
    df,
    scan_name: str,
    selected_fields: list[str],
    threshold: float,
    source_type="CSV",
    sensitive_mode: bool = True,
    scan_mode: str = "SAME_SITE_DUPLICATE",
    strict_custom_fields: list[dict] | None = None,
    custom_fields_used: list[dict] | None = None,
    part_type: str = "INVENTORY",
):
    return ScanRunner(db).run(
        df, scan_name, selected_fields, threshold, source_type, sensitive_mode, scan_mode,
        strict_custom_fields, custom_fields_used, part_type,
    )


def list_scans(db: Session):
    return ScanRepository(db).list()


def get_scan(db: Session, scan_id):
    return ScanRepository(db).get(scan_id)


def get_scan_candidates(db: Session, scan_id):
    return CandidateRepository(db).list_for_scan(scan_id)


def get_scan_warnings(db: Session, scan_id):
    return WarningRepository(db).list_for_scan(scan_id)


def get_scan_rejections(db: Session, scan_id):
    return RejectionRepository(db).list_for_scan(scan_id)
