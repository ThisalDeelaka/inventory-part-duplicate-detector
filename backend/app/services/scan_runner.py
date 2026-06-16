import pandas as pd
from sqlalchemy.orm import Session

from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.scoring import score_candidate
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.scan_repository import ScanRepository
from app.repositories.warning_repository import WarningRepository
from app.services.validation_service import validate_dataframe


class ScanRunner:
    def __init__(self, db: Session):
        self.db = db
        self.scans = ScanRepository(db)
        self.candidates = CandidateRepository(db)
        self.warnings = WarningRepository(db)

    def run(self, df: pd.DataFrame, scan_name: str, selected_fields: list[str], threshold: float, source_type="CSV", sensitive_mode: bool = True):
        validation = validate_dataframe(df, selected_fields, sensitive_mode=sensitive_mode)
        if validation["missing_required_columns"]:
            raise ValueError(f"Missing required columns: {', '.join(validation['missing_required_columns'])}")

        scan = self.scans.create(scan_name, selected_fields, threshold, source_type)
        try:
            for warning in validation["warnings"]:
                self.warnings.save(scan.id, warning)

            usable = df[df["DESCRIPTION"].fillna("").str.strip().ne("")].copy()
            pairs = generate_candidate_pairs(usable, selected_fields)

            existing_warnings = {(w["warning_type"], w["message"]) for w in validation["warnings"]}
            generated_warnings = {(w["warning_type"], w["message"]) for pair in pairs for w in pair["warnings"]}
            for warning_type, message in generated_warnings - existing_warnings:
                self.warnings.save(scan.id, {"warning_type": warning_type, "message": message})

            candidates_found = 0
            for pair in pairs:
                result = score_candidate(pair["record_a"], pair["record_b"], selected_fields)
                if result["final_score"] >= threshold:
                    self.candidates.save(scan.id, pair["record_a"], pair["record_b"], result)
                    candidates_found += 1

            self.db.commit()
            warning_count = self.warnings.count_for_scan(scan.id)
            return self.scans.update_status(
                scan,
                "COMPLETED",
                total_records=len(df),
                total_candidates=candidates_found,
                warnings_count=warning_count,
            ), len(pairs)
        except Exception:
            self.db.rollback()
            self.scans.update_status(scan, "FAILED", total_records=len(df))
            raise
