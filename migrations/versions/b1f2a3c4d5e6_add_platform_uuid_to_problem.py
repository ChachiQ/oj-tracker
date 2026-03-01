"""add platform_uuid to problem

Revision ID: b1f2a3c4d5e6
Revises: 9b5cd53165d4
Create Date: 2026-03-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1f2a3c4d5e6'
down_revision = '9b5cd53165d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('problem', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform_uuid', sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table('problem', schema=None) as batch_op:
        batch_op.drop_column('platform_uuid')
