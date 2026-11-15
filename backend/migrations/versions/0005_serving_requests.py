"""Persist the public response atomically with its decision."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '0005_serving_requests'
down_revision = '0004_slate_seed'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'serving_requests',
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('event_actors.id'), primary_key=True),
        sa.Column('request_key', UUID(as_uuid=True), primary_key=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('decision_id', UUID(as_uuid=True), sa.ForeignKey('recommendation_decisions.id'), nullable=False),
        sa.Column('response', JSONB, nullable=False),
        sa.UniqueConstraint('decision_id'),
    )


def downgrade():
    op.drop_table('serving_requests')
