"""Apply product migrations, using only ALFA_EVENTS_DATABASE_URL."""
import sys
from pathlib import Path
from alembic.config import Config
from alembic import command
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
if __name__=="__main__":
    command.upgrade(Config(str(ROOT/"backend/alembic.ini")),"head")
    print("Product events migrations applied")
