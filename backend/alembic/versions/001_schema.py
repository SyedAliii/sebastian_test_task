"""Create the moderation tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("verified", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.CheckConstraint("role in ('admin', 'member')", name="users_role_check"),
    )
    op.create_table(
        "media",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("submitted_by", sa.Text(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("frames", postgresql.JSONB(), nullable=False),
        sa.Column("frame_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("type in ('image', 'video')", name="media_type_check"),
        sa.CheckConstraint("source in ('upload', 'generation')", name="media_source_check"),
        sa.CheckConstraint("status in ('pending', 'published', 'held', 'blocked')", name="media_status_check"),
        sa.CheckConstraint(
            "hold_reason is null or hold_reason in ('review', 'no_decision')",
            name="media_hold_reason_value_check",
        ),
        sa.CheckConstraint("frame_count >= 1", name="media_frame_count_check"),
        sa.CheckConstraint(
            "(status = 'held' and hold_reason is not null) or (status <> 'held' and hold_reason is null)",
            name="media_held_reason_check",
        ),
        sa.CheckConstraint(
            "(source = 'generation' and prompt is not null) or (source = 'upload' and prompt is null)",
            name="media_prompt_check",
        ),
        sa.CheckConstraint(
            "type <> 'image' or frame_count = 1",
            name="media_image_frame_count_check",
        ),
    )
    op.create_index("media_workspace_status", "media", ["workspace_id", "status"])
    op.create_index(
        "media_review_queue",
        "media",
        ["workspace_id"],
        postgresql_where=sa.text("status = 'held' and hold_reason = 'review'"),
    )
    op.create_table(
        "screening_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("decided_by", sa.Text(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source in ('provider', 'admin')", name="screening_decisions_source_check"),
        sa.CheckConstraint(
            "outcome in ('published', 'held', 'blocked')",
            name="screening_decisions_outcome_check",
        ),
    )
    op.create_index(
        "one_provider_decision",
        "screening_decisions",
        ["media_id"],
        unique=True,
        postgresql_where=sa.text("source = 'provider'"),
    )
    op.create_index(
        "one_admin_decision",
        "screening_decisions",
        ["media_id"],
        unique=True,
        postgresql_where=sa.text("source = 'admin'"),
    )
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id"), nullable=False, unique=True),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("attempts_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_enqueue", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state in ('queued', 'running', 'awaiting_callback', 'retry_wait', 'parked', 'succeeded')",
            name="jobs_state_check",
        ),
    )
    op.create_index("jobs_state_available_at", "jobs", ["state", "available_at"])
    op.create_index(
        "jobs_needs_enqueue",
        "jobs",
        ["id"],
        postgresql_where=sa.text("needs_enqueue"),
    )
    op.create_table(
        "attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id"), nullable=False),
        sa.Column("workspace_id", sa.Text(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.UniqueConstraint("job_id", "n", name="attempts_job_n_key"),
    )


def downgrade() -> None:
    op.drop_table("attempts")
    op.drop_table("jobs")
    op.drop_table("screening_decisions")
    op.drop_table("media")
    op.drop_table("users")
    op.drop_table("workspaces")
