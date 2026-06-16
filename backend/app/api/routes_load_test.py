import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.schemas import LoadTestRequest
from app.services.load_test_service import generate_synthetic_dataframe, run_load_test

router = APIRouter(prefix="/api/load-test", tags=["load-test"])


@router.post("/generate")
def generate(payload: LoadTestRequest):
    df = generate_synthetic_dataframe(payload.record_count, payload.duplicate_rate, payload.variation_rate)
    return Response(df.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="generated_load_test_data.csv"'})


@router.post("/run")
def run(payload: LoadTestRequest, db: Session = Depends(get_db)):
    return run_load_test(db, payload)
