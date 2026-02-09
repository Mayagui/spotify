from sqlmodel import SQLModel, create_engine, Session
import os

# Utiliser SQLite pour le développement (plus simple)
# Pour PostgreSQL en production, utilisez: "postgresql://user:password@localhost:5432/spotify_db"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./spotify.db")

engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    """Crée toutes les tables définies dans models.py"""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Fournit une session de base de données pour les dépendances FastAPI"""
    with Session(engine) as session:
        yield session
