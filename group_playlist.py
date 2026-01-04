import requests
import json
import logging
from typing import List, Dict, Any
import random

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CORRECTION CRITIQUE DE L'ADRESSE ---
# C'est la seule adresse officielle de l'API Spotify
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

# --- Fonctions Utilitaires ---

def _get_top_items(access_token: str, item_type: str, limit: int = 20) -> List[Any]:
    """Récupère les top titres ou artistes de l'utilisateur."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": "medium_term"} 
    url = f"{SPOTIFY_API_BASE}/me/top/{item_type}"
    
    logging.info(f"🔍 Appel API: {url}")
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    
    if not resp.ok:
        logging.warning(f"⚠️ Info Top Items ({item_type}): Status {resp.status_code} - {resp.text}")
        return []
    
    try:
        items = resp.json().get("items", [])
        logging.info(f"✅ Top {item_type} récupérés: {len(items)} items")
        return items
    except Exception as e:
        logging.error(f"❌ Erreur parsing JSON: {e}")
        return []


def create_playlist(access_token: str, owner_user_id: str, name: str, description: str, public: bool) -> str:
    """Crée une nouvelle playlist et retourne son ID."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {"name": name, "description": description, "public": public}
    
    url = f"{SPOTIFY_API_BASE}/users/{owner_user_id}/playlists"
    logging.info(f"🎼 Création playlist sur: {url}")
    
    resp = requests.post(url, headers=headers, data=json.dumps(body), timeout=15)
    
    if not resp.ok:
        logging.error(f"❌ Playlist Creation Error: {resp.status_code} - {resp.text}")
        raise Exception(f"Erreur création playlist: {resp.status_code}")
    
    playlist_id = resp.json().get("id")
    logging.info(f"✅ Playlist créée avec ID: {playlist_id}")
    return playlist_id


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: List[str]):
    """Ajoute des titres à une playlist."""
    if not uris:
        logging.warning("⚠️ Aucun URI à ajouter")
        return
        
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    # Spotify limite à 100 tracks par requête
    batch_size = 100
    for i in range(0, len(uris), batch_size):
        batch = uris[i:i+batch_size]
        body = {"uris": batch}
        
        logging.info(f"➕ Ajout de {len(batch)} titres à la playlist (batch {i//batch_size + 1})")
        
        resp = requests.post(f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks", 
                           headers=headers, data=json.dumps(body), timeout=15)

        if not resp.ok:
            logging.error(f"❌ Add Tracks Error: {resp.status_code} - {resp.text}")
            raise Exception(f"Erreur ajout titres: {resp.status_code}")
    
    logging.info(f"✅ Tous les titres ajoutés avec succès")


def generate_group_playlist(owner_access_token: str, owner_user_id: str, member_tokens: List[str], 
                           name: str, description: str, public: bool, preferences: Dict[str, Any], 
                           limit: int = 50) -> Dict[str, Any]:
    """
    Fonction principale - Version sans API Recommendations.
    Crée une playlist basée sur les top tracks de tous les membres.
    """
    logging.info("=" * 60)
    logging.info("🎵 DÉBUT GÉNÉRATION PLAYLIST")
    logging.info(f"Owner ID: {owner_user_id}")
    logging.info(f"Nombre de membres: {len(member_tokens) + 1}")
    logging.info("=" * 60)
    
    all_top_tracks = []
    
    # 1) Récupérer les top tracks de tous les membres
    all_tokens = [owner_access_token] + member_tokens
    logging.info(f"📥 Récupération des données pour {len(all_tokens)} utilisateur(s)")
    
    for i, token in enumerate(all_tokens):
        logging.info(f"--- Utilisateur {i+1}/{len(all_tokens)} ---")
        tracks = _get_top_items(token, "tracks", limit=50)
        all_top_tracks.extend(tracks)

    logging.info(f"📊 Total récupéré: {len(all_top_tracks)} tracks")

    if not all_top_tracks:
        logging.error("❌ Aucun track récupéré")
        return {"error": "Impossible de récupérer les morceaux favoris. Vérifiez vos permissions."}

    # 2) Dédupliquer et mélanger
    unique_tracks = {}
    for track in all_top_tracks:
        track_id = track.get('id')
        if track_id and track_id not in unique_tracks:
            unique_tracks[track_id] = track

    tracks_list = list(unique_tracks.values())
    
    # Mélanger pour plus de variété
    random.shuffle(tracks_list)
    
    # Limiter au nombre demandé
    selected_tracks = tracks_list[:limit]
    
    logging.info(f"🎲 {len(selected_tracks)} tracks sélectionnés après déduplication et mélange")

    # 3) Extraire les URIs
    uris = [track.get("uri") for track in selected_tracks if track.get("uri")]
    
    if not uris:
        logging.error("❌ Aucun URI valide")
        return {"error": "Aucun morceau valide trouvé"}

    logging.info(f"🎶 {len(uris)} URIs collectés")

    # 4) Créer la playlist et ajouter les titres
    try:
        playlist_id = create_playlist(owner_access_token, owner_user_id, name, description, public)
        add_tracks_to_playlist(owner_access_token, playlist_id, uris)
        
        logging.info("=" * 60)
        logging.info("✅ PLAYLIST GÉNÉRÉE AVEC SUCCÈS")
        logging.info("=" * 60)
        
        return {
            "success": True, 
            "playlist_id": playlist_id, 
            "track_count": len(uris),
            "url": f"https://open.spotify.com/playlist/{playlist_id}",
            "message": f"Playlist créée avec {len(uris)} morceaux issus des favoris du groupe"
        }
    except Exception as e:
        logging.error(f"❌ Failed to create playlist: {e}")
        return {"error": f"Erreur finale: {str(e)}"}