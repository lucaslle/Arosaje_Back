# app/tests/test_comments_e2e.py
import os

# Configuration spécifique pour les tests
os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

import pytest
from fastapi.testclient import TestClient
import io
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings

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


@pytest.fixture(scope="module")
def test_user_token():
    """Fixture pour créer un utilisateur de test et obtenir un token"""
    # Créer un utilisateur de test
    user_data = {
        "email": "commentuser@example.com",
        "username": "commentuser",
        "phone": "1234567890",
        "password": "testpassword",
        "is_botanist": False
    }
    response = client.post("/users/", json=user_data)
    assert response.status_code == 200, f"Création d'utilisateur échouée: {response.json()}"
    
    # Obtenir un token
    login_data = {
        "username": user_data["email"],
        "password": user_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200, f"Login échoué: {response.json()}"
    token_data = response.json()
    user_response = client.get("/users/me/", headers={"Authorization": f"Bearer {token_data['access_token']}"})
    
    return {
        "user_id": user_response.json()["id"],
        "token": token_data["access_token"],
        "user_data": user_data
    }

@pytest.fixture(scope="module")
def test_botanist_token():
    """Fixture pour créer un botaniste de test et obtenir un token"""
    # Créer un botaniste de test
    botanist_data = {
        "email": "commentbotanist@example.com",
        "username": "commentbotanist",
        "phone": "0987654321",
        "password": "botanistpassword",
        "is_botanist": True
    }
    response = client.post("/users/", json=botanist_data)
    assert response.status_code == 200, f"Création de botaniste échouée: {response.json()}"
    
    # Obtenir un token
    login_data = {
        "username": botanist_data["email"],
        "password": botanist_data["password"]
    }
    response = client.post("/token", data=login_data)
    assert response.status_code == 200, f"Login échoué: {response.json()}"
    token_data = response.json()
    user_response = client.get("/users/me/", headers={"Authorization": f"Bearer {token_data['access_token']}"})
    
    return {
        "user_id": user_response.json()["id"],
        "token": token_data["access_token"],
        "user_data": botanist_data
    }

@pytest.fixture(scope="module")
def test_plant(test_user_token):
    """Fixture pour créer une plante de test"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Créer une plante sans photo pour simplifier
    plant_data = {
        "name": "Comment Test Plant",
        "location": "Test Location",
        "care_instructions": "Test care instructions"
    }
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    response = client.post(
        "/plants/",
        params=plant_data,
        files=files,
        headers=headers
    )
    
    assert response.status_code == 200, f"Création de plante échouée: {response.json()}"
    
    # Retourner l'ID de la plante créée
    return response.json()["id"]

@pytest.fixture(scope="module")
def test_comment(test_user_token, test_plant):
    """Fixture pour créer un commentaire de test"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    comment_data = {
        "plant_id": test_plant,
        "comment": "This is a test comment"
    }
    
    response = client.post("/comments/", params=comment_data, headers=headers)
    
    assert response.status_code == 200, f"Création de commentaire échouée: {response.json()}"
    
    # Retourner l'ID du commentaire créé
    return response.json()["id"]

def test_create_comment(test_user_token, test_plant):
    """Test de création d'un commentaire"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    comment_data = {
        "plant_id": test_plant,
        "comment": "This is a new comment for testing"
    }
    
    response = client.post("/comments/", params=comment_data, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["comment"] == comment_data["comment"]
    assert data["plant_id"] == test_plant
    assert data["user_id"] == test_user_token["user_id"]
    assert "id" in data

def test_create_comment_nonexistent_plant(test_user_token):
    """Test de création d'un commentaire pour une plante inexistante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    nonexistent_plant_id = 9999  # ID qui n'existe pas
    comment_data = {
        "plant_id": nonexistent_plant_id,
        "comment": "This comment should not be created"
    }
    
    response = client.post("/comments/", params=comment_data, headers=headers)
    
    assert response.status_code == 404
    assert "Plant not found" in response.json()["detail"]

def test_get_plant_comments(test_user_token, test_plant, test_comment):
    """Test de récupération des commentaires d'une plante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    response = client.get(f"/plants/{test_plant}/comments/", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Vérifier si le commentaire créé précédemment est dans la liste
    comment_ids = [comment["id"] for comment in data]
    assert test_comment in comment_ids
    
    # Vérifier le contenu d'au moins un commentaire
    comment = next((c for c in data if c["id"] == test_comment), None)
    assert comment is not None
    assert "comment" in comment
    assert "user_id" in comment
    assert "plant_id" in comment
    assert comment["plant_id"] == test_plant
    assert set(comment["user"]) == {"id", "username", "is_botanist"}

def test_get_plant_comments_requires_login(test_plant, test_comment):
    """Les commentaires (et les noms de leurs auteurs) ne sont pas visibles sans connexion"""
    response = client.get(f"/plants/{test_plant}/comments/")
    assert response.status_code == 401

def test_get_comments_nonexistent_plant(test_user_token):
    """Test de récupération des commentaires d'une plante inexistante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    nonexistent_plant_id = 9999  # ID qui n'existe pas
    response = client.get(f"/plants/{nonexistent_plant_id}/comments/", headers=headers)
    
    assert response.status_code == 404
    assert "Plant not found" in response.json()["detail"]

def test_update_comment(test_user_token, test_comment):
    """Test de mise à jour d'un commentaire"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    updated_text = "This is an updated comment text"
    
    response = client.put(
        f"/comments/{test_comment}", 
        params={"comment_text": updated_text},
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["comment"] == updated_text
    assert data["id"] == test_comment

def test_update_nonexistent_comment(test_user_token):
    """Test de mise à jour d'un commentaire inexistant"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    nonexistent_comment_id = 9999  # ID qui n'existe pas
    updated_text = "This should not update anything"
    
    response = client.put(
        f"/comments/{nonexistent_comment_id}", 
        params={"comment_text": updated_text},
        headers=headers
    )
    
    assert response.status_code == 404
    assert "Comment not found" in response.json()["detail"]

def test_unauthorized_comment_update(test_botanist_token, test_comment):
    """Test de mise à jour non autorisée d'un commentaire"""
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    
    updated_text = "This is an unauthorized update attempt"
    
    response = client.put(
        f"/comments/{test_comment}", 
        params={"comment_text": updated_text},
        headers=botanist_headers
    )
    
    # Devrait échouer car le commentaire n'appartient pas au botaniste
    assert response.status_code == 403
    assert "Not authorized to update this comment" in response.json()["detail"]

def test_get_user_comments(test_user_token, test_comment):
    """Test de récupération des commentaires d'un utilisateur"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    response = client.get(f"/users/{test_user_token['user_id']}/comments/", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # Vérifier si le commentaire créé précédemment est dans la liste
    comment_ids = [comment["id"] for comment in data]
    assert test_comment in comment_ids

def test_get_comments_nonexistent_user(test_user_token):
    """Test de récupération des commentaires d'un utilisateur inexistant"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    nonexistent_user_id = 9999  # ID qui n'existe pas
    response = client.get(f"/users/{nonexistent_user_id}/comments/", headers=headers)
    
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]

def test_comment_owner_can_delete(test_user_token, test_plant):
    """Test de suppression d'un commentaire par son auteur"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Créer un commentaire temporaire
    comment_data = {
        "plant_id": test_plant,
        "comment": "This comment will be deleted by its owner"
    }
    
    create_response = client.post("/comments/", params=comment_data, headers=headers)
    assert create_response.status_code == 200
    comment_id = create_response.json()["id"]
    
    # Supprimer le commentaire
    delete_response = client.delete(f"/comments/{comment_id}", headers=headers)
    
    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["id"] == comment_id
    
    # Vérifier que le commentaire a bien été supprimé
    response = client.get(f"/plants/{test_plant}/comments/", headers=headers)
    comment_ids = [comment["id"] for comment in response.json()]
    assert comment_id not in comment_ids

def test_plant_owner_can_delete_comment(test_user_token, test_botanist_token, test_plant):
    """Test qu'un propriétaire de plante peut supprimer n'importe quel commentaire sur sa plante"""
    # Créer un commentaire en tant que botaniste
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    comment_data = {
        "plant_id": test_plant,
        "comment": "This comment will be deleted by the plant owner"
    }
    
    create_response = client.post("/comments/", params=comment_data, headers=botanist_headers)
    assert create_response.status_code == 200
    comment_id = create_response.json()["id"]
    
    # Supprimer le commentaire en tant que propriétaire de la plante
    user_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    delete_response = client.delete(f"/comments/{comment_id}", headers=user_headers)
    
    assert delete_response.status_code == 200
    
    # Vérifier que le commentaire a bien été supprimé
    response = client.get(f"/plants/{test_plant}/comments/", headers=user_headers)
    comment_ids = [comment["id"] for comment in response.json()]
    assert comment_id not in comment_ids

def test_unauthorized_comment_delete(test_user_token, test_botanist_token, test_comment):
    """Test qu'un utilisateur ne peut pas supprimer un commentaire qui ne lui appartient pas sur une plante qui ne lui appartient pas"""
    # Créer une plante pour le botaniste
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    
    plant_data = {
        "name": "Botanist Plant",
        "location": "Botanist Location",
        "care_instructions": "Botanist care"
    }
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    plant_response = client.post("/plants/", params=plant_data, files=files, headers=botanist_headers)
    assert plant_response.status_code == 200
    botanist_plant_id = plant_response.json()["id"]
    
    # Créer un commentaire sur la plante du botaniste
    comment_data = {
        "plant_id": botanist_plant_id,
        "comment": "Comment on botanist's plant"
    }
    comment_response = client.post("/comments/", params=comment_data, headers=botanist_headers)
    assert comment_response.status_code == 200
    botanist_comment_id = comment_response.json()["id"]
    
    # Tentative de suppression du commentaire par l'utilisateur
    user_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    delete_response = client.delete(f"/comments/{botanist_comment_id}", headers=user_headers)
    
    # Devrait échouer car l'utilisateur n'est ni l'auteur du commentaire ni le propriétaire de la plante
    assert delete_response.status_code == 403
    assert "Not authorized to delete this comment" in delete_response.json()["detail"]

# Nettoyer la base de données de test après les tests
def teardown_module():
    Base.metadata.drop_all(bind=engine)
    os.remove("./test_a_rosa_je.db")