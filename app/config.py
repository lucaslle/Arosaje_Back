# app/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    DATABASE_URL: str = "postgresql://plant_user:plant_password@localhost:5432/plant_care_db"

    # Required: no default, so the app refuses to start without real keys
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    TESTING: bool = False
    TEST_DATABASE_URL: str = "postgresql://plant_user:plant_password@localhost:5432/plant_care_test_db"

    ENABLE_OBSERVABILITY: bool = True
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://alloy:4317"

    UPLOAD_DIRECTORY: str = "photos"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: list[str] = ["jpg", "jpeg", "png", "gif", "webp"]

    CORS_ORIGINS: list[str] = ["http://localhost:5000"]


settings = Settings()

if os.getenv("TESTING", "").lower() in ("true", "1", "t"):
    settings.TESTING = True
    settings.DATABASE_URL = settings.TEST_DATABASE_URL
    settings.ENABLE_OBSERVABILITY = False


def get_database_url() -> str:
    """Retourne l'URL de base de données avec gestion des différents environnements"""
    if settings.TESTING:
        return settings.TEST_DATABASE_URL
    return settings.DATABASE_URL


def validate_config():
    """Valide la configuration au démarrage"""
    errors = []

    for name in ("SECRET_KEY", "ENCRYPTION_KEY"):
        value = getattr(settings, name)
        if len(value) < 32 or value.startswith("change-me"):
            errors.append(f"{name} must be a random value of at least 32 characters (see .env.example)")

    if settings.ENABLE_OBSERVABILITY and not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        errors.append("OTEL_EXPORTER_OTLP_ENDPOINT is required when observability is enabled")

    try:
        os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
    except OSError as e:
        errors.append(f"Cannot create upload directory {settings.UPLOAD_DIRECTORY}: {e}")

    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")


if not settings.TESTING:
    validate_config()
