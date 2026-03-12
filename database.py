from sqlmodel import SQLModel, create_engine, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./spotify.db")

# pool_pre_ping=True : vérifie la connexion avant chaque requête.
# Indispensable avec PostgreSQL pour survivre aux redémarrages du conteneur.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, connect_args=connect_args)

def create_db_and_tables():
    """Crée toutes les tables définies dans models.py"""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Fournit une session de base de données pour les dépendances FastAPI"""
    with Session(engine) as session:
        yield session
