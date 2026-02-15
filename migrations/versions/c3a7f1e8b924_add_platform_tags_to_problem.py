"""add platform_tags to problem

Revision ID: c3a7f1e8b924
Revises: 45e145c4d5d3
Create Date: 2026-02-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3a7f1e8b924'
down_revision = '45e145c4d5d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('problem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform_tags', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('problem', schema=None) as batch_op:
        batch_op.drop_column('platform_tags')
