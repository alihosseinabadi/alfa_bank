from alembic import context
from app.database.base import Base
from app.database.connection import events_engine
import app.models.events

def migrate(connection):
    context.configure(connection=connection,target_metadata=Base.metadata)
    with context.begin_transaction():context.run_migrations()

provided=context.config.attributes.get("connection")
if provided is not None:
    migrate(provided)
else:
    engine=events_engine()
    with engine.connect() as connection:migrate(connection)
