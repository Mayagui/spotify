import os

from dotenv import load_dotenv


load_dotenv()


SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")
TOKEN_ENCRYPTION_KEY: str = os.getenv("TOKEN_ENCRYPTION_KEY", "")


def assert_config() -> None:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET manquants. "
            "Configurez votre fichier .env avec vos vrais identifiants."
        )
    if not TOKEN_ENCRYPTION_KEY:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY manquant dans .env. "
            "Générez une clé avec : python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        