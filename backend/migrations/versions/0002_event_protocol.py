"""Persist the protocol version independently from model/feature versions."""
from alembic import op
import sqlalchemy as sa
revision="0002_event_protocol"
down_revision="0001_event_storage"
branch_labels=None
depends_on=None

TABLES=("recommendation_decisions","recommendation_impressions","interaction_events","event_receipts")
def upgrade():
    for name in TABLES:
        op.add_column(name,sa.Column("protocol_version",sa.String(24),nullable=False,server_default="events-v1"))
def downgrade():
    for name in reversed(TABLES):
        op.drop_column(name,"protocol_version")
