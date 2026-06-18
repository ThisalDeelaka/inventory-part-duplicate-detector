import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.column_semantics import normalize_scan_mode
from app.engine.models import PartRecord
from app.engine.pipeline import run_duplicate_detection_pipeline
from app.engine.result_adapter import decision_results_to_scan_candidates
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

    def run(self, df: pd.DataFrame, scan_name: str, selected_fields: list[str], threshold: float, source_type="CSV", sensitive_mode: bool = True, scan_mode: str = "SAME_SITE_DUPLICATE"):
        scan_mode = normalize_scan_mode(scan_mode)
        validation = validate_dataframe(df, selected_fields, sensitive_mode=sensitive_mode)
        if validation["missing_required_columns"]:
            raise ValueError(f"Missing required columns: {', '.join(validation['missing_required_columns'])}")

        scan = self.scans.create(scan_name, selected_fields, threshold, source_type, scan_mode)
        try:
            for warning in validation["warnings"]:
                self.warnings.save(scan.id, warning)

            usable = df[df["DESCRIPTION"].fillna("").str.strip().ne("")].copy()
            if settings.use_redesigned_engine:
                candidates_found, pair_count = self._run_redesigned(scan.id, usable, selected_fields, threshold, scan_mode)
            else:
                candidates_found, pair_count = self._run_legacy(scan.id, usable, selected_fields, threshold, scan_mode, validation)

            self.db.commit()
            warning_count = self.warnings.count_for_scan(scan.id)
            return self.scans.update_status(
                scan,
                "COMPLETED",
                total_records=len(df),
                total_candidates=candidates_found,
                warnings_count=warning_count,
            ), pair_count
        except Exception:
            self.db.rollback()
            self.scans.update_status(scan, "FAILED", total_records=len(df))
            raise

    def _run_legacy(self, scan_id: int, usable: pd.DataFrame, selected_fields: list[str], threshold: float, scan_mode: str, validation: dict) -> tuple[int, int]:
        pairs = generate_candidate_pairs(usable, selected_fields)
        existing_warnings = {(w["warning_type"], w["message"]) for w in validation["warnings"]}
        generated_warnings = {(w["warning_type"], w["message"]) for pair in pairs for w in pair["warnings"]}
        for warning_type, message in generated_warnings - existing_warnings:
            self.warnings.save(scan_id, {"warning_type": warning_type, "message": message})

        candidates_found = 0
        for pair in pairs:
            result = score_candidate(pair["record_a"], pair["record_b"], selected_fields, scan_mode)
            if result["final_score"] >= threshold:
                self.candidates.save(scan_id, pair["record_a"], pair["record_b"], result)
                candidates_found += 1
        return candidates_found, len(pairs)

    def _run_redesigned(self, scan_id: int, usable: pd.DataFrame, selected_fields: list[str], threshold: float, scan_mode: str) -> tuple[int, int]:
        records = [
            PartRecord(
                part_no="" if row.get("PART_NO") is None else str(row.get("PART_NO")),
                description="" if row.get("DESCRIPTION") is None else str(row.get("DESCRIPTION")),
                contract=None if row.get("CONTRACT") is None else str(row.get("CONTRACT")),
                raw=row,
            )
            for row in usable.to_dict("records")
        ]
        cross_site = scan_mode == "CROSS_SITE_STANDARDIZATION"
        decisions = run_duplicate_detection_pipeline(records, selected_fields, cross_site=cross_site)
        adapted_results = decision_results_to_scan_candidates(decisions)
        pairs = generate_candidate_pairs(records, selected_fields, cross_site=cross_site)

        candidates_found = 0
        for pair, result in zip(pairs, adapted_results, strict=False):
            if result["final_score"] >= threshold:
                self.candidates.save(scan_id, pair.record_a.raw, pair.record_b.raw, result)
                candidates_found += 1
        return candidates_found, len(pairs)
