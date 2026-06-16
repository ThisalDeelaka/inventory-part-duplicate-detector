import random
import time

import pandas as pd

from app.services.scan_service import run_scan

BASE = [
    ("MCB30A", "MCB30A", "Miniature Circuit Breaker 30A", "EA", "ELECTRICAL"),
    ("COCO-1", "Decicated Coconut type 1", "Desiccated Coconut type 1", "KG", "FOOD"),
    ("GOF-1", "Generator Oil Filter", "Generator Oil Filter", "EA", "FILTER"),
    ("GAF-1", "Generator Air Filter", "Generator Air Filter", "EA", "FILTER"),
    ("BOLT-10", "Bolt 10MM", "Bolt 10 mm", "EA", "FASTENER"),
    ("BOLT-12", "Bolt 12MM", "Bolt 12 mm", "EA", "FASTENER"),
    ("SSP-1", "Stainless Steel Pipe", "SS Pipe", "M", "PIPE"),
]


def generate_synthetic_dataframe(record_count, duplicate_rate, variation_rate):
    rows = []
    for i in range(record_count):
        # Synthetic demo data only; this randomness is not security-sensitive.
        part, canonical, variant, unit, commodity = random.choice(BASE)  # nosec B311
        use_variant = random.random() < variation_rate or random.random() < duplicate_rate  # nosec B311
        rows.append({"CONTRACT": random.choice(["SITE-A", "SITE-B"]), "PART_NO": f"{part}-{i:05d}", "DESCRIPTION": variant if use_variant else canonical, "TYPE_CODE": "P", "UNIT_MEAS": unit, "PRIME_COMMODITY": commodity, "SECOND_COMMODITY": "", "HAZARD_CODE": "", "ACCOUNTING_GROUP": "INV", "PART_PRODUCT_CODE": commodity, "PART_PRODUCT_FAMILY": commodity, "PRODUCT_CATEGORY_ID": commodity, "HSN_SAC_CODE": ""})  # nosec B311
    return pd.DataFrame(rows)


def run_load_test(db, request):
    df = generate_synthetic_dataframe(request.record_count, request.duplicate_rate, request.variation_rate)
    started = time.perf_counter()
    scan, pair_count = run_scan(db, df, f"Synthetic load test {request.record_count}", ["CONTRACT", "UNIT_MEAS", "PRIME_COMMODITY"], request.threshold, "SYNTHETIC")
    return {"scan_id": scan.id, "record_count": request.record_count, "candidate_pair_count": pair_count, "processing_time_seconds": round(time.perf_counter() - started, 3), "candidates_found": scan.total_candidates, "warnings_count": scan.warnings_count}
