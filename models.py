from typing import Optional
from sqlmodel import Field, SQLModel

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    spotify_id: str = Field(index=True, unique=True)
    display_name: str
    
    # Nouveaux champs pour stocker l'accès
    access_token: str
    refresh_token: str
    profile_image: Optional[str] = None
