"""Audit the version and reason for reward projection revisions."""
from alembic import op
import sqlalchemy as sa

revision = '0006_reward_projection'
down_revision = '0005_serving_requests'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reward_revisions', sa.Column('projection_version', sa.String(40),
                  nullable=False, server_default='legacy-v1'))
    op.add_column('reward_revisions', sa.Column('reason', sa.String(80), nullable=True))


def downgrade():
    op.drop_column('reward_revisions', 'reason')
    op.drop_column('reward_revisions', 'projection_version')
