"""fix ybt unknown status to wa

Revision ID: 84458af20925
Revises: e5316a7db1b3
Create Date: 2026-02-19 10:18:52.111872

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '84458af20925'
down_revision = 'e5316a7db1b3'
branch_labels = None
depends_on = None


def upgrade():
    # All YBT UNKNOWN submissions are actually '不完全正确' (WA),
    # since CE submissions are already skipped during sync.
    op.execute(
        "UPDATE submission SET status = 'WA'"
        " WHERE status = 'UNKNOWN'"
        " AND platform_account_id IN"
        " (SELECT id FROM platform_account WHERE platform = 'ybt')"
    )


def downgrade():
    # Cannot reliably revert — we don't know original raw status per row.
    pass
