"""Add SyncJob model and last_submission_at to PlatformAccount

Revision ID: e5316a7db1b3
Revises: 87387cefced3
Create Date: 2026-02-17 23:45:44.885168

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5316a7db1b3'
down_revision = '87387cefced3'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()

    # Create sync_job table if not already present (db.create_all may have run)
    if 'sync_job' not in existing_tables:
        op.create_table('sync_job',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('job_type', sa.String(length=30), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('platform_account_id', sa.Integer(), nullable=True),
            sa.Column('current_phase', sa.String(length=50), nullable=True),
            sa.Column('progress_current', sa.Integer(), nullable=False),
            sa.Column('progress_total', sa.Integer(), nullable=False),
            sa.Column('stats_json', sa.Text(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('finished_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['platform_account_id'], ['platform_account.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('sync_job', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_sync_job_user_id'), ['user_id'], unique=False)
            batch_op.create_index(batch_op.f('ix_sync_job_platform_account_id'), ['platform_account_id'], unique=False)

    # Add last_submission_at to platform_account if not present
    pa_cols = [c['name'] for c in inspector.get_columns('platform_account')]
    if 'last_submission_at' not in pa_cols:
        with op.batch_alter_table('platform_account', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_submission_at', sa.DateTime(), nullable=True))

    # Backfill last_submission_at from submission table
    op.execute(
        "UPDATE platform_account SET last_submission_at = ("
        "  SELECT MAX(submitted_at) FROM submission"
        "  WHERE submission.platform_account_id = platform_account.id"
        ") WHERE last_submission_at IS NULL"
    )


def downgrade():
    with op.batch_alter_table('platform_account', schema=None) as batch_op:
        batch_op.drop_column('last_submission_at')

    with op.batch_alter_table('sync_job', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sync_job_platform_account_id'))
        batch_op.drop_index(batch_op.f('ix_sync_job_user_id'))

    op.drop_table('sync_job')
