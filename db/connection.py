"""Shared PostgreSQL connection factory.

Lives in db/ so that both db/init_db.py and ingestion/loader.py can use it
without ingestion becoming a dependency of the database layer.
"""

import psycopg2

from db.settings import DatabaseSettings, get_db_settings


def get_db_connection():
    settings: DatabaseSettings = get_db_settings()

    if not all(
        [
            settings.ZEPHYRWERK_RDS_HOST,
            settings.ZEPHYRWERK_RDS_USER,
            settings.ZEPHYRWERK_RDS_PASSWORD,
            settings.ZEPHYRWERK_RDS_DB,
        ]
    ):
        raise RuntimeError("Missing one or more required ZEPHYRWERK_RDS_* environment variables")

    return psycopg2.connect(
        host=settings.ZEPHYRWERK_RDS_HOST,
        port=settings.ZEPHYRWERK_RDS_PORT,
        user=settings.ZEPHYRWERK_RDS_USER,
        password=settings.ZEPHYRWERK_RDS_PASSWORD,
        dbname=settings.ZEPHYRWERK_RDS_DB,
    )