"""Migrations for the separate legacy product database only."""
from alembic import context
from app.database import Base
from app.database.connection import product_engine
import app.models


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


provided = context.config.attributes.get("connection")
if provided is not None:
    migrate(provided)
else:
    with product_engine().connect() as connection:
        migrate(connection)
