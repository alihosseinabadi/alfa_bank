"""Record clicks that occur before any confirmed impression without reward."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0007_unattributed_clicks'
down_revision = '0006_reward_projection'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('unattributed_clicks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('event_actors.id'), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', UUID(as_uuid=True), sa.ForeignKey('recommendation_items.id'), nullable=False),
        sa.Column('event_key', UUID(as_uuid=True), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('simulated', sa.Boolean, nullable=False),
        sa.Column('client_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('actor_id', 'event_key'))
    op.create_index('ix_unattributed_clicks_actor_id', 'unattributed_clicks', ['actor_id'])


def downgrade():
    op.drop_index('ix_unattributed_clicks_actor_id', table_name='unattributed_clicks')
    op.drop_table('unattributed_clicks')
