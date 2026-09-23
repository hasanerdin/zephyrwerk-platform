from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.settings import get_db_settings

settings = get_db_settings()
engine = create_engine(
    settings.database_url,
    echo=False,         # Disable SQLAlchemy logging for cleaner output
    pool_pre_ping=True, # Enable connection pool pre-ping to check if connections are alive
    pool_recycle=3600,  # Recycle connections every hour
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)