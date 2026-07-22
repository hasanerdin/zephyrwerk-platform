from collections.abc import Generator

from db.database import engine


def get_db() -> Generator:
    """
    Dependency function to provide a database session.

    Yields:
        Generator: A generator that yields a database session.
    """
    with engine.connect() as conn:
        yield conn