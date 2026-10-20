import os

# Setup test environment
os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings

TEST_DATABASE_URL = "sqlite:///./test_a_rosa_je.db"
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)



def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_preflight_options():
    headers = {"Origin": "http://localhost:5000", "Access-Control-Request-Method": "POST"}
    response = client.options("/plants/", headers=headers)
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5000"
    assert "Access-Control-Allow-Methods" in response.headers


def test_preflight_rejects_unknown_origin():
    headers = {"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"}
    response = client.options("/plants/", headers=headers)
    assert "Access-Control-Allow-Origin" not in response.headers


def test_static_photo_serving():
    filename = "test_main_photo.txt"
    path = os.path.join(settings.UPLOAD_DIRECTORY, filename)
    with open(path, "w") as f:
        f.write("hello")

    response = client.get(f"/photos/{filename}")
    assert response.status_code == 200
    assert response.text == "hello"

    os.remove(path)
