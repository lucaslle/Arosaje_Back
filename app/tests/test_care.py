import os

os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

import io
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import settings
from app.database import Base, get_db
from app.main import app

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

START = date.today() + timedelta(days=1)
END = date.today() + timedelta(days=8)
_counter = iter(range(1000))


def register(is_botanist=False, email=None):
    n = next(_counter)
    email = email or f"member{n}@example.com"
    body = {"email": email, "username": f"member{n}", "phone": f"06{n:08d}", "password": "password123", "is_botanist": is_botanist}
    assert client.post("/users/", json=body).status_code == 200
    token = client.post("/token", data={"username": email, "password": "password123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers, client.get("/users/me/", headers=headers).json()["id"]


def create_plant(headers, name="Monstera", location="Lyon"):
    files = {"photo": ("p.jpg", io.BytesIO(b"img"), "image/jpeg")}
    response = client.post("/plants/", params={"name": name, "location": location}, files=files, headers=headers)
    assert response.status_code == 200
    return response.json()["id"]


def request_care(headers, plant_id, start=START, end=END):
    return client.put(f"/plants/{plant_id}", params={"care_requested": True, "care_start": str(start), "care_end": str(end)}, headers=headers)


@pytest.fixture
def admin(monkeypatch):
    headers, user_id = register(email=f"admin{next(_counter)}@example.com")
    monkeypatch.setattr(settings, "ADMIN_EMAILS", [client.get("/users/me/", headers=headers).json()["email"]])
    return headers


def test_care_request_needs_valid_dates():
    owner, _ = register()
    plant = create_plant(owner)
    assert client.put(f"/plants/{plant}", params={"care_requested": True}, headers=owner).status_code == 400
    assert request_care(owner, plant, START, START - timedelta(days=1)).status_code == 400
    assert request_care(owner, plant, date.today() - timedelta(days=9), date.today() - timedelta(days=2)).status_code == 400

    response = request_care(owner, plant)
    assert response.status_code == 200
    assert response.json()["care_start"] == str(START) and response.json()["care_end"] == str(END)


def test_full_care_flow():
    owner, _ = register()
    sitter, sitter_id = register()
    other, _ = register()
    outsider, _ = register()
    plant = create_plant(owner)

    assert client.post(f"/plants/{plant}/care-offers", headers=sitter).status_code == 409  # no request yet
    request_care(owner, plant)
    offer = client.post(f"/plants/{plant}/care-offers", headers=sitter).json()
    other_offer = client.post(f"/plants/{plant}/care-offers", headers=other).json()
    assert client.post(f"/plants/{plant}/care-offers", headers=sitter).status_code == 409  # already offered
    assert client.post(f"/plants/{plant}/care-offers", headers=owner).status_code == 400  # own plant

    offers = client.get(f"/plants/{plant}/care-offers", headers=owner).json()
    assert {o["id"] for o in offers} == {offer["id"], other_offer["id"]}
    assert offers[0]["sitter"]["rating_count"] == 0
    assert client.get(f"/plants/{plant}/care-offers", headers=sitter).status_code == 403

    # private conversation between the owner and this sitter only
    assert client.post(f"/care-offers/{offer['id']}/messages", json={"text": "Bonjour !"}, headers=sitter).status_code == 201
    assert client.post(f"/care-offers/{offer['id']}/messages", json={"text": "Bienvenue"}, headers=owner).status_code == 201
    assert client.get(f"/care-offers/{offer['id']}/messages", headers=outsider).status_code == 403
    assert [m["text"] for m in client.get(f"/care-offers/{offer['id']}/messages", headers=owner).json()] == ["Bonjour !", "Bienvenue"]

    accepted = client.put(f"/care-offers/{offer['id']}/accept", headers=owner)
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert client.put(f"/care-offers/{other_offer['id']}/accept", headers=owner).status_code == 409
    mine = {o["id"]: o["status"] for o in client.get("/care-offers/mine", headers=other).json()}
    assert mine[other_offer["id"]] == "refused"

    # care journal: only the current sitter writes, owner and sitter read
    photo = {"photo": ("log.jpg", io.BytesIO(b"img"), "image/jpeg")}
    assert client.post(f"/plants/{plant}/care-logs", data={"text": "Arrosée"}, files=photo, headers=sitter).status_code == 201
    assert client.post(f"/plants/{plant}/care-logs", data={"text": "Intrus"}, headers=outsider).status_code == 403
    logs = client.get(f"/plants/{plant}/care-logs", headers=owner).json()
    assert logs[0]["text"] == "Arrosée" and logs[0]["photo_url"].startswith("photos/")
    assert client.get(f"/plants/{plant}/care-logs", headers=outsider).status_code == 403

    assert client.post(f"/care-offers/{offer['id']}/review", json={"rating": 5}, headers=owner).status_code == 409  # not finished
    assert client.put(f"/plants/{plant}/end-care", headers=owner).status_code == 200
    assert client.post(f"/care-offers/{offer['id']}/review", json={"rating": 6}, headers=owner).status_code == 422
    assert client.post(f"/care-offers/{offer['id']}/review", json={"rating": 5, "comment": "Parfait"}, headers=sitter).status_code == 403
    assert client.post(f"/care-offers/{offer['id']}/review", json={"rating": 5, "comment": "Parfait"}, headers=owner).status_code == 201
    assert client.post(f"/care-offers/{offer['id']}/review", json={"rating": 4}, headers=owner).status_code == 409

    profile = client.get(f"/users/{sitter_id}/profile", headers=outsider).json()
    assert profile["rating_average"] == 5 and profile["rating_count"] == 1 and profile["completed_cares"] == 1
    assert client.post(f"/care-offers/{offer['id']}/messages", json={"text": "Merci"}, headers=sitter).status_code == 409


def test_sitter_can_withdraw_pending_offer():
    owner, _ = register()
    sitter, _ = register()
    plant = create_plant(owner)
    request_care(owner, plant)
    offer = client.post(f"/plants/{plant}/care-offers", headers=sitter).json()
    assert client.delete(f"/care-offers/{offer['id']}", headers=owner).status_code == 403
    assert client.delete(f"/care-offers/{offer['id']}", headers=sitter).status_code == 204
    assert client.get(f"/plants/{plant}/care-offers", headers=owner).json() == []


def test_finished_care_and_expired_requests_are_closed():
    owner, _ = register()
    sitter, _ = register()
    waiting_plant, cared_plant = create_plant(owner, "Waiting"), create_plant(owner, "Cared")
    request_care(owner, waiting_plant)
    request_care(owner, cared_plant)
    pending = client.post(f"/plants/{waiting_plant}/care-offers", headers=sitter).json()
    accepted = client.post(f"/plants/{cared_plant}/care-offers", headers=sitter).json()
    client.put(f"/care-offers/{accepted['id']}/accept", headers=owner)

    db = TestingSessionLocal()
    db.query(models.Plant).filter(models.Plant.id.in_([waiting_plant, cared_plant])).update(
        {"care_end": date.today() - timedelta(days=1)}, synchronize_session=False
    )
    db.commit()
    db.close()

    plants = {p["id"]: p for p in client.get("/my_plants/", headers=owner).json()}
    assert plants[waiting_plant]["care_requested"] is False
    assert plants[cared_plant]["in_care_id"] is None
    statuses = {o["id"]: o["status"] for o in client.get("/care-offers/mine", headers=sitter).json()}
    assert statuses == {accepted["id"]: "completed"}  # the expired pending offer is cancelled, so hidden
    assert pending["id"] not in statuses


def test_favorites():
    owner, _ = register()
    fan, _ = register()
    plant = create_plant(owner)
    assert client.put(f"/plants/{plant}/favorite", headers=fan).status_code == 204
    assert client.put(f"/plants/{plant}/favorite", headers=fan).status_code == 204  # idempotent
    assert [p["id"] for p in client.get("/favorites/", headers=fan).json()] == [plant]
    assert client.delete(f"/plants/{plant}/favorite", headers=fan).status_code == 204
    assert client.get("/favorites/", headers=fan).json() == []


def test_change_password():
    headers, _ = register()
    email = client.get("/users/me/", headers=headers).json()["email"]
    wrong = {"current_password": "nope", "new_password": "newpassword1"}
    assert client.put("/users/me/password", json=wrong, headers=headers).status_code == 400
    assert client.put("/users/me/password", json={"current_password": "password123", "new_password": "short"}, headers=headers).status_code == 422
    assert client.put("/users/me/password", json={"current_password": "password123", "new_password": "newpassword1"}, headers=headers).status_code == 204
    assert client.post("/token", data={"username": email, "password": "password123"}).status_code == 401
    assert client.post("/token", data={"username": email, "password": "newpassword1"}).status_code == 200


def test_botanist_verification_and_advice(admin):
    owner, _ = register()
    botanist, botanist_id = register(is_botanist=True)
    refused, refused_id = register(is_botanist=True)
    plant = create_plant(owner)

    # a claimed but unverified botanist is not shown as one and cannot see the questions
    assert client.get("/advice-requests/", headers=botanist).status_code == 403
    assert client.get("/admin/botanist-requests", headers=owner).status_code == 403
    pending_ids = {u["id"] for u in client.get("/admin/botanist-requests", headers=admin).json()}
    assert {botanist_id, refused_id} <= pending_ids

    assert client.put(f"/admin/users/{botanist_id}/botanist", json={"verified": True}, headers=admin).status_code == 200
    assert client.put(f"/admin/users/{refused_id}/botanist", json={"verified": False}, headers=admin).status_code == 200
    assert client.get("/users/me/", headers=refused).json()["is_botanist"] is False
    assert client.get("/users/me/", headers=botanist).json()["botanist_verified"] is True

    assert client.post(f"/plants/{plant}/advice-requests", json={"question": "Feuilles jaunes ?"}, headers=botanist).status_code == 403
    advice = client.post(f"/plants/{plant}/advice-requests", json={"question": "Feuilles jaunes ?"}, headers=owner).json()
    assert client.post(f"/plants/{plant}/advice-requests", json={"question": "Encore ?"}, headers=owner).status_code == 409
    assert advice["id"] in [a["id"] for a in client.get("/advice-requests/", headers=botanist).json()]

    client.post("/comments/", params={"plant_id": plant, "comment": "Trop d'eau."}, headers=botanist)
    assert client.get(f"/plants/{plant}/advice-requests", headers=owner).json()[0]["status"] == "answered"
    comment = client.get(f"/plants/{plant}/comments/", headers=owner).json()[0]
    assert comment["user"]["is_botanist"] is True


def test_search_and_pagination():
    owner, _ = register()
    viewer, _ = register()
    for name in ("Ficus Alpha", "Ficus Beta", "Cactus Gamma"):
        create_plant(owner, name, "Paris")
    ficus = [p["name"] for p in client.get("/all_plants/", params={"q": "ficus"}, headers=viewer).json()]
    assert sorted(ficus) == ["Ficus Alpha", "Ficus Beta"]
    first = client.get("/all_plants/", params={"limit": 1, "q": "Paris"}, headers=viewer).json()
    second = client.get("/all_plants/", params={"limit": 1, "offset": 1, "q": "Paris"}, headers=viewer).json()
    assert len(first) == 1 and len(second) == 1 and first[0]["id"] != second[0]["id"]
    assert client.get("/all_plants/", params={"limit": 500}, headers=viewer).status_code == 422


def test_personal_data_export():
    headers, _ = register()
    create_plant(headers)
    response = client.get("/users/me/export", headers=headers)
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["profile"]["email"].endswith("@example.com")
    assert len(data["plants"]) == 1
    assert "hashed_password" not in response.text


def test_metrics_expose_business_gauges():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "plant_care_plants_waiting_sitter" in response.text
    assert "plant_care_average_wait_seconds" in response.text


def test_member_dashboard():
    owner, owner_id = register()
    sitter, _ = register()
    plant = create_plant(owner, "Dash")
    create_plant(owner, "Other")
    request_care(owner, plant)
    offer = client.post(f"/plants/{plant}/care-offers", headers=sitter).json()
    client.post(f"/plants/{plant}/advice-requests", json={"question": "Arrosage ?"}, headers=owner)

    dashboard = client.get("/users/me/dashboard", headers=owner).json()
    assert dashboard["plants_total"] == 2 and dashboard["plants_waiting_sitter"] == 1
    assert [o["id"] for o in dashboard["offers_to_answer"]] == [offer["id"]]
    assert dashboard["advice"][0]["question"] == "Arrosage ?"
    assert client.get("/users/me/dashboard", headers=sitter).json()["my_pending_offers"] == 1

    client.put(f"/care-offers/{offer['id']}/accept", headers=owner)
    sitter_view = client.get("/users/me/dashboard", headers=sitter).json()
    assert [s["plant"]["id"] for s in sitter_view["sitting"]] == [plant]
    owner_view = client.get("/users/me/dashboard", headers=owner).json()
    assert owner_view["plants_being_cared"] == 1 and owner_view["offers_to_answer"] == []

    client.put(f"/plants/{plant}/end-care", headers=owner)
    assert [o["id"] for o in client.get("/users/me/dashboard", headers=owner).json()["reviews_to_give"]] == [offer["id"]]
    client.post(f"/care-offers/{offer['id']}/review", json={"rating": 4}, headers=owner)
    assert client.get("/users/me/dashboard", headers=owner).json()["reviews_to_give"] == []
