"""Bring the database schema up to date; run before the API starts."""
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.database import engine

BASELINE = "b167118927ca"


def main():
    config = Config(os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini"))
    tables = inspect(engine).get_table_names()
    if "users" in tables and "alembic_version" not in tables:
        # built by the old create_all at startup: mark it as the first migration, later ones skip what exists
        command.stamp(config, BASELINE)
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
