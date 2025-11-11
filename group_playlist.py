import random
from typing import Dict, List, Tuple

import requests


SPOTIFY_API_BASE = "https://api.spotify.com/v1"


def _batched(iterable: List[str], size: int) -> List[List[str]]:
    return [iterable[i:i + size] for i in range(0, len(iterable), size)]


def _fetch_top_items(access_token: str) -> Tuple[List[Dict], List[Dict]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    top_tracks = requests.get(
        f"{SPOTIFY_API_BASE}/me/top/tracks",
        headers=headers,
        params={"limit": 10, "time_range": "medium_term"},
        timeout=30,
    ).json().get("items", [])
    top_artists = requests.get(
        f"{SPOTIFY_API_BASE}/me/top/artists",
        headers=headers,
        params={"limit": 10, "time_range": "medium_term"},
        timeout=30,
    ).json().get("items", [])
    return top_tracks, top_artists


def _average_features(access_token: str, track_ids: List[str]) -> Dict[str, float]:
    if not track_ids:
        return {"energy": 0.6, "valence": 0.5}
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        f"{SPOTIFY_API_BASE}/audio-features",
        headers=headers,
        params={"ids": ",".join(track_ids[:100])},
        timeout=30,
    )
    features = [f for f in resp.json().get("audio_features", []) if f]
    if not features:
        return {"energy": 0.6, "valence": 0.5}
    energy = sum(f.get("energy", 0.6) for f in features) / len(features)
    valence = sum(f.get("valence", 0.5) for f in features) / len(features)
    return {"energy": energy, "valence": valence}


def _recommend(access_token: str, seed_tracks: List[str], seed_artists: List[str], limit: int, target_energy: float, target_valence: float) -> List[Dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "seed_tracks": ",".join(seed_tracks[:3]),
        "seed_artists": ",".join(seed_artists[:2]),
        "limit": max(1, min(100, limit)),
        "target_energy": round(target_energy, 3),
        "target_valence": round(target_valence, 3),
    }
    resp = requests.get(f"{SPOTIFY_API_BASE}/recommendations", headers=headers, params=params, timeout=30)
    return resp.json().get("tracks", [])


def create_playlist(access_token: str, owner_user_id: str, name: str, description: str, public: bool) -> str:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {"name": name, "description": description, "public": public}
    resp = requests.post(f"{SPOTIFY_API_BASE}/users/{owner_user_id}/playlists", headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def add_tracks_to_playlist(access_token: str, playlist_id: str, uris: List[str]) -> None:
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    for chunk in _batched(uris, 100):
        requests.post(f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks", headers=headers, json={"uris": chunk}, timeout=30).raise_for_status()


def generate_group_playlist(owner_access_token: str, member_tokens: List[str], name: str, description: str, public: bool, preferences: Dict) -> Dict:
    limit = int(preferences.get("limit", 30))
    # 1) Collecte des tops
    all_tracks: List[Dict] = []
    all_artists: List[Dict] = []
    for token in member_tokens:
        t, a = _fetch_top_items(token)
        all_tracks.extend(t)
        all_artists.extend(a)

    # 2) Seeds diversifies (max 5)
    track_ids = [t["id"] for t in all_tracks if t.get("id")]
    artist_ids = [a["id"] for a in all_artists if a.get("id")]
    seed_tracks = random.sample(track_ids, min(3, len(track_ids))) if track_ids else []
    seed_artists = random.sample(artist_ids, min(2, len(artist_ids))) if artist_ids else []

    # 3) Caracteristiques moyennes
    base_features = _average_features(owner_access_token, seed_tracks)
    target_energy = float(preferences.get("target_energy")) if preferences.get("target_energy") is not None else base_features["energy"]
    target_valence = float(preferences.get("target_valence")) if preferences.get("target_valence") is not None else base_features["valence"]

    # 4) Recommandations
    recs = _recommend(owner_access_token, seed_tracks, seed_artists, limit, target_energy, target_valence)
    uris = []
    seen = set()
    for tr in recs:
        uri = tr.get("uri")
        if uri and uri not in seen:
            seen.add(uri)
            uris.append(uri)

    return {"uris": uris, "seed_tracks": seed_tracks, "seed_artists": seed_artists, "target_energy": target_energy, "target_valence": target_valence}

