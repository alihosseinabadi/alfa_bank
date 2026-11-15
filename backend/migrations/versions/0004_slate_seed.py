"""Reserve an independent random seed before selecting a slate."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = '0004_slate_seed'
down_revision = '0003_reward_ledger'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('slate_random_seeds',
        sa.Column('actor_id',UUID(as_uuid=True),sa.ForeignKey('event_actors.id'),primary_key=True),
        sa.Column('request_key',UUID(as_uuid=True),primary_key=True),
        sa.Column('seed',sa.BigInteger,nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.CheckConstraint('seed >= 0'))

def downgrade():
    op.drop_table('slate_random_seeds')
