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
import random

load_dotenv()

from database import create_db_and_tables, get_session
from models import User

# --- Configuration ---
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError("⚠️ ERREUR : Clés Spotify introuvables dans le .env")

REDIRECT_URI = "http://127.0.0.1:8000/callback"
SCOPE = "user-read-private user-read-email user-top-read playlist-modify-public playlist-modify-private"

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

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

    headers = {"Authorization": f"Bearer {access_token}"}
    user_response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    user_info = user_response.json()
    
    spotify_id = user_info["id"]
    
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

# 🎵 NOUVELLE FONCTION : Récupérer les top tracks d'un utilisateur
def get_user_top_tracks(access_token: str, limit: int = 20):
    """Récupère les morceaux préférés d'un utilisateur"""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # On récupère les top tracks sur une période moyenne (6 mois)
    url = f"https://api.spotify.com/v1/me/top/tracks?limit={limit}&time_range=medium_term"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        # On retourne uniquement les URIs des tracks
        return [track['uri'] for track in data.get('items', [])]
    return []

# 🎵 NOUVELLE FONCTION : Fusionner les goûts de plusieurs utilisateurs
def merge_tracks(all_tracks: List[List[str]], limit: int) -> List[str]:
    """
    Mélange intelligemment les tracks de plusieurs utilisateurs
    en alternant équitablement entre chaque membre
    """
    merged = []
    max_length = max(len(tracks) for tracks in all_tracks) if all_tracks else 0
    
    # On alterne entre les utilisateurs pour une distribution équitable
    for i in range(max_length):
        for user_tracks in all_tracks:
            if i < len(user_tracks) and len(merged) < limit:
                track = user_tracks[i]
                # On évite les doublons
                if track not in merged:
                    merged.append(track)
    
    # Mélange léger pour plus de variété
    random.shuffle(merged)
    
    return merged[:limit]

@app.post("/generate")
def generate_playlist(data: PlaylistRequest, session: Session = Depends(get_session)):
    # 1. Récupérer tous les utilisateurs
    users = session.exec(select(User)).all()
    
    if not users:
        return {"success": False, "error": "Aucun utilisateur connecté."}
    
    # 2. Utiliser le premier user comme admin (créateur de la playlist)
    admin_user = users[0]
    
    headers = {
        "Authorization": f"Bearer {admin_user.access_token}",
        "Content-Type": "application/json"
    }
    
    # 3. Créer la playlist vide
    user_id = admin_user.spotify_id
    create_url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
    
    playlist_data = {
        "name": data.name,
        "description": data.description,
        "public": data.public
    }
    
    response = requests.post(create_url, headers=headers, json=playlist_data)
    
    if response.status_code not in [200, 201]:
        return {"success": False, "error": f"Erreur création playlist: {response.text}"}
    
    playlist_info = response.json()
    playlist_id = playlist_info['id']
    
    # 4. 🎵 MAGIE : Récupérer les top tracks de chaque membre
    all_tracks = []
    for user in users:
        user_tracks = get_user_top_tracks(user.access_token, limit=data.limit)
        if user_tracks:
            all_tracks.append(user_tracks)
    
    if not all_tracks:
        return {
            "success": True,
            "track_count": 0,
            "message": "Playlist créée mais aucun morceau trouvé dans les favoris des membres.",
            "url": playlist_info['external_urls']['spotify']
        }
    
    # 5. Fusionner les tracks de manière intelligente
    final_tracks = merge_tracks(all_tracks, data.limit)
    
    # 6. Ajouter les tracks à la playlist
    add_tracks_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    add_response = requests.post(
        add_tracks_url, 
        headers=headers, 
        json={"uris": final_tracks}
    )
    
    if add_response.status_code not in [200, 201]:
        return {
            "success": False, 
            "error": f"Playlist créée mais erreur lors de l'ajout des morceaux: {add_response.text}"
        }
    
    # 7. Succès ! 🎉
    return {
        "success": True,
        "track_count": len(final_tracks),
        "message": f"Playlist créée avec {len(final_tracks)} morceaux des goûts de {len(users)} membre(s) !",
        "url": playlist_info['external_urls']['spotify']
    }