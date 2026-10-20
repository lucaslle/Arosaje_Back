# app/tests/test_plants_e2e.py
import os

# Configuration spécifique pour les tests
os.environ["TESTING"] = "True"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-for-testing"
os.environ["TEST_DATABASE_URL"] = "sqlite:///./test_a_rosa_je.db"

import pytest
from fastapi.testclient import TestClient
import io
from PIL import Image
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings

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
        "email": "plantuser@example.com",
        "username": "plantuser",
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
        "email": "plantbotanist@example.com",
        "username": "plantbotanist",
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

@pytest.fixture
def test_image():
    """Fixture pour créer une image de test"""
    # Créer une image test
    file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    image = Image.new('RGB', (100, 100), color='red')
    image.save(file.name)
    file.close()
    
    yield file.name
    
    # Nettoyer après les tests
    os.unlink(file.name)

@pytest.fixture
def test_plant(test_user_token, test_image):
    """Fixture pour créer une plante de test"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Préparer les données multipart
    with open(test_image, "rb") as img:
        plant_data = {
            "name": "Test Plant",
            "location": "Test Location",
            "care_instructions": "Test care instructions"
        }
        files = {"photo": ("test_plant.jpg", img, "image/jpeg")}
        
        response = client.post(
            "/plants/",
            params=plant_data,
            files=files,
            headers=headers
        )
    
    assert response.status_code == 200, f"Création de plante échouée: {response.json()}"
    plant_id = response.json()["id"]
    
    # Retourner l'ID de la plante créée
    return plant_id

def test_create_plant(test_user_token, test_image):
    """Test de création d'une plante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Préparer les données multipart
    with open(test_image, "rb") as img:
        plant_data = {
            "name": "Test Creation Plant",
            "location": "Test Creation Location",
            "care_instructions": "Water daily"
        }
        files = {"photo": ("test_plant.jpg", img, "image/jpeg")}
        
        response = client.post(
            "/plants/",
            params=plant_data,
            files=files,
            headers=headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == plant_data["name"]
    assert data["location"] == plant_data["location"]
    assert data["care_instructions"] == plant_data["care_instructions"]
    assert data["photo_url"] is not None
    assert "id" in data
    assert "owner_id" in data
    assert data["owner_id"] == test_user_token["user_id"]

def test_list_user_plants(test_user_token, test_plant):
    """Test de récupération des plantes de l'utilisateur"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    response = client.get("/my_plants/", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    
    # Vérifier si la plante créée précédemment est dans la liste
    plant_ids = [plant["id"] for plant in data]
    assert test_plant in plant_ids

def test_list_all_plants_except_users(test_user_token, test_botanist_token, test_plant):
    """Test de récupération de toutes les plantes sauf celles de l'utilisateur"""
    # Créer une plante pour le botaniste
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    
    # Création sans photo pour simplifier
    botanist_plant_data = {
        "name": "Botanist Plant",
        "location": "Botanist Location",
        "care_instructions": "Special care"
    }
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    botanist_response = client.post(
        "/plants/",
        params=botanist_plant_data,
        files=files,
        headers=botanist_headers
    )
    assert botanist_response.status_code == 200
    botanist_plant_id = botanist_response.json()["id"]
    
    # Maintenant, vérifier les plantes listées pour l'utilisateur (ne devrait pas voir ses propres plantes)
    user_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    response = client.get("/all_plants/", headers=user_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    
    # Vérifier que seule la plante du botaniste est visible (pas celle de l'utilisateur)
    plant_ids = [plant["id"] for plant in data]
    assert botanist_plant_id in plant_ids
    assert test_plant not in plant_ids

    # Le propriétaire n'expose que des infos publiques (ni hash, ni email, ni téléphone)
    owner = next(plant for plant in data if plant["id"] == botanist_plant_id)["owner"]
    assert set(owner) == {"id", "username", "is_botanist"}
    assert owner["is_botanist"] is False  # claimed but not yet verified by an admin

def test_update_plant(test_user_token, test_plant):
    """Test de mise à jour d'une plante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Données de mise à jour
    update_data = {
        "name": "Updated Plant Name",
        "location": "Updated Location",
        "care_instructions": "Updated care instructions"
    }
    
    # On n'envoie pas de nouvelle photo pour simplifier le test
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    response = client.put(
        f"/plants/{test_plant}",
        params=update_data,
        files=files,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["location"] == update_data["location"]
    assert data["care_instructions"] == update_data["care_instructions"]

def test_photo_upload_rules(test_user_token, test_image):
    """Les photos reçoivent un nom unique et seuls les formats image sont acceptés"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    params = {"name": "Photo Plant", "location": "Here"}

    photo_urls = []
    for _ in range(2):
        with open(test_image, "rb") as img:
            response = client.post("/plants/", params=params, files={"photo": ("same_name.jpg", img, "image/jpeg")}, headers=headers)
        assert response.status_code == 200
        photo_urls.append(response.json()["photo_url"])
    assert photo_urls[0] != photo_urls[1]
    assert all(url.startswith("photos/") for url in photo_urls)

    response = client.post("/plants/", params=params, files={"photo": ("page.html", io.BytesIO(b"<script>"), "text/html")}, headers=headers)
    assert response.status_code == 400

    # après remplacement de la photo, l'URL stockée reste un chemin relatif valide
    plant_id = client.get("/my_plants/", headers=headers).json()[-1]["id"]
    with open(test_image, "rb") as img:
        response = client.put(f"/plants/{plant_id}", files={"photo": ("new.jpg", img, "image/jpeg")}, headers=headers)
    assert response.status_code == 200
    listed = next(p for p in client.get("/my_plants/", headers=headers).json() if p["id"] == plant_id)
    assert listed["photo_url"].startswith("photos/")
    assert os.path.isfile(os.path.join(settings.UPLOAD_DIRECTORY, os.path.basename(listed["photo_url"])))

def test_created_at_is_computed_per_row():
    """La date de création doit être calculée à l'insertion, pas une seule fois au démarrage"""
    from app import models
    assert models.Plant.__table__.c.created_at.default.is_callable

def test_delete_plant(test_user_token):
    """Test de suppression d'une plante"""
    headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    
    # Créer une plante temporaire pour la suppression
    plant_data = {
        "name": "Temporary Plant",
        "location": "Temporary Location",
        "care_instructions": "To be deleted"
    }
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    create_response = client.post(
        "/plants/",
        params=plant_data,
        files=files,
        headers=headers
    )
    assert create_response.status_code == 200
    plant_id = create_response.json()["id"]
    
    # Supprimer la plante
    delete_response = client.delete(
        "/plants", 
        params={"plant_id": plant_id},
        headers=headers
    )
    
    assert delete_response.status_code == 200
    
    # Vérifier que la plante n'existe plus
    response = client.get("/my_plants/", headers=headers)
    assert response.status_code == 200
    plants = response.json()
    
    plant_ids = [plant["id"] for plant in plants]
    assert plant_id not in plant_ids

def test_unauthorized_plant_delete(test_user_token, test_botanist_token, test_plant):
    """Ni un anonyme ni un autre utilisateur ne peut supprimer la plante"""
    anonymous_response = client.delete("/plants", params={"plant_id": test_plant})
    assert anonymous_response.status_code == 401

    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    response = client.delete("/plants", params={"plant_id": test_plant}, headers=botanist_headers)
    assert response.status_code == 403

    owner_headers = {"Authorization": f"Bearer {test_user_token['token']}"}
    plant_ids = [plant["id"] for plant in client.get("/my_plants/", headers=owner_headers).json()]
    assert test_plant in plant_ids

def test_unauthorized_plant_update(test_user_token, test_botanist_token, test_plant):
    """Test de tentative de mise à jour non autorisée d'une plante"""
    botanist_headers = {"Authorization": f"Bearer {test_botanist_token['token']}"}
    
    # Tentative de mise à jour d'une plante non appartenant au botaniste
    update_data = {
        "name": "Hacked Plant Name",
        "location": "Hacked Location"
    }
    files = {"photo": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    
    response = client.put(
        f"/plants/{test_plant}",
        data=update_data,
        files=files,
        headers=botanist_headers
    )
    
    # Devrait échouer car la plante n'appartient pas au botaniste
    assert response.status_code == 404
    assert "Plant not found or not owned by current user" in response.json()["detail"]

# Nettoyer la base de données de test après les tests
def teardown_module():
    Base.metadata.drop_all(bind=engine)
    os.remove("./test_a_rosa_je.db")
