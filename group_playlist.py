import requests
import json
import logging
from typing import List, Dict, Any

# Configure logging to help debug API issues
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_USER_ID = "51styg3kpgsxkzsxe0yziefpz" # Placeholder, replace with actual owner ID dynamically if possible

# --- Utility Functions ---

def _get_top_items(access_token: str, item_type: str, limit: int = 5) -> List[Any]:
    """Fetches user's top tracks or artists."""
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": "medium_term"} # Focus on recent preferences
    url = f"{SPOTIFY_API_BASE}/me/top/{item_type}"
    
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    
    if not resp.ok:
        logging.error(f"Spotify API Top Items Error ({item_type}): Status {resp.status_code}, Response: {resp.text}")
        # Return empty list on failure to prevent crash
        return []
    
    try:
        return resp.json().get("items", [])
    except requests.exceptions.JSONDecodeError as e:
        logging.error(f"JSON Decode Error for Top Items (Status {resp.status_code}): {e}. Text was: {resp.text[:200]}...")
        return []

def _average_features(access_token: str, tracks: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculates the average audio features (energy, valence) of a list of tracks."""
    if not tracks:
        return {"energy": 0.5, "valence": 0.5}

    track_ids = [t.get('id') for t in tracks if t.get('id')]
    if not track_ids:
        return {"energy": 0.5, "valence": 0.5}

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"ids": ",".join(track_ids)}

    resp = requests.get(f"{SPOTIFY_API_BASE}/audio-features", headers=headers, params=params, timeout=15)

    if not resp.ok:
        logging.error(f"Spotify API Audio Features Error: Status {resp.status_code}, Response: {resp.text}")
        return {"energy": 0.5, "valence": 0.5}

    try:
        features_data = resp.json().get("audio_features", [])
    except requests.exceptions.JSONDecodeError as e:
        logging.error(f"JSON Decode Error for Audio Features (Status {resp.status_code}): {e}. Text was: {resp.text[:200]}...")
        return {"energy": 0.5, "valence": 0.5}

    total_energy = sum(f.get("energy", 0) for f in features_data if f)
    total_valence = sum(f.get("valence", 0) for f in features_data if f)
    count = len(features_data)
    
    return {
        "energy": total_energy / count if count > 0 else 0.5,
        "valence": total_valence / count if count > 0 else 0.5
    }

def _recommend(access_token: str, seed_tracks: list, seed_artists: list, limit: int, target_energy: float, target_valence: float) -> list:
    """Generates track recommendations using Spotify API."""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    seed_track_ids = [t.get('id') for t in seed_tracks if t.get('id')]
    seed_artist_ids = [a.get('id') for a in seed_artists if a.get('id')]
    
    # Spotify allows a maximum of 5 seeds total
    seeds = seed_track_ids[:2] + seed_artist_ids[:3] 
    
    if not seeds:
        logging.warning("No seeds available for recommendation.")
        return []

    params = {
        "seed_tracks": ",".join(seed_track_ids[:2]),
        "seed_artists": ",".join(seed_artist_ids[:3]),
        "limit": max(1, min(100, limit)),
        "target_energy": round(target_energy, 3),
        "target_valence": round(target_valence, 3),
    }

    # API Call
    resp = requests.get(f"{SPOTIFY_API_BASE}/recommendations", headers=headers, params=params, timeout=30)
    
    # VULNERABILITY FIX: Check status code before trying to parse JSON
    if not resp.ok:
        logging.error(f"Spotify API Recommendation Error: Status {resp.status_code}. Response body: {resp.text}")
        # The crash happened here because resp.json() was called on a non-JSON body.
        return []
    
    try:
        return resp.json().get("tracks", [])
    except requests.exceptions.JSONDecodeError as e:
        logging.error(f"JSON Decode Error for Recommendations (Status {resp.status_code}): {e}. Text was: {resp.text[:200]}...")
        return []


def create_playlist(access_token: str, owner_user_id: str, name: str, description: str, public: bool) -> str:
    """Creates a new playlist and returns its ID."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {"name": name, "description": description, "public": public}
    
    resp = requests.post(f"{SPOTIFY_API_BASE}/users/{owner_user_id}/playlists", headers=headers, data=json.dumps(body), timeout=15)
    
    if not resp.ok:
        logging.error(f"Spotify API Playlist Creation Error: Status {resp.status_code}, Response: {resp.text}")
        raise Exception(f"Could not create playlist: {resp.status_code} - {resp.text}")
    
    return resp.json().get("id")


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: List[str]):
    """Adds tracks to a playlist."""
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {"uris": uris}

    resp = requests.post(f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks", headers=headers, data=json.dumps(body), timeout=15)

    if not resp.ok:
        logging.error(f"Spotify API Add Tracks Error: Status {resp.status_code}, Response: {resp.text}")
        raise Exception(f"Could not add tracks to playlist: {resp.status_code} - {resp.text}")


def generate_group_playlist(owner_access_token: str, member_tokens: List[str], name: str, description: str, public: bool, preferences: Dict[str, Any], limit: int = 50) -> Dict[str, Any]:
    """
    Generates a group playlist based on member preferences and creates it on Spotify.
    This function logic is simplified, assuming it aggregates top tracks/artists from all members.
    """
    all_top_tracks = []
    all_top_artists = []
    
    # 1) Aggregate top items from all members (including the owner)
    for token in [owner_access_token] + member_tokens:
        all_top_tracks.extend(_get_top_items(token, "tracks"))
        all_top_artists.extend(_get_top_items(token, "artists"))

    # Select seeds (e.g., top 5 unique tracks and 5 unique artists overall)
    unique_tracks = {t['id']: t for t in all_top_tracks}.values()
    unique_artists = {a['id']: a for a in all_top_artists}.values()

    seed_tracks = list(unique_tracks)[:5]
    seed_artists = list(unique_artists)[:5]
    
    if not seed_tracks and not seed_artists:
        logging.error("Could not find any seed tracks or artists from members.")
        return {"error": "No music preferences found to generate a playlist."}

    # 2) Determine targets based on owner's top tracks (or general defaults)
    base_features = _average_features(owner_access_token, seed_tracks)
    target_energy = float(preferences.get("target_energy", base_features["energy"]))
    target_valence = float(preferences.get("target_valence", base_features["valence"]))

    # 3) Get recommendations (uses _recommend, where the fix was applied)
    recs = _recommend(owner_access_token, seed_tracks, seed_artists, limit, target_energy, target_valence)
    
    if not recs:
        logging.error("Recommendation returned no tracks.")
        return {"error": "Spotify could not generate recommendations with the given seeds/parameters."}

    uris = [tr.get("uri") for tr in recs if tr.get("uri")]

    # 4) Create playlist and add tracks
    try:
        # Assuming SPOTIFY_USER_ID is the owner's ID
        playlist_id = create_playlist(owner_access_token, SPOTIFY_USER_ID, name, description, public)
        add_tracks_to_playlist(owner_access_token, playlist_id, uris)
        
        return {
            "success": True, 
            "playlist_id": playlist_id, 
            "track_count": len(uris),
            "url": f"https://open.spotify.com/playlist/{playlist_id}"
        }
    except Exception as e:
        logging.error(f"Failed to create or populate playlist: {e}")
        return {"error": f"Failed to finalize playlist creation: {e}"}
