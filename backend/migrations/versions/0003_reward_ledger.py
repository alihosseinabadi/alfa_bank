"""Add durable shared learner observations and revision ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = '0003_reward_ledger'
down_revision = '0002_event_protocol'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('reward_observations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('impression_id', UUID(as_uuid=True), sa.ForeignKey('recommendation_impressions.id'), nullable=False),
        sa.Column('model_key', sa.String(80), nullable=False),
        sa.Column('registry_hash', sa.String(64), nullable=False),
        sa.Column('policy_hash', sa.String(64), nullable=False),
        sa.Column('features', JSONB, nullable=False),
        sa.Column('reward', sa.Float, nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('model_key','impression_id'),
        sa.CheckConstraint('reward >= 0 AND reward <= 1'), sa.CheckConstraint('revision >= 1'))
    op.create_table('reward_revisions',
        sa.Column('observation_id', UUID(as_uuid=True), sa.ForeignKey('reward_observations.id'), primary_key=True),
        sa.Column('revision', sa.Integer, primary_key=True),
        sa.Column('old_reward', sa.Float), sa.Column('new_reward', sa.Float, nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('revision >= 1'), sa.CheckConstraint('new_reward >= 0 AND new_reward <= 1'),
        sa.CheckConstraint('old_reward IS NULL OR (old_reward >= 0 AND old_reward <= 1)'))

def downgrade():
    op.drop_table('reward_revisions')
    op.drop_table('reward_observations')
