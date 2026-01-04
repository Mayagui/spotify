from sqlmodel import SQLModel, create_engine, Session

# C'est l'adresse de ta base de données qu'on vient de lancer avec Docker
DATABASE_URL = "postgresql://postgres:password@localhost:5432/spotify_db"

engine = create_engine(DATABASE_URL)

def create_db_and_tables():
    """Crée les tables dans la base de données"""
    SQLModel.metadata.create_all(engine)

def get_session():
    """Dépendance pour récupérer une session de DB dans FastAPI"""
    with Session(engine) as session:
        yield session
