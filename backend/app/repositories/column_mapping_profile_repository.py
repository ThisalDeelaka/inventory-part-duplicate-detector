import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import ColumnMappingProfile


class ColumnMappingProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_signature(self, header_signature: str):
        return (
            self.db.query(ColumnMappingProfile)
            .filter(ColumnMappingProfile.header_signature == header_signature, ColumnMappingProfile.is_active == "true")
            .first()
        )

    def upsert(self, profile_name: str, header_signature: str, source_columns: list[str], column_mapping: list[dict]):
        profile = self.get_by_signature(header_signature)
        now = datetime.now(timezone.utc)
        payload_source_columns = json.dumps(source_columns)
        payload_column_mapping = json.dumps(column_mapping)

        if profile is None:
            profile = ColumnMappingProfile(
                profile_name=profile_name,
                header_signature=header_signature,
                source_columns=payload_source_columns,
                column_mapping=payload_column_mapping,
                updated_at=now,
                last_used_at=now,
                usage_count=1,
                is_active="true",
            )
            self.db.add(profile)
        else:
            profile.profile_name = profile_name
            profile.source_columns = payload_source_columns
            profile.column_mapping = payload_column_mapping
            profile.updated_at = now
            profile.last_used_at = now
            profile.usage_count = int(profile.usage_count or 0) + 1
            profile.is_active = "true"

        self.db.commit()
        self.db.refresh(profile)
        return profile

    def touch(self, profile: ColumnMappingProfile):
        profile.last_used_at = datetime.now(timezone.utc)
        profile.usage_count = int(profile.usage_count or 0) + 1
        self.db.commit()
        self.db.refresh(profile)
        return profile
