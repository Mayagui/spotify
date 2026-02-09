import numpy as np
import requests
import json
import logging
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from sqlmodel import Session, select
from models import User, Track, UserFeedback, ListeningHistory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class RecommendationService:
    """Service de recommandation musicale avec approches collaborative, content-based et hybride"""
    
    def __init__(self, session: Session):
        self.session = session
    
    # ==================== CONTENT-BASED RECOMMENDATION ====================
    
    def get_audio_features(self, access_token: str, track_ids: List[str]) -> Dict[str, Dict]:
        """Récupère les audio features depuis Spotify API"""
        headers = {"Authorization": f"Bearer {access_token}"}
        features_dict = {}
        
        # Spotify limite à 100 tracks par requête
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i:i+100]
            try:
                resp = requests.get(
                    f"{SPOTIFY_API_BASE}/audio-features",
                    headers=headers,
                    params={"ids": ",".join(batch)},
                    timeout=15
                )
                if resp.ok:
                    for feat in resp.json().get("audio_features", []):
                        if feat:
                            features_dict[feat["id"]] = feat
                else:
                    logger.warning(f"Erreur récupération audio features: {resp.status_code}")
            except Exception as e:
                logger.error(f"Exception lors de la récupération audio features: {e}")
        
        return features_dict
    
    def compute_content_similarity(self, track1_features: Dict, track2_features: Dict) -> float:
        """Calcule la similarité cosinus entre deux tracks basée sur audio features"""
        features = ['danceability', 'energy', 'valence', 'tempo', 'acousticness', 
                   'instrumentalness', 'liveness', 'speechiness']
        
        vec1 = np.array([track1_features.get(f, 0) for f in features])
        vec2 = np.array([track2_features.get(f, 0) for f in features])
        
        # Normalisation tempo (0-200 BPM -> 0-1)
        if vec1[3] > 0:
            vec1[3] = min(vec1[3] / 200.0, 1.0)
        if vec2[3] > 0:
            vec2[3] = min(vec2[3] / 200.0, 1.0)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    
    def content_based_recommendations(self, seed_tracks: List[str], access_token: str, 
                                     candidate_tracks: List[str], top_k: int = 20) -> List[str]:
        """Recommandations basées sur similarité de contenu (audio features)"""
        if not seed_tracks or not candidate_tracks:
            return []
        
        seed_features = self.get_audio_features(access_token, seed_tracks)
        candidate_features = self.get_audio_features(access_token, candidate_tracks)
        
        if not seed_features or not candidate_features:
            logger.warning("Impossible de récupérer les audio features")
            return []
        
        scores = []
        for cand_id in candidate_tracks:
            if cand_id in seed_tracks:
                continue
            if cand_id not in candidate_features:
                continue
            
            # Moyenne de similarité avec tous les seeds
            similarities = []
            for seed_id in seed_tracks:
                if seed_id in seed_features:
                    sim = self.compute_content_similarity(
                        seed_features[seed_id],
                        candidate_features[cand_id]
                    )
                    similarities.append(sim)
            
            if similarities:
                avg_sim = np.mean(similarities)
                scores.append((cand_id, avg_sim))
        
        # Trier par score décroissant
        scores.sort(key=lambda x: x[1], reverse=True)
        return [track_id for track_id, _ in scores[:top_k]]
    
    # ==================== COLLABORATIVE FILTERING ====================
    
    def build_user_item_matrix(self) -> Tuple[np.ndarray, Dict[int, int], Dict[int, int], List[int], List[int]]:
        """Construit la matrice user-item pour collaborative filtering"""
        users = self.session.exec(select(User)).all()
        tracks = self.session.exec(select(Track)).all()
        
        if not users or not tracks:
            return np.zeros((0, 0)), {}, {}, [], []
        
        user_idx = {user.id: i for i, user in enumerate(users)}
        track_idx = {track.id: i for i, track in enumerate(tracks)}
        
        matrix = np.zeros((len(users), len(tracks)))
        
        # Remplir avec feedbacks explicites (likes = 1, skips = -0.5, dislikes = -1)
        feedbacks = self.session.exec(select(UserFeedback)).all()
        for fb in feedbacks:
            if fb.user_id in user_idx and fb.track_id in track_idx:
                if fb.feedback_type == "like":
                    score = 1.0
                elif fb.feedback_type == "skip":
                    score = -0.5
                elif fb.feedback_type == "dislike":
                    score = -1.0
                else:
                    score = 0
                matrix[user_idx[fb.user_id]][track_idx[fb.track_id]] = score
        
        # Ajouter poids historique d'écoute (implicit feedback)
        history = self.session.exec(select(ListeningHistory)).all()
        for h in history:
            if h.user_id in user_idx and h.track_id in track_idx:
                # Poids basé sur durée d'écoute (normalisé)
                weight = min(h.duration_ms / 30000.0, 1.0) if h.duration_ms else 0.5
                matrix[user_idx[h.user_id]][track_idx[h.track_id]] += weight * 0.3
        
        user_ids_list = [user.id for user in users]
        track_ids_list = [track.id for track in tracks]
        
        return matrix, user_idx, track_idx, user_ids_list, track_ids_list
    
    def collaborative_recommendations(self, user_id: int, top_k: int = 20) -> List[int]:
        """Recommandations collaboratives basées sur similarité utilisateur"""
        matrix, user_idx, track_idx, user_ids_list, track_ids_list = self.build_user_item_matrix()
        
        if user_id not in user_idx or matrix.shape[0] == 0:
            return []
        
        user_row = user_idx[user_id]
        user_vector = matrix[user_row]
        
        # Si l'utilisateur n'a aucun historique, retourner vide
        if np.sum(np.abs(user_vector)) == 0:
            return []
        
        # Similarité cosinus avec autres utilisateurs
        similarities = []
        for i, other_vector in enumerate(matrix):
            if i == user_row:
                continue
            dot = np.dot(user_vector, other_vector)
            norm1 = np.linalg.norm(user_vector)
            norm2 = np.linalg.norm(other_vector)
            if norm1 > 0 and norm2 > 0:
                sim = dot / (norm1 * norm2)
                similarities.append((i, sim))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Recommander tracks aimés par utilisateurs similaires
        recommended_tracks = defaultdict(float)
        for similar_user_idx, sim_score in similarities[:5]:  # Top 5 utilisateurs similaires
            similar_user_vector = matrix[similar_user_idx]
            for track_idx_val, rating in enumerate(similar_user_vector):
                if rating > 0 and user_vector[track_idx_val] == 0:  # Pas encore écouté
                    recommended_tracks[track_idx_val] += sim_score * rating
        
        # Trier et retourner
        sorted_tracks = sorted(recommended_tracks.items(), key=lambda x: x[1], reverse=True)
        return [track_ids_list[track_idx_val] for track_idx_val, _ in sorted_tracks[:top_k]]
    
    # ==================== HYBRID RECOMMENDATION ====================
    
    def hybrid_recommendations(self, user_id: int, seed_tracks: List[str], 
                              access_token: str, candidate_tracks: List[str],
                              content_weight: float = 0.6, collab_weight: float = 0.4,
                              top_k: int = 30) -> List[str]:
        """Combine content-based et collaborative filtering avec poids configurables"""
        scores = defaultdict(float)
        
        # Content-based recommendations
        content_recs = []
        if seed_tracks and candidate_tracks and content_weight > 0:
            content_recs = self.content_based_recommendations(
                seed_tracks, access_token, candidate_tracks, top_k=top_k*2
            )
            # Attribuer des scores normalisés
            for i, track_id in enumerate(content_recs):
                scores[track_id] += content_weight * (len(content_recs) - i) / max(len(content_recs), 1)
        
        # Collaborative recommendations
        collab_track_ids = []
        if collab_weight > 0:
            collab_track_ids = self.collaborative_recommendations(user_id, top_k=top_k*2)
            # Convertir track.id -> spotify_id
            tracks_dict = {t.id: t.spotify_id for t in self.session.exec(select(Track)).all()}
            collab_recs = [tracks_dict.get(tid, "") for tid in collab_track_ids if tid in tracks_dict]
            
            # Attribuer des scores normalisés
            for i, track_id in enumerate(collab_recs):
                if track_id:
                    scores[track_id] += collab_weight * (len(collab_recs) - i) / max(len(collab_recs), 1)
        
        # Trier par score décroissant
        sorted_recs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [track_id for track_id, _ in sorted_recs[:top_k]]
    
    # ==================== UTILITY METHODS ====================
    
    def save_track_features(self, track_data: Dict, features: Dict) -> Optional[Track]:
        """Sauvegarde ou met à jour un track avec ses audio features en DB"""
        spotify_id = track_data.get("id")
        if not spotify_id:
            return None
        
        # Chercher si le track existe déjà
        statement = select(Track).where(Track.spotify_id == spotify_id)
        existing_track = self.session.exec(statement).first()
        
        track_info = {
            "spotify_id": spotify_id,
            "name": track_data.get("name", "Unknown"),
            "artist": ", ".join([a["name"] for a in track_data.get("artists", [])]),
            "album": track_data.get("album", {}).get("name"),
            "popularity": track_data.get("popularity"),
            "duration_ms": track_data.get("duration_ms"),
            "danceability": features.get("danceability"),
            "energy": features.get("energy"),
            "valence": features.get("valence"),
            "tempo": features.get("tempo"),
            "acousticness": features.get("acousticness"),
            "instrumentalness": features.get("instrumentalness"),
            "liveness": features.get("liveness"),
            "speechiness": features.get("speechiness"),
            "key": features.get("key"),
            "mode": features.get("mode"),
            "time_signature": features.get("time_signature"),
        }
        
        if existing_track:
            for key, value in track_info.items():
                if value is not None:
                    setattr(existing_track, key, value)
            self.session.add(existing_track)
            self.session.commit()
            return existing_track
        else:
            new_track = Track(**track_info)
            self.session.add(new_track)
            self.session.commit()
            return new_track
