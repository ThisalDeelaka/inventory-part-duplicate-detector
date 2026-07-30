"""Create the characterized current five-table schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_current_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "duplicate_scan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("selected_fields", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_records", sa.Integer(), nullable=True),
        sa.Column("total_candidates", sa.Integer(), nullable=True),
        sa.Column("warnings_count", sa.Integer(), nullable=True),
        sa.Column("rejections_count", sa.Integer(), nullable=True),
        sa.Column("scan_mode", sa.String(length=60), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duplicate_scan")),
    )
    op.create_table(
        "duplicate_candidate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("contract_a", sa.String(length=100), nullable=True),
        sa.Column("part_no_a", sa.String(length=200), nullable=False),
        sa.Column("description_a", sa.Text(), nullable=False),
        sa.Column("contract_b", sa.String(length=100), nullable=True),
        sa.Column("part_no_b", sa.String(length=200), nullable=False),
        sa.Column("description_b", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("confidence_level", sa.String(length=20), nullable=False),
        sa.Column("description_similarity", sa.Float(), nullable=False),
        sa.Column("tfidf_score", sa.Float(), nullable=False),
        sa.Column("fuzzy_score", sa.Float(), nullable=False),
        sa.Column("part_no_similarity", sa.Float(), nullable=False),
        sa.Column("technical_token_score", sa.Float(), nullable=False),
        sa.Column("matched_fields", sa.Text(), nullable=True),
        sa.Column("mismatched_fields", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.String(length=200), nullable=False),
        sa.Column("business_status", sa.String(length=80), nullable=False),
        sa.Column("rule_decision", sa.String(length=50), nullable=False),
        sa.Column("rejection_reason", sa.String(length=120), nullable=True),
        sa.Column("scan_mode", sa.String(length=60), nullable=False),
        sa.Column("critical_mismatches", sa.Text(), nullable=True),
        sa.Column("variant_attributes_a", sa.Text(), nullable=True),
        sa.Column("variant_attributes_b", sa.Text(), nullable=True),
        sa.Column("generic_description_warning", sa.String(length=10), nullable=True),
        sa.Column("application_context_a", sa.Text(), nullable=True),
        sa.Column("application_context_b", sa.Text(), nullable=True),
        sa.Column("application_context_warning", sa.String(length=10), nullable=True),
        sa.Column("normalized_description_a", sa.Text(), nullable=True),
        sa.Column("normalized_description_b", sa.Text(), nullable=True),
        sa.Column("normalized_part_no_a", sa.Text(), nullable=True),
        sa.Column("normalized_part_no_b", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("reviewed_by", sa.String(length=100), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["duplicate_scan.id"],
            name=op.f("fk_duplicate_candidate_scan_id_duplicate_scan"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duplicate_candidate")),
    )
    op.create_index(
        op.f("ix_duplicate_candidate_scan_id"),
        "duplicate_candidate", ["scan_id"], unique=False,
    )
    op.create_table(
        "duplicate_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("user_decision", sa.String(length=30), nullable=False),
        sa.Column("user_comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["duplicate_candidate.id"],
            name=op.f("fk_duplicate_feedback_candidate_id_duplicate_candidate"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duplicate_feedback")),
    )
    op.create_index(
        op.f("ix_duplicate_feedback_candidate_id"),
        "duplicate_feedback", ["candidate_id"], unique=False,
    )
    op.create_table(
        "scan_warning",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("warning_type", sa.String(length=80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("record_reference", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["duplicate_scan.id"],
            name=op.f("fk_scan_warning_scan_id_duplicate_scan"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_warning")),
    )
    op.create_index(
        op.f("ix_scan_warning_scan_id"),
        "scan_warning", ["scan_id"], unique=False,
    )
    op.create_table(
        "rule_exclusion_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_id", sa.Integer(), nullable=False),
        sa.Column("contract_a", sa.String(length=100), nullable=True),
        sa.Column("part_no_a", sa.String(length=200), nullable=False),
        sa.Column("description_a", sa.Text(), nullable=False),
        sa.Column("contract_b", sa.String(length=100), nullable=True),
        sa.Column("part_no_b", sa.String(length=200), nullable=False),
        sa.Column("description_b", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("confidence_level", sa.String(length=20), nullable=False),
        sa.Column("business_status", sa.String(length=80), nullable=False),
        sa.Column("rule_decision", sa.String(length=50), nullable=False),
        sa.Column("rejection_reason", sa.String(length=120), nullable=False),
        sa.Column("critical_mismatches", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["duplicate_scan.id"],
            name=op.f("fk_rule_exclusion_audit_scan_id_duplicate_scan"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rule_exclusion_audit")),
    )
    op.create_index(
        op.f("ix_rule_exclusion_audit_scan_id"),
        "rule_exclusion_audit", ["scan_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_rule_exclusion_audit_scan_id"), table_name="rule_exclusion_audit")
    op.drop_index(op.f("ix_scan_warning_scan_id"), table_name="scan_warning")
    op.drop_index(op.f("ix_duplicate_feedback_candidate_id"), table_name="duplicate_feedback")
    op.drop_index(op.f("ix_duplicate_candidate_scan_id"), table_name="duplicate_candidate")
    op.drop_table("rule_exclusion_audit")
    op.drop_table("scan_warning")
    op.drop_table("duplicate_feedback")
    op.drop_table("duplicate_candidate")
    op.drop_table("duplicate_scan")
