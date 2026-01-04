import os
import secrets
from typing import Dict, List

from flask import Flask, jsonify, redirect, request, session, url_for, render_template

from config import APP_SECRET_KEY, assert_config, SPOTIFY_REDIRECT_URI
from group_playlist import generate_group_playlist
from spotify_oauth import get_auth_url, exchange_code_for_token, get_current_user_profile, get_valid_access_token
from store import init_db, upsert_member, list_member_ids, get_member_tokens, update_member_tokens

from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import create_db_and_tables  # Importe ta fonction
from models import User # Importe ton modèle pour qu'il soit détecté

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Au démarrage de l'app, on crée les tables
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message": "L'API tourne et la DB est connectée !"}
# --- SCOPES NÉCESSAIRES POUR SPOTIFY ---
SCOPES = "user-top-read user-read-recently-played playlist-modify-public playlist-modify-private user-read-private user-read-email"


def create_app() -> Flask:
    assert_config()
    app = Flask(__name__)
    app.secret_key = APP_SECRET_KEY

    # Initialisation de la base SQLite
    init_db()

    # ------------------------
    #         ROUTE /
    # ------------------------
    @app.get("/")
    def root():
        return jsonify({"ok": True, "routes": ["/login", "/callback", "/members", "/generate", "/test-spotify"]})

    # ------------------------
    #   DEBUG CONFIG SPOTIFY
    # ------------------------
    @app.get("/debug-config")
    def debug_config():
        state = "debug"
        auth_preview = get_auth_url(state=state, scopes=SCOPES)
        return jsonify({
            "redirect_uri_config": SPOTIFY_REDIRECT_URI,
            "auth_url_preview": auth_preview,
        })

    # ------------------------
    #   UI HTML
    # ------------------------
    @app.get("/ui")
    def ui():
        return render_template("ui.html")

    # ------------------------
    #         LOGIN
    # ------------------------
    @app.get("/login")
    def login():
        state = secrets.token_urlsafe(16)
        session["oauth_state"] = state
        return redirect(get_auth_url(state=state, scopes=SCOPES))

    # ------------------------
    #        CALLBACK
    # ------------------------
    @app.get("/callback")
def callback(code: str, db: Session = Depends(get_session)):
    """
    Cette fonction reçoit le code de Spotify, récupère le token,
    et enregistre/met à jour l'utilisateur dans la Base de Données.
    """
    
    # 1. Vérification basique (FastAPI gère le 'code' manquant automatiquement avec le type str)
    if not code:
        raise HTTPException(status_code=400, detail="Pas de code reçu de Spotify")

    # 2. Récupération des tokens (On garde ta logique existante)
    # Assure-toi que cette fonction est bien accessible ici
    tokens = exchange_code_for_token(code) 
    
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token") # Important de le récupérer aussi !

    if not access_token:
        raise HTTPException(status_code=400, detail="Pas de access_token renvoyé")

    # 3. Récupérer le profil Spotify (On garde ta logique)
    try:
        profile = get_current_user_profile(access_token)
    except Exception as e:
        print(f"Erreur API Spotify: {e}")
        raise HTTPException(status_code=401, detail="Impossible de récupérer le profil")

    spotify_user_id = profile.get("id")
    display_name = profile.get("display_name")

    # --- C'EST ICI QUE LA MAGIE DB OPÈRE (Remplacement de upsert_member) ---
    
    # A. On cherche si l'utilisateur existe déjà dans la DB
    statement = select(User).where(User.spotify_id == spotify_user_id)
    existing_user = db.exec(statement).first()

    if existing_user:
        # B. IL EXISTE : On met à jour ses tokens (au cas où ils ont changé)
        existing_user.access_token = access_token
        existing_user.refresh_token = refresh_token
        existing_user.display_name = display_name # On met à jour le nom au cas où
        db.add(existing_user)
        print(f"🔄 Utilisateur {display_name} mis à jour.")
    else:
        # C. NOUVEAU : On crée l'utilisateur
        new_user = User(
            spotify_id=spotify_user_id,
            display_name=display_name,
            access_token=access_token,
            refresh_token=refresh_token
        )
        db.add(new_user)
        print(f"✨ Nouvel utilisateur créé : {display_name}")

    # D. On valide la transaction (Sauvegarde réelle)
    db.commit()
    
    # -----------------------------------------------------------------------

    # 4. Redirection vers l'interface (FastAPI way)
    return RedirectResponse(url="http://localhost:3000/ui") # Ou juste "/ui" selon ton frontend


    # ------------------------
    #     LISTE DES MEMBRES
    # ------------------------
    @app.get("/members")
    def members():
        return jsonify({"members": list_member_ids()})
    
    # ------------------------
    #     TEST SPOTIFY API
    # ------------------------
    @app.get("/test-spotify")
    def test_spotify():
        member_ids = list_member_ids()
        if not member_ids:
            return jsonify({"error": "Aucun membre connecté"})
        
        owner_id = member_ids[0]
        tokens = get_member_tokens(owner_id)
        access = get_valid_access_token(tokens)
        
        # Test 1: Récupérer le profil
        try:
            profile = get_current_user_profile(access)
            user_id = profile.get("id")
        except Exception as e:
            return jsonify({"error": f"Profil error: {e}"})
        
        # Test 2: Récupérer les top tracks
        from group_playlist import _get_top_items
        top_tracks = _get_top_items(access, "tracks", limit=5)
        top_artists = _get_top_items(access, "artists", limit=5)
        
        return jsonify({
            "user_id": user_id,
            "top_tracks_count": len(top_tracks),
            "top_artists_count": len(top_artists),
            "top_tracks": [t.get("name") for t in top_tracks],
            "top_artists": [a.get("name") for a in top_artists]
        })

    # ------------------------
    #     GÉNÉRATION PLAYLIST
    # ------------------------
    @app.post("/generate")
    def generate():
        payload = request.get_json(force=True, silent=True) or {}
        member_ids: List[str] = payload.get("member_ids", [])
        name: str = payload.get("name", "Ma Playlist de Groupe")
        description: str = payload.get("description", "Generee automatiquement")
        public: bool = bool(payload.get("public", False))
        preferences = payload.get("preferences", {})

        if not member_ids:
            return jsonify({"error": "member_ids requis"}), 400

        owner_id = member_ids[0]

        # Vérifier/rafraîchir token du propriétaire
        owner_tokens = get_member_tokens(owner_id) or {}
        owner_access = get_valid_access_token(owner_tokens)
        if not owner_access:
            return jsonify({"error": "Token proprietaire invalide"}), 401

        # Récupère le profil pour avoir l'ID Spotify réel
        try:
            profile = get_current_user_profile(owner_access)
            spotify_user_id = profile.get("id")
            if not spotify_user_id:
                return jsonify({"error": "Impossible de récupérer l'ID Spotify du propriétaire"}), 400
        except Exception as e:
            print(f"Erreur lors de la récupération du profil : {e}")
            return jsonify({"error": "Erreur lors de la récupération du profil utilisateur"}), 500

        # Vérifier/rafraîchir les autres tokens
        member_tokens = []
        for mid in member_ids[1:]:  # On commence à 1 car le premier est le owner
            t = get_member_tokens(mid) or {}
            access = get_valid_access_token(t)
            if not access:
                return jsonify({"error": f"Token invalide pour {mid}"}), 401

            update_member_tokens(mid, t)
            member_tokens.append(access)

        # Lancer la génération de la playlist
        result = generate_group_playlist(
            owner_access_token=owner_access,
            owner_user_id=spotify_user_id,  # ✅ AJOUT DU PARAMÈTRE MANQUANT
            member_tokens=member_tokens,
            name=name,
            description=description,
            public=public,
            preferences=preferences,
        )

        if "error" in result:
            return jsonify(result), 500

        return jsonify(result)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5050)
