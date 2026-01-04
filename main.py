from fastapi import FastAPI, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List, Optional
import urllib.parse
import os
import requests 
from dotenv import load_dotenv 

# 1. On charge le .env
load_dotenv()

# Imports locaux
from database import create_db_and_tables, get_session
from models import User

# --- Configuration ---
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("⚠️ ERREUR : Clés Spotify introuvables dans le .env")

REDIRECT_URI = "http://127.0.0.1:8000/callback"
SCOPE = "user-read-private user-read-email user-top-read playlist-modify-public playlist-modify-private"

# --- Initialisation ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# --- Modèle de données ---
class PlaylistRequest(BaseModel):
    member_ids: List[str]
    name: str
    description: str
    public: bool
    limit: int
    preferences: Optional[dict] = {}

# --- ROUTES ---

@app.get("/")
def home(request: Request):
    # Affiche l'interface graphique (index.html)
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
def login():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "redirect_uri": REDIRECT_URI,
    }
    url = f"https://accounts.spotify.com/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@app.get("/callback")
def callback(code: str, db: Session = Depends(get_session)):
    # 1. Échange du code
    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(token_url, data=data)
    tokens = response.json()
    
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token:
         return {"error": "Impossible de récupérer le token", "details": tokens}

    # 2. Profil User
    headers = {"Authorization": f"Bearer {access_token}"}
    user_response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    user_info = user_response.json()
    
    spotify_id = user_info["id"]
    
    # 3. Sauvegarde DB
    statement = select(User).where(User.spotify_id == spotify_id)
    existing_user = db.exec(statement).first()

    if existing_user:
        existing_user.access_token = access_token
        if refresh_token: 
            existing_user.refresh_token = refresh_token
        db.add(existing_user)
    else:
        new_user = User(
            spotify_id=spotify_id,
            display_name=user_info.get("display_name"),
            access_token=access_token,
            refresh_token=refresh_token
        )
        db.add(new_user)

    db.commit()
    return RedirectResponse("/")

@app.get("/members")
def get_members(session: Session = Depends(get_session)):
    users = session.exec(select(User)).all()
    members_list = [user.display_name for user in users]
    return {"members": members_list}

@app.post("/generate")
def generate_playlist(data: PlaylistRequest, session: Session = Depends(get_session)):
    admin_user = session.exec(select(User)).first()

    if not admin_user:
        return {"success": False, "error": "Personne n'est connecté."}

    headers = {
        "Authorization": f"Bearer {admin_user.access_token}",
        "Content-Type": "application/json"
    }

    user_id = admin_user.spotify_id
    create_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"

    playlist_data = {
        "name": data.name,
        "description": data.description,
        "public": data.public
    }

    response = requests.post(create_url, headers=headers, json=playlist_data)

    if response.status_code not in [200, 201]:
        return {"success": False, "error": f"Erreur Spotify ({response.status_code}): {response.text}"}

    result = response.json()
    
    return {
        "success": True,
        "track_count": 0,
        "message": "Playlist créée !",
        "url": result['external_urls']['spotify']
    }