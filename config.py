import os

from dotenv import load_dotenv


load_dotenv()


SPOTIFY_CLIENT_ID: str = os.getenv("SPOTIFY_CLIENT_ID", "9461acee2c2d46578eb2da910369b74f")
SPOTIFY_CLIENT_SECRET: str = os.getenv("SPOTIFY_CLIENT_SECRET", "afd28405b83e4453806a8dc4550f5728")
SPOTIFY_REDIRECT_URI: str = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:5050/callback")
APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "dev-secret")


def assert_config() -> None:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET manquants. Configurez votre .env")

