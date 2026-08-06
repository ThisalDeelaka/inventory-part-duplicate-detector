"""Add the durable dataset registry metadata foundation."""

from alembic import op
import sqlalchemy as sa


revision = "0002_dataset_registry"
down_revision = "0001_current_schema"
branch_labels = None
depends_on = None


_LOWERCASE_SHA256_CHECK = (
    "length({column}) = 64 AND lower({column}) = {column} AND "
    "replace(replace(replace(replace(replace(replace(replace(replace("
    "replace(replace(replace(replace(replace(replace(replace(replace("
    "{column}, '0', ''), '1', ''), '2', ''), '3', ''), '4', ''), "
    "'5', ''), '6', ''), '7', ''), '8', ''), '9', ''), 'a', ''), "
    "'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = ''"
)

_ASCII_WHITESPACE = (" ", "\t", "\n", "\r", "\f", "\v")


def _ascii_whitespace_nonempty_check(column: str) -> str:
    expression = column
    for character in _ASCII_WHITESPACE:
        expression = f"replace({expression}, '{character}', '')"
    return f"length({expression}) > 0"


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            _ascii_whitespace_nonempty_check("name"),
            name=op.f("ck_datasets_name_nonempty"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')",
            name=op.f("ck_datasets_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_index(
        op.f("ix_datasets_status"), "datasets", ["status"], unique=False
    )

    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_media_type", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_record_count", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version_number > 0",
            name=op.f("ck_dataset_versions_version_number_positive"),
        ),
        sa.CheckConstraint(
            "status IN ('REGISTERED', 'STAGED', 'PROFILED', 'READY', 'REJECTED')",
            name=op.f("ck_dataset_versions_status"),
        ),
        sa.CheckConstraint(
            _ascii_whitespace_nonempty_check("source_filename"),
            name=op.f("ck_dataset_versions_source_filename_nonempty"),
        ),
        sa.CheckConstraint(
            _ascii_whitespace_nonempty_check("source_media_type"),
            name=op.f("ck_dataset_versions_source_media_type_nonempty"),
        ),
        sa.CheckConstraint(
            _LOWERCASE_SHA256_CHECK.format(column="source_sha256"),
            name=op.f("ck_dataset_versions_source_sha256_format"),
        ),
        sa.CheckConstraint(
            "source_size_bytes >= 0",
            name=op.f(
                "ck_dataset_versions_source_size_bytes_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "source_record_count IS NULL OR source_record_count >= 0",
            name=op.f(
                "ck_dataset_versions_source_record_count_nonnegative"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_versions_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_dataset_versions")
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "version_number",
            name=op.f(
                "uq_dataset_versions_dataset_id_version_number"
            ),
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "source_sha256",
            "source_size_bytes",
            name=op.f(
                "uq_dataset_versions_dataset_id_source_sha256_"
                "source_size_bytes"
            ),
        ),
    )
    op.create_index(
        op.f("ix_dataset_versions_dataset_id"),
        "dataset_versions",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dataset_versions_status"),
        "dataset_versions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "dataset_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_kind", sa.String(length=40), nullable=False),
        sa.Column("artifact_ordinal", sa.Integer(), nullable=False),
        sa.Column("object_uri", sa.String(length=2048), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "artifact_kind IN ('SOURCE_CSV', 'SCHEMA_PROFILE_JSON', "
            "'CANONICAL_PARQUET')",
            name=op.f("ck_dataset_artifacts_artifact_kind"),
        ),
        sa.CheckConstraint(
            "artifact_ordinal >= 0",
            name=op.f(
                "ck_dataset_artifacts_artifact_ordinal_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            _ascii_whitespace_nonempty_check("object_uri"),
            name=op.f("ck_dataset_artifacts_object_uri_nonempty"),
        ),
        sa.CheckConstraint(
            _LOWERCASE_SHA256_CHECK.format(column="content_sha256"),
            name=op.f("ck_dataset_artifacts_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name=op.f("ck_dataset_artifacts_size_bytes_nonnegative"),
        ),
        sa.CheckConstraint(
            _ascii_whitespace_nonempty_check("media_type"),
            name=op.f("ck_dataset_artifacts_media_type_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            name=op.f(
                "fk_dataset_artifacts_dataset_version_id_dataset_versions"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_dataset_artifacts")
        ),
        sa.UniqueConstraint(
            "dataset_version_id",
            "artifact_kind",
            "artifact_ordinal",
            name=op.f(
                "uq_dataset_artifacts_dataset_version_id_artifact_kind_"
                "artifact_ordinal"
            ),
        ),
        sa.UniqueConstraint(
            "object_uri",
            name=op.f("uq_dataset_artifacts_object_uri"),
        ),
    )
    op.create_index(
        op.f("ix_dataset_artifacts_dataset_version_id"),
        "dataset_artifacts",
        ["dataset_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dataset_artifacts_dataset_version_id_artifact_kind"),
        "dataset_artifacts",
        ["dataset_version_id", "artifact_kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_dataset_artifacts_dataset_version_id_artifact_kind"),
        table_name="dataset_artifacts",
    )
    op.drop_index(
        op.f("ix_dataset_artifacts_dataset_version_id"),
        table_name="dataset_artifacts",
    )
    op.drop_table("dataset_artifacts")
    op.drop_index(
        op.f("ix_dataset_versions_status"),
        table_name="dataset_versions",
    )
    op.drop_index(
        op.f("ix_dataset_versions_dataset_id"),
        table_name="dataset_versions",
    )
    op.drop_table("dataset_versions")
    op.drop_index(
        op.f("ix_datasets_status"), table_name="datasets"
    )
    op.drop_table("datasets")
