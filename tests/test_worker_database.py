from backend.app.db.base import Base
from backend.app.db.session import create_database


def test_worker_database_session_registers_all_foreign_key_models() -> None:
    """The standalone Temporal worker must not depend on FastAPI imports for mappings."""
    create_database("sqlite://")
    # Sorting metadata resolves ReadingSession.book_id -> books.id.
    assert {table.name for table in Base.metadata.sorted_tables} >= {"books", "reading_sessions"}
