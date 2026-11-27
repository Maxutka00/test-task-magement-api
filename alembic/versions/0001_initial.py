from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

invitation_status_enum = postgresql.ENUM(
    "pending",
    "accepted",
    "revoked",
    "expired",
    name="invitation_status",
    create_type=False,
)
task_status_enum = postgresql.ENUM(
    "backlog",
    "in_progress",
    "review",
    "done",
    "cancelled",
    name="task_status",
    create_type=False,
)
task_priority_enum = postgresql.ENUM(
    "high",
    "medium",
    "low",
    name="task_priority",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    invitation_status_enum.create(bind, checkfirst=True)
    task_status_enum.create(bind, checkfirst=True)
    task_priority_enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], unique=False)
    op.create_index("ix_refresh_tokens_token_jti", "refresh_tokens", ["token_jti"], unique=True)

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("join_code", sa.String(length=6), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_teams_owner_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
    )
    op.create_index("ix_teams_join_code", "teams", ["join_code"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("level >= 0 AND level <= 100", name="ck_roles_role_level_range"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_roles_team_id_teams", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("team_id", "name", name="uq_roles_team_id_name"),
    )
    op.create_index("ix_roles_team_id", "roles", ["team_id"], unique=False)

    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_role_permissions_role_id_roles", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission", name="pk_role_permissions"),
    )

    op.create_table(
        "team_members",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_team_members_role_id_roles", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_team_members_team_id_teams", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_team_members_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("team_id", "user_id", name="pk_team_members"),
    )
    op.create_index("ix_team_members_role_id", "team_members", ["role_id"], unique=False)
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"], unique=False)

    op.create_table(
        "team_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", invitation_status_enum, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], name="fk_team_invitations_invited_by_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_user_id"], ["users.id"], name="fk_team_invitations_invited_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_team_invitations_team_id_teams", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_team_invitations"),
    )
    op.create_index("ix_team_invitations_team_id", "team_invitations", ["team_id"], unique=False)
    op.create_index("ix_team_invitations_invited_user_id", "team_invitations", ["invited_user_id"], unique=False)
    op.create_index(
        "ix_team_invitations_pending_unique",
        "team_invitations",
        ["team_id", "invited_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", task_status_enum, nullable=False),
        sa.Column("priority", task_priority_enum, nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], name="fk_tasks_assignee_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_tasks_author_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_tasks_team_id_teams", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
    )
    op.create_index("ix_tasks_team_id", "tasks", ["team_id"], unique=False)
    op.create_index("ix_tasks_author_id", "tasks", ["author_id"], unique=False)
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"], unique=False)
    op.create_index("ix_tasks_team_status", "tasks", ["team_id", "status"], unique=False)
    op.create_index("ix_tasks_team_priority", "tasks", ["team_id", "priority"], unique=False)
    op.create_index("ix_tasks_team_assignee_status", "tasks", ["team_id", "assignee_id", "status"], unique=False)
    op.create_index("ix_tasks_deadline", "tasks", ["deadline"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_comments_author_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["comments.id"], name="fk_comments_parent_id_comments", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_comments_task_id_tasks", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_comments"),
    )
    op.create_index("ix_comments_task_id", "comments", ["task_id"], unique=False)
    op.create_index("ix_comments_author_id", "comments", ["author_id"], unique=False)
    op.create_index("ix_comments_parent_id", "comments", ["parent_id"], unique=False)
    op.create_index("ix_comments_task_parent_created", "comments", ["task_id", "parent_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("comments")
    op.drop_table("tasks")
    op.drop_table("team_invitations")
    op.drop_table("team_members")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("teams")
    op.drop_table("refresh_tokens")
    op.drop_table("users")

    bind = op.get_bind()
    task_priority_enum.drop(bind, checkfirst=True)
    task_status_enum.drop(bind, checkfirst=True)
    invitation_status_enum.drop(bind, checkfirst=True)
