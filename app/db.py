import os
from sqlmodel import SQLModel, create_engine, Session, text
from app.config import settings
from app.models import Card, PriceChartingLink, PriceSnapshot, CollectionEntry


# Create database directory if it doesn't exist
db_dir = os.path.dirname(settings.db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# SQLite connection string with optimizations
sqlite_url = f"sqlite:///{settings.db_path}"

# Create engine with SQLite optimizations
engine = create_engine(
    sqlite_url,
    echo=settings.sql_echo,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    }
)


def init_db():
    """Initialize database tables and set SQLite pragmas."""
    # Set SQLite pragmas for better performance and data integrity
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA cache_size=10000"))
        conn.execute(text("PRAGMA temp_store=memory"))
        conn.commit()
    
    # Create all tables
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session


def get_db_session():
    """Get database session for direct use (not dependency injection)."""
    return Session(engine)


def health_check() -> bool:
    """Check if database is accessible."""
    try:
        with Session(engine) as session:
            session.exec("SELECT 1").first()
        return True
    except Exception:
        return False
