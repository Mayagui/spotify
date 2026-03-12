import os
import secrets
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

# FastAPI & Tools
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Tes modules locaux
from config import APP_SECRET_KEY, assert_config, SPOTIFY_REDIRECT_URI
from group_playlist import generate_group_playlist
from spotify_oauth import get_auth_url, exchange_code_for_token, get_current_user_profile, get_valid_access_token
from database import create_db_and_tables, get_session
from models import User, Track, UserFeedback, ListeningHistory, Room, RoomMember
from recommendation_service import RecommendationService

# --- CONFIGURATION ---
SCOPES = "user-top-read user-read-recently-played playlist-modify-public playlist-modify-private user-read-private user-read-email"
templates = Jinja2Templates(directory="templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialisation au démarrage
    assert_config()
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# ------------------------
#         MODELS PYDANTIC
# ------------------------

class FeedbackRequest(BaseModel):
    track_id: str  # Spotify ID
    feedback_type: str  # "like", "skip", "dislike"

class PlaylistGenerateRequest(BaseModel):
    member_ids: List[str]
    room_id: Optional[str] = None
    name: str = "Ma Playlist de Groupe"
    description: str = "Générée automatiquement"
    public: bool = False
    limit: int = 30
    preferences: Dict[str, Any] = {}

# ------------------------
#         ROUTES
# ------------------------

@app.get("/")
def root():
    return {
        "ok": True, 
        "message": "L'API FastAPI tourne !",
        "routes": ["/login", "/callback", "/members", "/generate", "/ui", "/feedback", "/recommendations"]
    }

@app.get("/ui", response_class=HTMLResponse)
def ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/debug-config")
def debug_config():
    return {
        "redirect_uri_config": SPOTIFY_REDIRECT_URI,
        "auth_url_preview": get_auth_url(state="debug", scopes=SCOPES),
    }

@app.get("/login")
def login(request: Request):
    state = secrets.token_urlsafe(16)
    response = RedirectResponse(url=get_auth_url(state=state, scopes=SCOPES))
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        max_age=300,  # 5 minutes : largement suffisant pour finir le flow OAuth
    )
    return response

@app.get("/callback")
def callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_session),
):
    # Gérer les erreurs OAuth (utilisateur refuse, etc.)
    if error:
        error_msg = error_description or error
        logger.error(f"Erreur OAuth: {error} - {error_msg}")
        return RedirectResponse(url=f"/ui?error={error}&error_description={error_msg}")

    # Vérifier le state anti-CSRF :
    # Le state reçu de Spotify doit correspondre à celui qu'on a mis dans le cookie au moment du /login.
    # Si ce n'est pas le cas, c'est une tentative d'attaque ou une requête invalide.
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or state != expected_state:
        logger.error(f"State OAuth invalide (reçu: {state!r}, attendu: {expected_state!r})")
        return RedirectResponse(url="/ui?error=invalid_state&error_description=Requête invalide, veuillez réessayer")

    # Vérifier que le code est présent
    if not code:
        logger.error("Pas de code reçu de Spotify")
        return RedirectResponse(url="/ui?error=no_code&error_description=Autorisation annulée ou code manquant")

    # Récupération des tokens
    tokens = exchange_code_for_token(code) 
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token:
        raise HTTPException(status_code=400, detail="Échec de récupération du token")

    # Récupérer le profil Spotify
    try:
        profile = get_current_user_profile(access_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Erreur Spotify: {str(e)}")

    spotify_user_id = profile.get("id")
    display_name = profile.get("display_name")
    profile_image = profile.get("images", [{}])[0].get("url") if profile.get("images") else None

    # Mise à jour de la Base de Données
    statement = select(User).where(User.spotify_id == spotify_user_id)
    existing_user = db.exec(statement).first()

    if existing_user:
        existing_user.access_token = access_token
        existing_user.refresh_token = refresh_token
        existing_user.display_name = display_name
        if profile_image:
            existing_user.profile_image = profile_image
        db.add(existing_user)
    else:
        new_user = User(
            spotify_id=spotify_user_id,
            display_name=display_name,
            access_token=access_token,
            refresh_token=refresh_token,
            profile_image=profile_image
        )
        db.add(new_user)

    db.commit()

    response = RedirectResponse(url="/ui")
    # Cookie utilisé pour identifier l'utilisateur courant (rooms, etc.)
    response.set_cookie(
        key="spotify_user_id",
        value=spotify_user_id,
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        max_age=60 * 60 * 24 * 30,  # 30 jours
    )
    # Supprimer le cookie anti-CSRF : il a rempli son rôle
    response.delete_cookie("oauth_state")
    return response

@app.post("/rooms")
def create_room(request: Request, db: Session = Depends(get_session)):
    """Crée une nouvelle room et retourne son code partageable."""
    spotify_user_id = request.cookies.get("spotify_user_id")
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Non connecté")

    # Générer un code court et lisible, ex: "A3X9KL"
    room_code = secrets.token_urlsafe(4).upper()[:6]

    # S'assurer de l'unicité (collision très improbable mais on vérifie)
    while db.exec(select(Room).where(Room.room_code == room_code)).first():
        room_code = secrets.token_urlsafe(4).upper()[:6]

    room = Room(room_code=room_code, creator_spotify_id=spotify_user_id)
    db.add(room)
    db.commit()
    db.refresh(room)

    # Le créateur rejoint automatiquement sa room
    db.add(RoomMember(room_id=room.id, spotify_id=spotify_user_id))
    db.commit()

    return {"room_code": room_code}


@app.post("/rooms/{room_code}/join")
def join_room(room_code: str, request: Request, db: Session = Depends(get_session)):
    """Permet à l'utilisateur connecté de rejoindre une room existante."""
    spotify_user_id = request.cookies.get("spotify_user_id")
    if not spotify_user_id:
        raise HTTPException(status_code=401, detail="Non connecté")

    room = db.exec(select(Room).where(Room.room_code == room_code)).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room introuvable")

    # N'ajouter que si pas déjà membre
    already = db.exec(
        select(RoomMember).where(
            RoomMember.room_id == room.id,
            RoomMember.spotify_id == spotify_user_id
        )
    ).first()
    if not already:
        db.add(RoomMember(room_id=room.id, spotify_id=spotify_user_id))
        db.commit()

    return {"room_code": room_code, "joined": True}


@app.get("/members")
def members(room_code: Optional[str] = None, db: Session = Depends(get_session)):
    """Retourne la liste des membres. Si room_code fourni, filtre par room."""
    if room_code:
        room = db.exec(select(Room).where(Room.room_code == room_code)).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room introuvable")

        room_members = db.exec(
            select(RoomMember).where(RoomMember.room_id == room.id)
        ).all()
        member_ids = [m.spotify_id for m in room_members]

        users = db.exec(
            select(User).where(User.spotify_id.in_(member_ids))
        ).all() if member_ids else []
    else:
        users = db.exec(select(User)).all()

    return {
        "members": [
            {
                "spotify_id": user.spotify_id,
                "display_name": user.display_name,
                "profile_image": user.profile_image
            }
            for user in users
        ]
    }

@app.post("/generate")
async def generate(request: PlaylistGenerateRequest, db: Session = Depends(get_session)):
    """Génère une playlist de groupe avec recommandation avancée"""
    # Déterminer la liste des membres à partir de la room ou de member_ids
    member_ids = request.member_ids or []

    # Si un room_code est fourni, on récupère les membres depuis la DB
    if request.room_id:
        room = db.exec(select(Room).where(Room.room_code == request.room_id)).first()
        if room:
            room_members = db.exec(
                select(RoomMember).where(RoomMember.room_id == room.id)
            ).all()
            if room_members:
                member_ids = [m.spotify_id for m in room_members]

    # Si toujours aucune liste de membres, utiliser tous les utilisateurs connectés
    if not member_ids:
        users = db.exec(select(User)).all()
        if not users:
            raise HTTPException(status_code=400, detail="Aucun utilisateur connecté")
        member_ids = [user.spotify_id for user in users]
    
    if not member_ids:
        raise HTTPException(status_code=400, detail="member_ids requis")

    # On met à jour l'objet de requête pour que le reste de la logique
    # continue de fonctionner avec la bonne liste de membres
    request.member_ids = member_ids

    owner_id = request.member_ids[0]
    
    # Récupérer l'utilisateur propriétaire depuis la DB
    owner_statement = select(User).where(User.spotify_id == owner_id)
    owner_user = db.exec(owner_statement).first()
    
    if not owner_user:
        raise HTTPException(status_code=404, detail=f"Utilisateur {owner_id} non trouvé")
    
    # Obtenir un token valide pour le propriétaire
    owner_tokens = {"access_token": owner_user.access_token, "refresh_token": owner_user.refresh_token}
    owner_access = get_valid_access_token(owner_tokens)
    
    if not owner_access:
        raise HTTPException(status_code=401, detail="Token propriétaire invalide")
    
    # Récupérer les tokens de tous les autres membres
    member_tokens = []
    for member_id in request.member_ids[1:]:  # Skip owner
        member_statement = select(User).where(User.spotify_id == member_id)
        member_user = db.exec(member_statement).first()
        if member_user:
            member_tokens_dict = {"access_token": member_user.access_token, "refresh_token": member_user.refresh_token}
            access = get_valid_access_token(member_tokens_dict)
            if access:
                member_tokens.append(access)
            else:
                logger.warning(f"Token invalide pour membre {member_id}")
    
    # Lancement de la génération avec session DB
    result = generate_group_playlist(
        owner_access_token=owner_access,
        owner_user_id=owner_id,
        member_tokens=member_tokens,
        name=request.name,
        description=request.description,
        public=request.public,
        preferences=request.preferences,
        session=db,
        limit=request.limit
    )
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result

@app.post("/feedback")
def add_feedback(feedback: FeedbackRequest, spotify_user_id: str, db: Session = Depends(get_session)):
    """Enregistre un feedback utilisateur (like/skip/dislike)"""
    # Récupérer l'utilisateur
    statement = select(User).where(User.spotify_id == spotify_user_id)
    user = db.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    # Récupérer ou créer le Track
    track_statement = select(Track).where(Track.spotify_id == feedback.track_id)
    track = db.exec(track_statement).first()
    
    if not track:
        # Créer un track minimal si pas encore en DB
        track = Track(
            spotify_id=feedback.track_id,
            name="Unknown",
            artist="Unknown"
        )
        db.add(track)
        db.commit()
        db.refresh(track)
    
    # Vérifier si feedback existe déjà
    existing_feedback = db.exec(
        select(UserFeedback).where(
            UserFeedback.user_id == user.id,
            UserFeedback.track_id == track.id
        )
    ).first()
    
    if existing_feedback:
        existing_feedback.feedback_type = feedback.feedback_type
        db.add(existing_feedback)
    else:
        new_feedback = UserFeedback(
            user_id=user.id,
            track_id=track.id,
            feedback_type=feedback.feedback_type
        )
        db.add(new_feedback)
    
    db.commit()
    
    return {
        "success": True,
        "message": f"Feedback '{feedback.feedback_type}' enregistré"
    }

@app.get("/recommendations/{spotify_user_id}")
def get_personal_recommendations(spotify_user_id: str, limit: int = 20, db: Session = Depends(get_session)):
    """Retourne recommandations personnalisées pour un utilisateur"""
    statement = select(User).where(User.spotify_id == spotify_user_id)
    user = db.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    rec_service = RecommendationService(db)
    
    # Récupérer les top tracks de l'utilisateur comme seeds
    tokens = {"access_token": user.access_token, "refresh_token": user.refresh_token}
    access_token = get_valid_access_token(tokens)
    
    if not access_token:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    from group_playlist import _get_top_items
    top_tracks = _get_top_items(access_token, "tracks", limit=20)
    seed_tracks = [t['id'] for t in top_tracks[:10]]
    candidate_tracks = [t['id'] for t in top_tracks]
    
    # Générer recommandations collaboratives
    collab_track_ids = rec_service.collaborative_recommendations(user.id, top_k=limit)
    tracks_dict = {t.id: t.spotify_id for t in db.exec(select(Track)).all()}
    collab_recs = [tracks_dict.get(tid, "") for tid in collab_track_ids if tid in tracks_dict]
    
    # Si pas assez de recommandations collaboratives, compléter avec content-based
    if len(collab_recs) < limit and seed_tracks:
        content_recs = rec_service.content_based_recommendations(
            seed_tracks, access_token, candidate_tracks, top_k=limit - len(collab_recs)
        )
        collab_recs.extend([r for r in content_recs if r not in collab_recs])
    
    return {
        "user_id": spotify_user_id,
        "recommendations": collab_recs[:limit],
        "count": len(collab_recs[:limit])
    }

@app.get("/stats/{spotify_user_id}")
def get_user_stats(spotify_user_id: str, db: Session = Depends(get_session)):
    """Retourne les statistiques d'un utilisateur"""
    statement = select(User).where(User.spotify_id == spotify_user_id)
    user = db.exec(statement).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    likes_count = db.exec(
        select(UserFeedback).where(
            UserFeedback.user_id == user.id,
            UserFeedback.feedback_type == "like"
        )
    ).all()
    
    return {
        "user_id": spotify_user_id,
        "display_name": user.display_name,
        "total_likes": len(likes_count),
        "total_tracks_in_db": db.exec(select(Track)).all().__len__()
    }
