from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime

class User(SQLModel, table=True):
    __tablename__ = "spotify_users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    spotify_id: str = Field(unique=True, index=True)
    display_name: Optional[str] = None
    access_token: str
    refresh_token: str
    profile_image: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Relations
    feedbacks: List["UserFeedback"] = Relationship(back_populates="user")
    listening_history: List["ListeningHistory"] = Relationship(back_populates="user")


class Track(SQLModel, table=True):
    __tablename__ = "tracks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    spotify_id: str = Field(unique=True, index=True)
    name: str
    artist: str
    album: Optional[str] = None
    # Audio features (de Spotify API)
    danceability: Optional[float] = None
    energy: Optional[float] = None
    valence: Optional[float] = None
    tempo: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    speechiness: Optional[float] = None
    key: Optional[int] = None
    mode: Optional[int] = None
    time_signature: Optional[int] = None
    popularity: Optional[int] = None
    genres: Optional[str] = None  # JSON array as string
    duration_ms: Optional[int] = None
    
    feedbacks: List["UserFeedback"] = Relationship(back_populates="track")
    listening_history: List["ListeningHistory"] = Relationship(back_populates="track")


class UserFeedback(SQLModel, table=True):
    __tablename__ = "user_feedback"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="spotify_users.id")
    track_id: int = Field(foreign_key="tracks.id")
    feedback_type: str  # "like", "skip", "dislike"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    user: User = Relationship(back_populates="feedbacks")
    track: Track = Relationship(back_populates="feedbacks")


class ListeningHistory(SQLModel, table=True):
    __tablename__ = "listening_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="spotify_users.id")
    track_id: int = Field(foreign_key="tracks.id")
    played_at: datetime
    duration_ms: Optional[int] = None

    user: User = Relationship(back_populates="listening_history")
    track: Track = Relationship(back_populates="listening_history")


class Room(SQLModel, table=True):
    __tablename__ = "rooms"

    id: Optional[int] = Field(default=None, primary_key=True)
    # Code court partageable entre amis, ex: "A3X9KL"
    room_code: str = Field(unique=True, index=True)
    creator_spotify_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RoomMember(SQLModel, table=True):
    __tablename__ = "room_members"

    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="rooms.id")
    spotify_id: str
    joined_at: datetime = Field(default_factory=datetime.utcnow)
