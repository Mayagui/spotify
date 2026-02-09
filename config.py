import os

from dotenv import load_dotenv


load_dotenv()


SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8000/callback")
APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")


def assert_config() -> None:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError(
            "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET manquants. "
            "Configurez votre fichier .env avec vos vrais identifiants."
        )
    if SPOTIFY_CLIENT_ID == "" or SPOTIFY_CLIENT_SECRET == "":
        raise RuntimeError("Veuillez remplir le fichier .env avec vos identifiants Spotify")
        