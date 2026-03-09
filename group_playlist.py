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


def generate_group_playlist(owner_access_token: str, owner_user_id: str, member_tokens: List[str], 
                           name: str, description: str, public: bool, preferences: Dict[str, Any],
                           session: Session, limit: int = 50) -> Dict[str, Any]:
    """
    Fonction principale - Version améliorée avec recommandation hybride.
    Combine content-based et collaborative filtering pour générer une playlist optimale.
    """
    logger.info("=" * 60)
    logger.info("🎵 DÉBUT GÉNÉRATION PLAYLIST AVEC RECOMMANDATION AVANCÉE")
    logger.info(f"Owner ID: {owner_user_id}")
    logger.info(f"Nombre de membres: {len(member_tokens) + 1}")
    logger.info(f"Préférences: {preferences}")
    logger.info("=" * 60)
    
    # Initialiser le service de recommandation
    rec_service = RecommendationService(session)
    
    all_top_tracks = []
    all_tokens = [owner_access_token] + member_tokens
    
    # 1) Récupérer les top tracks de tous les membres
    logger.info(f"📥 Récupération des données pour {len(all_tokens)} utilisateur(s)")
    
    for i, token in enumerate(all_tokens):
        logger.info(f"--- Utilisateur {i+1}/{len(all_tokens)} ---")
        tracks = _get_top_items(token, "tracks", limit=50)
        all_top_tracks.extend(tracks)
    
    logger.info(f"📊 Total récupéré: {len(all_top_tracks)} tracks")
    
    if not all_top_tracks:
        logger.error("❌ Aucun track récupéré")
        return {"error": "Impossible de récupérer les morceaux favoris. Vérifiez vos permissions."}
    
    # 2) Dédupliquer et préparer les seeds
    unique_tracks = {}
    for track in all_top_tracks:
        track_id = track.get('id')
        if track_id and track_id not in unique_tracks:
            unique_tracks[track_id] = track
    
    tracks_list = list(unique_tracks.values())
    seed_track_ids = [t['id'] for t in tracks_list[:10]]  # Top 10 comme seeds
    candidate_track_ids = [t['id'] for t in tracks_list]
    
    logger.info(f"🎯 {len(seed_track_ids)} seeds sélectionnés")
    logger.info(f"📋 {len(candidate_track_ids)} candidats disponibles")
    
    # 3) Récupérer l'ID utilisateur en DB pour collaborative filtering
    user_db_id = None
    statement = select(User).where(User.spotify_id == owner_user_id)
    owner_user = session.exec(statement).first()
    if owner_user:
        user_db_id = owner_user.id
    
    # 4) Récupérer les audio features et sauvegarder en DB
    logger.info("🎼 Récupération des audio features...")
    features_dict = rec_service.get_audio_features(owner_access_token, seed_track_ids)
    
    # Sauvegarder les tracks en DB avec leurs features
    for track_data in tracks_list[:50]:  # Limiter pour éviter trop de requêtes
        track_id = track_data.get('id')
        if track_id in features_dict:
            rec_service.save_track_features(track_data, features_dict[track_id])
    
    # 5) Générer recommandations HYBRIDES
    method = preferences.get("method", "hybrid")  # "hybrid", "content", "collaborative", "simple"
    content_weight = float(preferences.get("content_weight", 0.6))
    collab_weight = float(preferences.get("collab_weight", 0.4))
    
    logger.info(f"🔮 Méthode de recommandation: {method}")
    
    if method == "hybrid" and user_db_id:
        # Recommandation hybride (content + collaborative)
        recommended_ids = rec_service.hybrid_recommendations(
            user_id=user_db_id,
            seed_tracks=seed_track_ids,
            access_token=owner_access_token,
            candidate_tracks=candidate_track_ids,
            content_weight=content_weight,
            collab_weight=collab_weight,
            top_k=limit
        )
        method_used = "hybrid"
    elif method == "content":
        # Content-based uniquement
        recommended_ids = rec_service.content_based_recommendations(
            seed_tracks=seed_track_ids,
            access_token=owner_access_token,
            candidate_tracks=candidate_track_ids,
            top_k=limit
        )
        method_used = "content-based"
    elif method == "collaborative" and user_db_id:
        # Collaborative uniquement
        collab_track_ids = rec_service.collaborative_recommendations(user_db_id, top_k=limit)
        tracks_dict = {t.id: t.spotify_id for t in session.exec(select(Track)).all()}
        recommended_ids = [tracks_dict.get(tid, "") for tid in collab_track_ids if tid in tracks_dict]
        method_used = "collaborative"
    else:
        # Fallback: méthode simple (déduplication + shuffle)
        random.shuffle(tracks_list)
        recommended_ids = [t['id'] for t in tracks_list[:limit]]
        method_used = "simple"
    
    if not recommended_ids:
        logger.warning("⚠️ Aucune recommandation générée, utilisation de la méthode simple")
        random.shuffle(tracks_list)
        recommended_ids = [t['id'] for t in tracks_list[:limit]]
        method_used = "simple"
    
    logger.info(f"✅ {len(recommended_ids)} recommandations générées avec méthode: {method_used}")
    
    # 6) Convertir en URIs Spotify
    uris = [f"spotify:track:{tid}" for tid in recommended_ids if tid]
    
    if not uris:
        logger.error("❌ Aucun URI valide")
        return {"error": "Aucun morceau valide trouvé"}
    
    logger.info(f"🎶 {len(uris)} URIs collectés")
    
    # 7) Créer la playlist et ajouter les titres
    try:
        playlist_id = create_playlist(owner_access_token, owner_user_id, name, description, public)
        add_tracks_to_playlist(owner_access_token, playlist_id, uris)
        
        logger.info("=" * 60)
        logger.info("✅ PLAYLIST GÉNÉRÉE AVEC SUCCÈS")
        logger.info("=" * 60)

        # Explicabilité de l'IA (Explainable AI)
        explanations = []
        if method_used in ("hybrid", "collaborative"):
            explanations.append("🎧 Certains titres ont été sélectionnés car ils se trouvent au croisement exact des goûts du groupe.")
        if method_used in ("hybrid", "content", "content-based"):
            explanations.append("🔥 L'algorithme a trouvé des jumeaux musicaux partageant la même énergie et le même tempo que vos favoris respectifs.")
        
        return {
            "success": True, 
            "playlist_id": playlist_id, 
            "track_count": len(uris),
            "url": f"https://open.spotify.com/playlist/{playlist_id}",
            "message": f"Playlist créée avec {len(uris)} morceaux",
            "method": method_used,
            "stats": {
                "seeds_used": len(seed_track_ids),
                "candidates_evaluated": len(candidate_track_ids),
                "content_weight": content_weight,
                "collab_weight": collab_weight
            },
            "explanations": explanations
        }
    except Exception as e:
        logger.error(f"❌ Failed to create playlist: {e}")
        return {"error": f"Erreur finale: {str(e)}"}
