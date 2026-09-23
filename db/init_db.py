"""Create the raw/staging/analytics schemas and the raw tables.

Locally the Postgres container applies db/init.sql automatically on first
start. RDS has no such mechanism, so this module applies the same file. It is
safe to run repeatedly: every statement in init.sql uses IF NOT EXISTS.
"""

import logging
from pathlib import Path

from db.connection import get_db_connection

logger = logging.getLogger(__name__)

# Resolved from this file's location rather than the working directory, so the
# path holds regardless of where the process is started from.
INIT_SQL_PATH = Path(__file__).resolve().parent / "init.sql"


def init_db() -> None:
    """Apply init.sql to the configured database."""
    sql = INIT_SQL_PATH.read_text()
    logger.info(f"Applying schema from {INIT_SQL_PATH}")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        logger.info("Schema applied successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()