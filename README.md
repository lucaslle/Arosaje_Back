# A'rosa-je — API

API d'A'rosa-je : des particuliers confient leurs plantes à d'autres membres pendant leur absence et demandent conseil à des botanistes.

Ce dépôt contient l'API (FastAPI + PostgreSQL) et sa pile d'observabilité (Grafana, Prometheus, Loki, Tempo, Alloy). L'interface web est dans [Arosaje_Front](https://github.com/lucaslle/Arosaje_Front).

## Démarrage rapide

Prérequis : Docker avec Docker Compose. Les ports listés plus bas doivent être libres.

1. Crée le fichier `.env` à partir de l'exemple, puis remplace `change-me` par deux valeurs aléatoires :
   ```bash
   cp .env.example .env
   ```
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Lance la seconde commande deux fois : une valeur pour `SECRET_KEY`, une pour `ENCRYPTION_KEY`. Pour avoir un compte administrateur, ajoute son e-mail dans `ADMIN_EMAILS`, par exemple `ADMIN_EMAILS=["moi@example.com"]`.

2. Démarre tout :
   ```bash
   docker compose up -d
   ```

3. Vérifie que l'API répond : http://localhost:8000/health. La documentation interactive des routes est sur http://localhost:8000/docs.

Au démarrage, le conteneur de l'API applique les migrations de la base avant de lancer le serveur, il n'y a rien à faire à la main. Une base créée par une ancienne version du projet est détectée et mise à niveau.

Pour l'interface web, voir le README d'Arosaje_Front.

> L'API refuse de démarrer si `SECRET_KEY` ou `ENCRYPTION_KEY` manque, fait moins de 32 caractères ou vaut encore `change-me`. Ne change pas `ENCRYPTION_KEY` sur une base existante : les e-mails, noms et téléphones déjà chiffrés deviendraient illisibles.

## Services

| Service | Port | Rôle |
|---|---|---|
| API (`plant_care_api`) | 8000 | FastAPI, documentation sur `/docs`, métriques sur `/metrics` |
| PostgreSQL | 5432 | Base de données |
| Grafana | 3000 | Tableaux de bord (identifiants `admin` / `admin`) |
| Prometheus | 9090 | Métriques |
| Loki | 3100 | Journaux |
| Tempo | 3200, 4317, 4318 | Traces |
| Alloy | 12345 | Collecteur de journaux et de traces |
| Node Exporter | 9100 | Métriques de la machine |

## Configuration

Toutes les variables se lisent depuis l'environnement ou depuis `.env`.

| Variable | Rôle | Défaut |
|---|---|---|
| `SECRET_KEY` | Signature des tokens de connexion | aucun, obligatoire |
| `ENCRYPTION_KEY` | Chiffrement des données personnelles et empreintes des e-mails et téléphones | aucun, obligatoire |
| `ADMIN_EMAILS` | E-mails des administrateurs, au format JSON | `[]` |
| `DATABASE_URL` | Base PostgreSQL | celle du `docker-compose.yml` |
| `CORS_ORIGINS` | Adresses autorisées à appeler l'API depuis un navigateur, au format JSON | `["http://localhost:5000"]` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Durée de validité d'un token | `30` |
| `MAX_FILE_SIZE` | Taille maximale d'une photo, en octets | 10 Mo |
| `ENABLE_OBSERVABILITY` | Envoi des traces et journaux à Alloy | `true` |

## Fonctionnalités de l'API

- **Comptes** : inscription, connexion par token, profil, changement de mot de passe, export de ses données (RGPD), suppression du compte avec ses plantes, photos et échanges.
- **Plantes** : ajout avec photo, modification, suppression, recherche par nom ou lieu, pagination.
- **Garde** : demande avec dates, offres que le propriétaire accepte ou refuse, messagerie privée par offre, journal de garde avec photos, fin de garde, avis du propriétaire sur le gardien. Les demandes et gardes dont la date de fin est passée se ferment automatiquement.
- **Communauté** : commentaires, favoris, questions aux botanistes, profils publics avec la note des gardiens.
- **Administration** : validation des membres qui se déclarent botanistes.
- **Tableau de bord** : `GET /users/me/dashboard` regroupe en un appel tout ce qu'un membre doit voir ou faire.

## Sécurité et données personnelles

- **Chiffrement :** e-mail, nom d'utilisateur et téléphone sont chiffrés en base. Pour retrouver un compte sans déchiffrer, l'API compare des empreintes HMAC (un calcul à sens unique qui dépend d'une clé secrète).
- **E-mails :** ils sont comparés en minuscules et sans espaces.
- **Token de connexion :** il désigne le membre par son identifiant. Changer d'e-mail ne déconnecte donc pas.
- **Données dans les requêtes :** tout ce que le membre saisit (profil, commentaires, lieu des plantes) voyage dans le corps des requêtes, jamais dans l'URL. Les journaux ne notent que le chemin des requêtes.
- **Réponses de l'API :** les données d'un autre membre se limitent à son identifiant, son nom d'utilisateur et son statut de botaniste validé.
- **Limite de connexion :** après 10 échecs sur un compte, ou 30 depuis une même adresse, en 15 minutes, la connexion répond 429. Les compteurs sont gardés en mémoire : avec plusieurs processus API, il faudra les déplacer dans Redis.
- **Photos :** elles reçoivent un nom aléatoire et sont limitées en format et en taille.

## Base de données et migrations

Le schéma est géré par Alembic (`alembic/versions/`) et appliqué au démarrage par `python -m app.migrate`.

Pour ajouter une migration :
1. modifie `app/models.py` ;
2. crée un fichier dans `alembic/versions/` dont `down_revision` pointe vers la dernière révision ;
3. redémarre l'API.

Pour appliquer les migrations à la main dans le conteneur :

```bash
docker compose exec api alembic upgrade head
```

## Tests

Les tests utilisent SQLite et un dossier de photos temporaire. Ils n'ont besoin ni de PostgreSQL ni de `.env`.

En local :

```bash
pip install -r requirements-dev.txt
```

```bash
pytest app/tests
```

La CI GitHub (`.github/workflows/ci.yml`) lance l'analyse du code, les tests et la construction de l'image Docker à chaque push.

## Observabilité

**Tableaux de bord Grafana** (http://localhost:3000) :
- **Plant Care - Activité métier** : plantes en attente de gardien, gardes en cours, offres à traiter, délai moyen avant prise en garde, note moyenne des gardiens, questions ouvertes aux botanistes, botanistes à vérifier.
- **Plant Care - Application Overview** : inscriptions, créations de plantes et journaux de l'application.

**Métriques** exposées sur `/metrics` et récupérées par Prometheus toutes les 15 secondes :
- **calculées depuis la base à chaque relevé :** `plant_care_plants_total`, `plant_care_plants_waiting_sitter`, `plant_care_plants_being_cared`, `plant_care_offers_pending`, `plant_care_cares_completed_total`, `plant_care_average_wait_seconds`, `plant_care_average_rating`, `plant_care_advice_requests_open`, `plant_care_botanists_waiting_verification` ;
- **compteurs d'événements :** `plant_care_user_registrations_total`, `plant_care_plant_creations_total`, `plant_care_care_requests_total`, `plant_care_comments_created_total`. Ils n'apparaissent qu'après le premier événement de chaque type.

**Journaux** au format JSON dans Loki, sous le label `service="api"`. Quelques exemples de requêtes :

```logql
{service="api", level="error"}
{service="api"} | json | path="/token" | status_code="429"
{service="api"} | json | __error__="" | duration_ms > 1000
```

**Traces** dans Tempo : recherche par `service.name="plant-care-api"`.

## Commandes utiles

```bash
docker compose logs -f api
```

```bash
docker compose up -d --build api
```

```bash
docker compose exec postgres pg_dump -U plant_user plant_care_db > sauvegarde.sql
```

```bash
docker compose down
```

`docker compose down -v` supprime aussi les volumes, donc **toute la base et les données Grafana**.

## Dépannage

| Symptôme | Cause et solution |
|---|---|
| `SECRET_KEY manquant, copiez .env.example vers .env` | Le fichier `.env` n'existe pas ou ne contient pas les clés : voir le Démarrage rapide. |
| `port is already allocated` | Un autre programme utilise ce port : arrête-le, ou change le port de gauche dans `docker-compose.yml`. |
| Le front reçoit des erreurs CORS | Ajoute l'adresse du front dans `CORS_ORIGINS`. |
| Tout le monde est déconnecté après une mise à jour | Normal quand le format du token change : il suffit de se reconnecter. |
| Connexion refusée avec 429 | Trop d'échecs récents : attends 15 minutes ou redémarre l'API. |
