import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import FIELD_DEFINITIONS
from app.db.database import get_db
from app.repositories.custom_field_repository import CustomFieldRepository
from app.schemas.schemas import CustomFieldCreate, CustomFieldResponse
from app.services.validation_service import normalize_column_name

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/fields")
def fields():
    return FIELD_DEFINITIONS


def _custom_field_json(field):
    return {
        "id": field.id,
        "field_key": field.field_key,
        "display_label": field.display_label,
        "mode": field.mode,
        "aliases": json.loads(field.aliases or "[]"),
        "created_at": field.created_at,
        "updated_at": field.updated_at,
    }


@router.get("/custom-fields", response_model=list[CustomFieldResponse])
def list_custom_fields(db: Session = Depends(get_db)):
    return [_custom_field_json(field) for field in CustomFieldRepository(db).list_all()]


@router.post("/custom-fields", response_model=CustomFieldResponse)
def create_custom_field(payload: CustomFieldCreate, db: Session = Depends(get_db)):
    field_key = normalize_column_name(payload.display_label)
    if not field_key:
        raise HTTPException(400, "display_label must contain at least one alphanumeric character")
    canonical_keys = {item["field"] for item in FIELD_DEFINITIONS}
    if field_key in canonical_keys:
        raise HTTPException(409, f"{field_key} is already a built-in field")
    repo = CustomFieldRepository(db)
    if repo.get_by_key(field_key):
        raise HTTPException(409, f"A custom field named {field_key} already exists")
    initial_alias = normalize_column_name(payload.source_column) if payload.source_column else None
    try:
        field = repo.create(field_key, payload.display_label.strip(), payload.mode, initial_alias)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A custom field named {field_key} already exists") from None
    return _custom_field_json(field)


@router.delete("/custom-fields/{field_id}")
def delete_custom_field(field_id: int, db: Session = Depends(get_db)):
    field = CustomFieldRepository(db).delete(field_id)
    if not field:
        raise HTTPException(404, "Custom field not found")
    return {"deleted": True}
