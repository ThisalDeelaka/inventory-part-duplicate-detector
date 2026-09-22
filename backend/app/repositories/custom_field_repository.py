import json

from sqlalchemy.orm import Session

from app.db.models import CustomField


class CustomFieldRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self):
        return self.db.query(CustomField).order_by(CustomField.display_label).all()

    def get_by_key(self, field_key):
        return self.db.query(CustomField).filter(CustomField.field_key == field_key).first()

    def create(self, field_key, display_label, mode, initial_alias=None):
        aliases = [initial_alias] if initial_alias else []
        field = CustomField(
            field_key=field_key,
            display_label=display_label,
            mode=mode,
            aliases=json.dumps(aliases),
        )
        self.db.add(field)
        self.db.commit()
        self.db.refresh(field)
        return field

    def delete(self, field_id):
        field = self.db.query(CustomField).filter(CustomField.id == field_id).first()
        if field:
            self.db.delete(field)
            self.db.commit()
        return field

    def record_alias(self, field, header):
        aliases = json.loads(field.aliases or "[]")
        if header not in aliases:
            aliases.append(header)
            field.aliases = json.dumps(aliases)
            self.db.commit()
            self.db.refresh(field)
        return field
