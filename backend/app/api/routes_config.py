from fastapi import APIRouter

from app.core.constants import FIELD_DEFINITIONS

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/fields")
def fields():
    return FIELD_DEFINITIONS
