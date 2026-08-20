"""
Shared pytest fixtures for the api-service tests.

Uses SQLite in-memory so no running Postgres is needed.
The `get_db` dependency is overridden on the FastAPI app so every
test client request uses the isolated test database.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Patch DATABASE_URL before any api module imports touch it
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AGENT_SERVICE_URL", "http://localhost:8001")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from api.auth import create_access_token  # noqa: E402
from api.database import Base, get_db    # noqa: E402
from api.main import app                 # noqa: E402
from api.models import User              # noqa: E402

SQLITE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once for the entire test session."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db_session():
    """Yield a transactional DB session that is rolled back after each test.

    Also seeds a default User(id=1) so FK constraints on JobApplication.user_id
    are satisfied — mirrors what will happen in Postgres.
    """
    connection = _engine.connect()
    transaction = connection.begin()
    session = _TestingSessionLocal(bind=connection)

    # Seed the default test user expected by all application fixtures
    seed_user = User(id=1, email="test@example.com", hashed_password="hashed")
    session.add(seed_user)
    session.flush()

    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with get_db overridden to use the test session.

    Includes a pre-authenticated Bearer token for the seeded User(id=1)
    so all protected endpoints work without a separate login step.
    """
    def _override_get_db():
        yield db_session

    token = create_access_token(user_id=1, email="test@example.com")
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c
    app.dependency_overrides.clear()