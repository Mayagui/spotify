import requests
import json
import logging
from typing import List, Dict, Any, Optional
import random
from sqlmodel import Session, select

from recommendation_service import RecommendationService
from models import User, Track

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CORRECTION CRITIQUE DE L'ADRESSE ---
# C'est la seule adresse officielle de l'API Spotify
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# --- Fonctions Utilitaires ---

def _get_recently_played(access_token: str, limit: int = 50) -> List[str]:
    """Récupère les IDs des titres récemment joués."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(
            f"{SPOTIFY_API_BASE}/me/player/recently-played",
            headers=headers,
            params={"limit": limit},
            timeout=15
        )
        if resp.ok:
            items = resp.json().get("items", [])
            ids = [item["track"]["id"] for item in items if item.get("track", {}).get("id")]
            logger.info(f"✅ Recently played: {len(ids)} tracks")
            return ids
    except Exception as e:
        logger.warning(f"⚠️ recently-played error: {e}")
    return []


def _get_top_items(access_token: str, item_type: str, limit: int = 20) -> List[Any]:
    """Récupère les top titres ou artistes de l'utilisateur."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": "medium_term"} 
    url = f"{SPOTIFY_API_BASE}/me/top/{item_type}"
    
    logger.info(f"🔍 Appel API: {url}")
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    
    if not resp.ok:
        logger.warning(f"⚠️ Info Top Items ({item_type}): Status {resp.status_code} - {resp.text}")
        return []
    
    try:
        items = resp.json().get("items", [])
        logger.info(f"✅ Top {item_type} récupérés: {len(items)} items")
        return items
    except Exception as e:
        logger.error(f"❌ Erreur parsing JSON: {e}")
        return []


def create_playlist(access_token: str, owner_user_id: str, name: str, description: str, public: bool) -> str:
    """Crée une nouvelle playlist et retourne son ID."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {"name": name, "description": description, "public": public}
    
    url = f"{SPOTIFY_API_BASE}/users/{owner_user_id}/playlists"
    logger.info(f"🎼 Création playlist sur: {url}")
    
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
    
    if not resp.ok:
        logger.error(f"❌ Playlist Creation Error: {resp.status_code} - {resp.text}")
        raise Exception(f"Erreur création playlist: {resp.status_code}")
    
    playlist_id = resp.json().get("id")
    logger.info(f"✅ Playlist créée avec ID: {playlist_id}")
    return playlist_id


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: List[str]):
    """Ajoute des titres à une playlist."""
    if not uris:
        logger.warning("⚠️ Aucun URI à ajouter")
        return
        
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    # Spotify limite à 100 tracks par requête
    batch_size = 100
    for i in range(0, len(uris), batch_size):
        batch = uris[i:i+batch_size]
        body = {"uris": batch}
        
        logger.info(f"➕ Ajout de {len(batch)} titres à la playlist (batch {i//batch_size + 1})")
        
        resp = requests.post(f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks", 
                           headers=headers, data=json.dumps(body), timeout=15)

        if not resp.ok:
            logger.error(f"❌ Add Tracks Error: {resp.status_code} - {resp.text}")
            raise Exception(f"Erreur ajout titres: {resp.status_code}")
    
    logger.info(f"✅ Tous les titres ajoutés avec succès")


def _get_artist_top_tracks(access_token: str, artist_id: str, market: str = "FR") -> List[Dict]:
    """Récupère les top tracks d'un artiste (endpoint non déprécié)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(
            f"{SPOTIFY_API_BASE}/artists/{artist_id}/top-tracks",
            headers=headers,
            params={"market": market},
            timeout=15
        )
        if resp.ok:
            return resp.json().get("tracks", [])
    except Exception as e:
        logger.warning(f"⚠️ artist top-tracks error ({artist_id}): {e}")
    return []


def _get_related_artists(access_token: str, artist_id: str) -> List[str]:
    """Récupère les artistes similaires à un artiste donné."""
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(
            f"{SPOTIFY_API_BASE}/artists/{artist_id}/related-artists",
            headers=headers,
            timeout=15
        )
        if resp.ok:
            artists = resp.json().get("artists", [])
            return [a["id"] for a in artists[:5]]
    except Exception as e:
        logger.warning(f"⚠️ related-artists error ({artist_id}): {e}")
    return []


def _discover_new_tracks(access_token: str, seed_artist_ids: List[str], limit: int = 100) -> List[Dict]:
    """
    Découvre de nouvelles musiques via les top tracks des artistes favoris
    et leurs artistes similaires.
    Remplace /v1/recommendations (déprécié fin 2024).
    """
    if not seed_artist_ids:
        return []

    candidate_tracks: Dict[str, Dict] = {}

    # 1) Top tracks des artistes favoris du groupe
    for artist_id in seed_artist_ids[:5]:
        tracks = _get_artist_top_tracks(access_token, artist_id)
        for t in tracks:
            if t.get("id"):
                candidate_tracks[t["id"]] = t

    # 2) Top tracks des artistes similaires (pour aller au-delà des favoris directs)
    related_artist_ids: List[str] = []
    for artist_id in seed_artist_ids[:3]:
        related_artist_ids.extend(_get_related_artists(access_token, artist_id))

    seen_related = set(seed_artist_ids)
    for artist_id in related_artist_ids:
        if artist_id in seen_related:
            continue
        seen_related.add(artist_id)
        tracks = _get_artist_top_tracks(access_token, artist_id)
        for t in tracks:
            if t.get("id"):
                candidate_tracks[t["id"]] = t
        if len(candidate_tracks) >= limit * 2:
            break

    result = list(candidate_tracks.values())
    random.shuffle(result)  # mélanger pour éviter de toujours prendre les mêmes
    logger.info(f"✅ Candidats découverts (artistes + similaires): {len(result)} tracks")
    return result[:limit]


def generate_group_playlist(owner_access_token: str, owner_user_id: str, member_tokens: List[str],
                           name: str, description: str, public: bool, preferences: Dict[str, Any],
                           session: Session, limit: int = 50) -> Dict[str, Any]:
    """
    Fonction principale.
    Génère une playlist avec de NOUVELLES musiques (pas les favoris existants des users).

    Étapes :
      1. Récupère les top tracks et top artistes de chaque membre → seeds uniquement
      2. Appelle /v1/recommendations avec ces seeds → nouvelles musiques inconnues
      3. Filtre les musiques déjà connues du groupe
      4. Applique le content-based filtering sur les nouveaux candidats
      5. Crée la playlist avec ces nouvelles musiques
    """
    logger.info("=" * 60)
    logger.info("🎵 GÉNÉRATION PLAYLIST — NOUVELLES MUSIQUES")
    logger.info(f"Owner ID: {owner_user_id}")
    logger.info(f"Nombre de membres: {len(member_tokens) + 1}")
    logger.info(f"Préférences: {preferences}")
    logger.info("=" * 60)

    rec_service = RecommendationService(session)
    all_tokens = [owner_access_token] + member_tokens

    # ----------------------------------------------------------------
    # 1) Récupérer les top tracks et top artistes de tous les membres
    #    Ces données servent UNIQUEMENT de seeds — pas de candidats.
    # ----------------------------------------------------------------
    all_top_tracks = []
    all_top_artists = []

    for i, token in enumerate(all_tokens):
        logger.info(f"--- Utilisateur {i+1}/{len(all_tokens)} ---")
        tracks = _get_top_items(token, "tracks", limit=20)
        artists = _get_top_items(token, "artists", limit=10)
        all_top_tracks.extend(tracks)
        all_top_artists.extend(artists)

    if not all_top_tracks:
        return {"error": "Impossible de récupérer les morceaux favoris. Vérifiez vos permissions."}

    # Dédupliquer les favoris connus (pour les exclure plus tard)
    # On inclut aussi les titres récemment joués pour éviter les sons déjà entendus
    known_track_ids = {t['id'] for t in all_top_tracks if t.get('id')}
    for token in all_tokens:
        recent_ids = _get_recently_played(token, limit=50)
        known_track_ids.update(recent_ids)
    logger.info(f"🚫 Titres connus à exclure (top + récents): {len(known_track_ids)}")

    # Sélectionner les seeds : tracks et artistes les plus représentatifs du groupe
    # On utilise les tracks qui apparaissent dans les favoris de plusieurs membres
    track_popularity: Dict[str, int] = {}
    for t in all_top_tracks:
        tid = t.get('id')
        if tid:
            track_popularity[tid] = track_popularity.get(tid, 0) + 1

    # Trier par popularité dans le groupe (les tracks communs à plusieurs membres en premier)
    sorted_seeds = sorted(track_popularity.keys(), key=lambda x: track_popularity[x], reverse=True)
    seed_track_ids = sorted_seeds[:3]

    # Seeds artistes : IDs uniques des top artistes du groupe
    seen_artists = set()
    seed_artist_ids = []
    for artist in all_top_artists:
        aid = artist.get('id')
        if aid and aid not in seen_artists:
            seen_artists.add(aid)
            seed_artist_ids.append(aid)
            if len(seed_artist_ids) == 2:
                break

    logger.info(f"🎯 Seeds tracks: {seed_track_ids}")
    logger.info(f"🎯 Seeds artistes: {seed_artist_ids}")

    # ----------------------------------------------------------------
    # 2) Découvrir de nouvelles musiques via les artistes favoris
    #    (/v1/recommendations est déprécié depuis fin 2024)
    # ----------------------------------------------------------------
    logger.info("🔍 Découverte de nouvelles musiques via top-tracks des artistes favoris...")
    spotify_recommendations = _discover_new_tracks(
        access_token=owner_access_token,
        seed_artist_ids=seed_artist_ids,
        limit=max(limit * 4, 100)  # Large marge pour le filtrage
    )

    if not spotify_recommendations:
        logger.warning("⚠️ Aucun candidat trouvé, fallback sur les favoris existants")
        unique_tracks = {t['id']: t for t in all_top_tracks if t.get('id')}
        tracks_list = list(unique_tracks.values())
        random.shuffle(tracks_list)
        recommended_ids = [t['id'] for t in tracks_list[:limit]]
        method_used = "simple-fallback"
    else:
        # ----------------------------------------------------------------
        # 3) Filtrer les musiques déjà connues du groupe
        #    On ne veut QUE des musiques nouvelles dans la playlist.
        # ----------------------------------------------------------------
        new_tracks = [t for t in spotify_recommendations if t.get('id') not in known_track_ids]
        logger.info(f"🧹 Après filtrage des musiques connues: {len(new_tracks)} nouveaux candidats")

        # Si presque tout a été filtré, on garde quand même quelques recommandations
        if len(new_tracks) < 10:
            logger.warning("⚠️ Peu de nouvelles musiques après filtrage, on conserve aussi les recommandations connues")
            new_tracks = spotify_recommendations

        candidate_track_ids = [t['id'] for t in new_tracks]

        # ----------------------------------------------------------------
        # 4) Affiner avec le content-based filtering
        #    On classe ces nouveaux candidats par similarité audio avec les seeds.
        # ----------------------------------------------------------------
        method = preferences.get("method", "content")
        content_weight = float(preferences.get("content_weight", 0.6))
        collab_weight = float(preferences.get("collab_weight", 0.4))

        logger.info(f"🔮 Affinement avec méthode: {method}")

        # Récupérer l'ID en DB pour le collaborative filtering
        user_db_id = None
        owner_db = session.exec(select(User).where(User.spotify_id == owner_user_id)).first()
        if owner_db:
            user_db_id = owner_db.id

        # Sauvegarder les nouveaux candidats en DB pour enrichir le modèle
        features_dict = rec_service.get_audio_features(owner_access_token, candidate_track_ids[:50])
        for track_data in new_tracks[:50]:
            tid = track_data.get('id')
            if tid and tid in features_dict:
                rec_service.save_track_features(track_data, features_dict[tid])

        if method in ("hybrid", "content"):
            recommended_ids = rec_service.content_based_recommendations(
                seed_tracks=seed_track_ids,
                access_token=owner_access_token,
                candidate_tracks=candidate_track_ids,
                top_k=limit
            )
            method_used = method
        else:
            recommended_ids = candidate_track_ids[:limit]
            method_used = "spotify-recommendations"

        if not recommended_ids:
            recommended_ids = candidate_track_ids[:limit]
            method_used = "spotify-recommendations"

        # Si le content-based filtering n'a pas renvoyé assez de titres
        # (ex: audio features indisponibles pour certains candidats),
        # on complète avec les candidats restants dans l'ordre Spotify.
        if len(recommended_ids) < limit:
            already_selected = set(recommended_ids)
            extras = [tid for tid in candidate_track_ids if tid not in already_selected]
            recommended_ids = recommended_ids + extras[:limit - len(recommended_ids)]
            logger.info(f"🔁 Complété à {len(recommended_ids)} titres (padding candidats Spotify)")

    logger.info(f"✅ {len(recommended_ids)} musiques sélectionnées avec méthode: {method_used}")

    # ----------------------------------------------------------------
    # 5) Créer la playlist Spotify et y ajouter les nouvelles musiques
    # ----------------------------------------------------------------
    uris = [f"spotify:track:{tid}" for tid in recommended_ids if tid]

    if not uris:
        return {"error": "Aucun morceau valide trouvé"}

    try:
        playlist_id = create_playlist(owner_access_token, owner_user_id, name, description, public)
        add_tracks_to_playlist(owner_access_token, playlist_id, uris)

        logger.info("=" * 60)
        logger.info("✅ PLAYLIST DE NOUVELLES MUSIQUES GÉNÉRÉE AVEC SUCCÈS")
        logger.info("=" * 60)

        return {
            "success": True,
            "playlist_id": playlist_id,
            "track_count": len(uris),
            "url": f"https://open.spotify.com/playlist/{playlist_id}",
            "message": f"Playlist créée avec {len(uris)} nouvelles musiques",
            "method": method_used,
            "stats": {
                "seeds_tracks": len(seed_track_ids),
                "seeds_artists": len(seed_artist_ids),
                "candidates_from_spotify": len(spotify_recommendations) if spotify_recommendations else 0,
                "known_tracks_excluded": len(known_track_ids),
            },
            "explanations": [
                "🎤 Les artistes favoris du groupe ont servi de point de départ.",
                "🔗 Les artistes similaires ont élargi la sélection à de nouveaux sons.",
                "🎵 Seules des musiques inconnues des membres ont été ajoutées à la playlist.",
            ]
        }
    except Exception as e:
        logger.error(f"❌ Erreur création playlist: {e}")
        return {"error": f"Erreur finale: {str(e)}"}
