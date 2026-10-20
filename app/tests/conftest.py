import os
import tempfile

# Loaded by pytest before any test module, so app.config sees these values
os.environ.setdefault("TESTING", "True")
os.environ.setdefault("SECRET_KEY", "test-secret-key-only-used-by-the-test-suite")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-for-testing")
os.environ.setdefault("UPLOAD_DIRECTORY", tempfile.mkdtemp(prefix="arosaje-photos-"))

import pytest


@pytest.fixture(autouse=True, scope="module")
def fresh_database(request):
    """Every module shares the same SQLite file: give each one fresh tables and its own get_db override."""
    from app.database import Base, get_db
    from app.main import app

    engine = request.module.engine
    engine.dispose()  # drop connections to a file a previous module removed
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = request.module.override_get_db
    yield
