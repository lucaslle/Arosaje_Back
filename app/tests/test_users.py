import os

# Configuration spécifique pour les tests
os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

import io
import pytest
from fastapi.testclient import TestClient
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings
from app.security import security_manager

# Créer une base de données de test SQLite en mémoire
TEST_DATABASE_URL = "sqlite:///./test_a_rosa_je.db"
engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Créer les tables dans la base de données de test
Base.metadata.create_all(bind=engine)

# Remplacer la dépendance de base de données par notre session de test
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Client de test
client = TestClient(app)

@pytest.fixture(scope="module")
def test_user_token():
    """Fixture pour créer un utilisateur de test et obtenir un token"""
    # Créer un utilisateur de test
    user_data = {
        "email": "test@example.com",
        "username": "testuser",
        "phone": "1234567890",
        "password": "testpassword",
        "is_botanist": False
    }
    response = client.post("/users/", json=user_data)
    assert response.status_code == 200, f"Création d'utilisateur échouée: {response.json()}"
    user_id = response.json()["id"]

    # Obtenir un token
    login_data = {
        "username": user_data["email"],
        "password": user_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200, f"Login échoué: {response.json()}"
    token_data = response.json()
    
    return {
        "user_id": user_id,
        "token": token_data["access_token"],
        "user_data": user_data
    }

@pytest.fixture(scope="module")
def test_botanist_token():
    """Fixture pour créer un botaniste de test et obtenir un token"""
    # Créer un botaniste de test
    botanist_data = {
        "email": "botanist@example.com",
        "username": "botanistuser",
        "phone": "0987654321",
        "password": "botanistpassword",
        "is_botanist": True
    }
    response = client.post("/users/", json=botanist_data)
    assert response.status_code == 200, f"Création de botaniste échouée: {response.json()}"
    botanist_id = response.json()["id"]

    # Obtenir un token
    login_data = {
        "username": botanist_data["email"],
        "password": botanist_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200, f"Login échoué: {response.json()}"
    token_data = response.json()
    
    return {
        "user_id": botanist_id,
        "token": token_data["access_token"],
        "user_data": botanist_data
    }

def test_create_user():
    """Test de création d'utilisateur"""
    user_data = {
        "email": "newuser@example.com",
        "username": "newuser",
        "phone": "5555555555",
        "password": "newpassword",
        "is_botanist": False
    }
    response = client.post("/users/", json=user_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert data["phone"] == user_data["phone"]
    assert data["is_botanist"] == user_data["is_botanist"]
    assert "id" in data

def test_create_duplicate_user():
    """Test de création d'utilisateur avec email dupliqué"""
    user_data = {
        "email": "duplicate@example.com",
        "username": "duplicateuser",
        "phone": "1231231231",
        "password": "duplicatepassword",
        "is_botanist": False
    }
    # Première création - devrait réussir
    response = client.post("/users/", json=user_data)
    assert response.status_code == 200
    
    # Deuxième création avec le même email - devrait échouer
    response = client.post("/users/", json=user_data)
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_get_current_user(test_user_token):
    """Test pour récupérer les informations de l'utilisateur actuel"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    response = client.get("/users/me/", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_token["user_data"]["email"]
    assert data["username"] == test_user_token["user_data"]["username"]
    assert data["is_botanist"] == test_user_token["user_data"]["is_botanist"]

def test_update_user(test_user_token):
    """Test de mise à jour d'un utilisateur"""
    user_id = test_user_token["user_id"]
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Mettre à jour le nom d'utilisateur et le téléphone
    update_data = {
        "username": "updateduser",
        "phone": "9876543210"
    }
    
    response = client.put(f"/users/{user_id}", params=update_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == update_data["username"]
    assert data["phone"] == update_data["phone"]
    
    # Vérifier que les modifications sont persistantes
    response = client.get("/users/me/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == update_data["username"]
    assert data["phone"] == update_data["phone"]

def test_unauthorized_user_update(test_user_token, test_botanist_token):
    """Test de mise à jour non autorisée d'un utilisateur"""
    botanist_id = test_botanist_token["user_id"]
    user_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Tentative de mise à jour d'un autre utilisateur
    update_data = {
        "username": "hackeduser",
        "phone": "1111111111"
    }
    
    response = client.put(f"/users/{botanist_id}", params=update_data, headers=user_headers)
    
    # Devrait être interdit (403)
    assert response.status_code == 403
    assert "Not authorized to update other users" in response.json()["detail"]

def test_login_with_wrong_credentials():
    """Test de connexion avec des identifiants incorrects"""
    login_data = {
        "username": "wrongemail@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/token", data=login_data)
    
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_authentication_without_token():
    """Test d'accès à un endpoint protégé sans token"""
    response = client.get("/users/me/")
    
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]

def test_delete_user(test_user_token):
    """Test de suppression d'un utilisateur"""
    # Créer un utilisateur temporaire pour la suppression
    temp_user_data = {
        "email": "temp@example.com",
        "username": "tempuser",
        "phone": "9999999999",
        "password": "temppassword",
        "is_botanist": False
    }
    response = client.post("/users/", json=temp_user_data)
    assert response.status_code == 200
    temp_user_id = response.json()["id"]
    
    # Connecter l'utilisateur temporaire
    login_response = client.post("/token", data={
        "username": temp_user_data["email"],
        "password": temp_user_data["password"]
    })
    assert login_response.status_code == 200
    temp_token = login_response.json()["access_token"]
    
    # Supprimer l'utilisateur
    headers = {"Authorization": f"Bearer {temp_token}"}
    response = client.delete(f"/users/", params={"id": temp_user_id}, headers=headers)
    
    assert response.status_code == 200
    
    # Vérifier que l'utilisateur a été supprimé en tentant de se connecter
    login_response = client.post("/token", data={
        "username": temp_user_data["email"],
        "password": temp_user_data["password"]
    })
    assert login_response.status_code == 401

def test_unauthorized_user_delete(test_user_token, test_botanist_token):
    """Un utilisateur ne peut pas supprimer le compte d'un autre"""
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    response = client.delete("/users/", params={"id": test_user_token["user_id"]}, headers=botanist_headers)
    assert response.status_code == 403

    user_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    assert client.get("/users/me/", headers=user_headers).status_code == 200

def test_delete_user_with_plants_keeps_lists_working():
    """Supprimer un compte qui possède une plante et en garde une autre ne casse pas les listes"""
    def register(email, username, phone):
        assert client.post("/users/", json={"email": email, "username": username, "phone": phone, "password": "password123"}).status_code == 200
        token = client.post("/token", data={"username": email, "password": "password123"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    leaving = register("leaving@example.com", "leaving", "0600000001")
    staying = register("staying@example.com", "staying", "0600000002")
    photo = lambda: {"photo": ("p.jpg", io.BytesIO(b"img"), "image/jpeg")}

    assert client.post("/plants/", params={"name": "Leaving plant", "location": "A"}, files=photo(), headers=leaving).status_code == 200
    staying_plant = client.post("/plants/", params={"name": "Staying plant", "location": "B"}, files=photo(), headers=staying).json()["id"]
    client.put(f"/plants/{staying_plant}", params={"care_requested": True}, headers=staying)
    assert client.put(f"/plants/{staying_plant}/start-care", headers=leaving).status_code == 200

    leaving_photo = client.get("/my_plants/", headers=leaving).json()[0]["photo_url"]
    leaving_id = client.get("/users/me/", headers=leaving).json()["id"]
    assert client.delete("/users/", params={"id": leaving_id}, headers=leaving).status_code == 200

    response = client.get("/all_plants/", headers=staying)
    assert response.status_code == 200
    assert "Leaving plant" not in [plant["name"] for plant in response.json()]
    assert not os.path.exists(os.path.join(settings.UPLOAD_DIRECTORY, os.path.basename(leaving_photo)))
    mine = client.get("/my_plants/", headers=staying).json()
    assert next(p for p in mine if p["id"] == staying_plant)["in_care_id"] is None

# Nettoyer la base de données de test après les tests
def teardown_module():
    Base.metadata.drop_all(bind=engine)
    os.remove("./test_a_rosa_je.db")