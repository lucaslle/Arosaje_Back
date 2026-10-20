# app/tests/test_security_e2e.py
import os

# Configuration spécifique pour les tests
os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings
from app.security import security_manager
from app import models
import json

# Créer une base de données de test SQLite
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

def get_db_session():
    """Fonction utilitaire pour obtenir une session de base de données"""
    db = TestingSessionLocal()
    try:
        return db
    finally:
        db.close()

@pytest.fixture(scope="module")
def test_user_data():
    """Fixture pour créer des données d'utilisateur de test"""
    return {
        "email": "security@example.com",
        "username": "securityuser",
        "phone": "1122334455",
        "password": "securepassword",
        "is_botanist": False
    }

def test_user_data_encryption(test_user_data):
    """Test que les données personnelles sont correctement chiffrées dans la base de données"""
    # Créer un utilisateur
    response = client.post("/users/", json=test_user_data)
    assert response.status_code == 200
    user_id = response.json()["id"]
    
    # Récupérer l'utilisateur directement depuis la base de données
    db = get_db_session()
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    
    # Vérifier que les données sensibles sont chiffrées
    assert db_user.email_encrypted != test_user_data["email"]
    assert db_user.username_encrypted != test_user_data["username"]
    assert db_user.phone_encrypted != test_user_data["phone"]
    
    # Vérifier que les données hashées sont présentes
    assert db_user.email_hash is not None
    assert db_user.username_hash is not None
    assert db_user.phone_hash is not None
    
    # Vérifier que le mot de passe est haché
    assert db_user.hashed_password != test_user_data["password"]
    
    # Vérifier que les données peuvent être déchiffrées correctement
    decrypted_email = security_manager.decrypt_value(db_user.email_encrypted)
    decrypted_username = security_manager.decrypt_value(db_user.username_encrypted)
    decrypted_phone = security_manager.decrypt_value(db_user.phone_encrypted)
    
    assert decrypted_email == test_user_data["email"]
    assert decrypted_username == test_user_data["username"]
    assert decrypted_phone == test_user_data["phone"]

def test_token_expiration():
    """Test que les tokens expirent correctement"""
    # Modifier temporairement le temps d'expiration des tokens pour le test
    original_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = 0  # Expire immédiatement
    
    # Créer un utilisateur et obtenir un token
    user_data = {
        "email": "expiration@example.com",
        "username": "expirationuser",
        "phone": "9988776655",
        "password": "expirationpassword",
        "is_botanist": False
    }
    client.post("/users/", json=user_data)
    
    login_data = {
        "username": user_data["email"],
        "password": user_data["password"]
    }
    response = client.post("/token", data=login_data)
    token = response.json()["access_token"]

    # Forcer l'expiration du token en ajustant la date d'expiration
    import time
    from jose import jwt
    payload = jwt.get_unverified_claims(token)
    payload["exp"] = int(time.time()) - 1
    expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    headers = {"Authorization": f"Bearer {expired_token}"}
    response = client.get("/users/me/", headers=headers)
    
    # Restaurer le temps d'expiration original
    settings.ACCESS_TOKEN_EXPIRE_MINUTES = original_expire_minutes
    
    # Vérifier que la requête a échoué à cause de l'expiration du token
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

def test_invalid_token():
    """Test que les tokens invalides sont rejetés"""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJpbnZhbGlkQGV4YW1wbGUuY29tIiwiZXhwIjoxOTU4NjU0NDAwfQ.invalid_signature"
    
    headers = {"Authorization": f"Bearer {invalid_token}"}
    response = client.get("/users/me/", headers=headers)
    
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]

def test_password_security(test_user_data):
    """Test que les mots de passe sont correctement hachés et vérifiés"""
    # Créer un utilisateur distinct pour ce test
    unique_data = test_user_data.copy()
    unique_data["email"] = "security2@example.com"
    unique_data["username"] = "securityuser2"
    response = client.post("/users/", json=unique_data)
    assert response.status_code == 200
    
    # Récupérer l'utilisateur directement depuis la base de données
    db = get_db_session()
    email_hash = security_manager.hash_value(unique_data["email"])
    db_user = db.query(models.User).filter(models.User.email_hash == email_hash).first()
    
    # Vérifier que le mot de passe est bien haché (ne contient pas le mot de passe en clair)
    assert test_user_data["password"] not in db_user.hashed_password
    
    # Vérifier que le login fonctionne avec le bon mot de passe
    login_data = {
        "username": unique_data["email"],
        "password": unique_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200
    
    # Vérifier que le login échoue avec un mauvais mot de passe
    wrong_login_data = {
        "username": unique_data["email"],
        "password": "wrongpassword"
    }
    response = client.post("/token", data=wrong_login_data)
    assert response.status_code == 401

def test_authorization_endpoints():
    """Test que les endpoints protégés nécessitent une authentification"""
    # Endpoints qui devraient être protégés
    protected_endpoints = [
        {"method": "GET", "url": "/users/me/"},
        {"method": "GET", "url": "/my_plants/"},
        {"method": "GET", "url": "/all_plants/"},
        {"method": "POST", "url": "/plants/", "params": {"name": "test", "location": "test"}, "files": {"photo": ("empty.jpg", b"")}},
        {"method": "GET", "url": "/care-requests/"}
    ]
    
    for endpoint in protected_endpoints:
        method = endpoint["method"]
        url = endpoint["url"]
        
        if method == "GET":
            response = client.get(url)
        elif method == "POST":
            params = endpoint.get("params", {})
            files = endpoint.get("files", {})
            response = client.post(url, data=params, files=files)
        
        # Tous les endpoints protégés devraient renvoyer 401 sans token
        assert response.status_code == 401, f"Endpoint {method} {url} ne nécessite pas d'authentification"

def test_cross_user_access_control(test_user_data):
    """Test que les utilisateurs ne peuvent pas accéder aux ressources d'autres utilisateurs"""
    # Créer deux utilisateurs
    user1_data = {
        "email": "user1@example.com",
        "username": "user1",
        "phone": "1111111111",
        "password": "password1",
        "is_botanist": False
    }
    user2_data = {
        "email": "user2@example.com",
        "username": "user2",
        "phone": "2222222222",
        "password": "password2",
        "is_botanist": False
    }
    
    client.post("/users/", json=user1_data)
    client.post("/users/", json=user2_data)
    
    # Obtenir des tokens pour les deux utilisateurs
    user1_login = {"username": user1_data["email"], "password": user1_data["password"]}
    user2_login = {"username": user2_data["email"], "password": user2_data["password"]}
    
    user1_token = client.post("/token", data=user1_login).json()["access_token"]
    user2_token = client.post("/token", data=user2_login).json()["access_token"]
    
    # Obtenir l'ID de l'utilisateur 1
    user1_headers = {"Authorization": f"Bearer {user1_token}"}
    user1_id = client.get("/users/me/", headers=user1_headers).json()["id"]
    
    # Obtenir l'ID de l'utilisateur 2
    user2_headers = {"Authorization": f"Bearer {user2_token}"}
    user2_id = client.get("/users/me/", headers=user2_headers).json()["id"]
    
    # L'utilisateur 1 tente de mettre à jour l'utilisateur 2
    update_data = {"username": "hacked"}
    response = client.put(f"/users/{user2_id}", params=update_data, headers=user1_headers)
    
    # Devrait être interdit
    assert response.status_code == 403
    assert "Not authorized to update other users" in response.json()["detail"]

# Nettoyer la base de données de test après les tests
def teardown_module():
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_a_rosa_je.db"):
        os.remove("./test_a_rosa_je.db")