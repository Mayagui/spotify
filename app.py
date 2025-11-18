import os
import secrets
from typing import Dict, List

from flask import Flask, jsonify, redirect, request, session, url_for, render_template

from config import APP_SECRET_KEY, assert_config, SPOTIFY_REDIRECT_URI
from group_playlist import create_playlist, add_tracks_to_playlist, generate_group_playlist
from spotify_oauth import get_auth_url, exchange_code_for_token, get_current_user_profile, get_valid_access_token
from store import init_db, upsert_member, list_member_ids, get_member_tokens, update_member_tokens


SCOPES = "user-top-read playlist-modify-private"


def create_app() -> Flask:
    assert_config()
    app = Flask(__name__)
    app.secret_key = APP_SECRET_KEY
    # Init DB
    init_db()

    @app.get("/")
    def root():
        return jsonify({"ok": True, "routes": ["/login", "/callback", "/members", "/generate"]})

    @app.get("/debug-config")
    def debug_config():
        state = "debug"
        auth_preview = get_auth_url(state=state, scopes=SCOPES)
        return jsonify({
            "redirect_uri_config": SPOTIFY_REDIRECT_URI,
            "auth_url_preview": auth_preview,
        })

    @app.get("/ui")
    def ui():
        return render_template("ui.html")

    @app.get("/login")
    def login():
        state = secrets.token_urlsafe(16)
        session["oauth_state"] = state
        return redirect(get_auth_url(state=state, scopes=SCOPES))

    @app.get("/callback")
    def callback():
        error = request.args.get("error")
        if error:
            return jsonify({"error": error}), 400
        state = request.args.get("state")
        code = request.args.get("code")
        if not code or not state or state != session.get("oauth_state"):
            return jsonify({"error": "state/code invalide"}), 400

        tokens = exchange_code_for_token(code)
        access = tokens.get("access_token")
        profile = get_current_user_profile(access)
        spotify_user_id = profile.get("id")
        if not spotify_user_id:
            return jsonify({"error": "Impossible de recuperer l'identifiant Spotify de l'utilisateur"}), 400

        upsert_member(spotify_user_id, tokens)
        return jsonify({"message": "Utilisateur ajoute", "spotify_user_id": spotify_user_id})

    @app.get("/members")
    def members():
        return jsonify({"members": list_member_ids()})

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
        existing = set(list_member_ids())
        missing = [mid for mid in member_ids if mid not in existing]
        if missing:
            return jsonify({"error": "Membres inconnus", "missing": missing}), 400

        # Rafraichir tokens si besoin
        owner_tokens = get_member_tokens(owner_id) or {}
        owner_access = get_valid_access_token(owner_tokens)
        if not owner_access:
            return jsonify({"error": "Token proprietaire invalide"}), 401
        member_tokens = []
        for mid in member_ids:
            t = get_member_tokens(mid) or {}
            access = get_valid_access_token(t)
            if not access:
                return jsonify({"error": f"Token invalide pour {mid}"}), 401
            # Persiste tout refresh
            update_member_tokens(mid, t)
            member_tokens.append(access)

        # 1. Generation recommandations
        rec = generate_group_playlist(
            owner_access_token=owner_access,
            member_tokens=member_tokens,
            name=name,
            description=description,
            public=public,
            preferences=preferences,
        )

        # 2. VÉRIFICATION D'ERREUR (nouvelle étape cruciale)
        if "error" in rec:
            # L'erreur (token expiré, pas de seed, etc.) est gérée dans group_playlist.py
            return jsonify({"error": f"Erreur de génération Spotify: {rec['error']}"}), 500
        
        # 3. Création playlist et ajout des titres (SÛR car 'rec' contient 'uris')
        owner_profile = get_current_user_profile(owner_access)
        owner_spotify_id = owner_profile.get("id")
        
        # Vérification supplémentaire au cas où le profil échouerait (rare, mais prudent)
        if not owner_spotify_id:
            return jsonify({"error": "Impossible de récupérer l'ID Spotify du propriétaire pour la création de la playlist."}), 500
            
        playlist_id = create_playlist(owner_access, owner_spotify_id, name, description, public)
        add_tracks_to_playlist(owner_access, playlist_id, rec["uris"])

        return jsonify({
            "playlist_id": playlist_id,
            "added": len(rec["uris"]),
            "seeds": {"tracks": rec["seed_tracks"], "artists": rec["seed_artists"]},
            "targets": {"energy": rec["target_energy"], "valence": rec["target_valence"]},
        })

    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True, port=5050) # Force le port à 5050
